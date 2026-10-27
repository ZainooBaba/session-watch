"""Loopback control panel and persistent audio supervisor."""
import argparse
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import secrets
import signal
import subprocess
import sys
import threading
import tomllib

from filelock import FileLock
from .alerts import alert_kind, play_alert
from .core import atomic_write


class Controller:
    def __init__(self, config_path):
        self.path = Path(config_path).resolve()
        self.config = tomllib.loads(self.path.read_text())
        self.root = (self.path.parent / self.config.get('state_dir', '.session-watch')).resolve()
        self.root.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.lock = threading.RLock()
        self.actions = threading.Lock()
        self.wake = threading.Event()
        self.closed = threading.Event()
        self.worker = self.login = None
        self.message = ''
        self.sequence = 0
        saved = self.root / 'active-alert.json'
        self.active = json.loads(saved.read_text()) if saved.exists() else None
        if self.active:
            self.sequence = self.active['version']

    def persist(self):
        atomic_write(self.root / 'active-alert.json', json.dumps(self.active))

    def notify(self, result):
        kind = alert_kind(result)
        if kind is None:
            return
        with self.lock:
            self.sequence += 1
            if self.active and self.active['kind'] == 'login':
                kind = 'login'
            self.active = {'kind': kind, 'version': self.sequence,
                           'since': self.active['since'] if self.active else datetime.now(timezone.utc).isoformat(),
                           'count': self.active['count'] + 1 if self.active else 1}
            self.persist()
        self.wake.set()

    def acknowledge(self, version=None):
        with self.lock:
            if self.active and version is not None and version != self.active['version']:
                raise ValueError('A newer alert arrived. Review the panel and acknowledge again.')
            self.active = None
            self.persist()
        self.wake.set()

    def audio_loop(self):
        while not self.closed.is_set():
            self.wake.clear()
            with self.lock:
                active = dict(self.active) if self.active else None
            if active:
                result = {'classification': 'auth_expired' if active['kind'] == 'login' else 'content_change'}
                settings = {**self.config, 'alerts': {**self.config.get('alerts', {}), 'persistent': False}}
                played = play_alert(settings, result)
                with self.lock:
                    self.message = '' if played and played.get('played') else 'Sound could not play; check system audio.'
                self.wake.wait(self.config.get('alerts', {}).get('repeat_seconds', 8))
            else:
                self.wake.wait()

    def spawn(self, command, stdin=None):
        with (self.root / 'watch.log').open('a') as log:
            return subprocess.Popen([sys.executable, '-u', '-m', 'session_watch.cli', command,
                                     '--config', str(self.path)], cwd=self.path.parent,
                                    stdin=stdin or subprocess.DEVNULL, stdout=log, stderr=subprocess.STDOUT)

    def resume(self):
        with self.actions:
            if self.login and self.login.poll() is None:
                raise ValueError('Finish sign-in and save the session first.')
            if self.worker and self.worker.poll() is None:
                return
            self.worker = self.spawn('watch')
            atomic_write(self.root / 'watch.pid', str(self.worker.pid))

    def begin_login(self):
        with self.actions:
            if self.login and self.login.poll() is None:
                return
            if self.worker and self.worker.poll() is None:
                self.worker.send_signal(signal.SIGINT)
                self.worker.wait(timeout=45)
            self.login = self.spawn('login', subprocess.PIPE)
            self.acknowledge()

    def save_login(self):
        with self.actions:
            if not self.login or self.login.poll() is not None:
                raise ValueError('Open the login browser first.')
            self.login.stdin.write(b'\n')
            self.login.stdin.flush()
            code = self.login.wait(timeout=60)
            if code:
                raise ValueError('Login was not confirmed. Open the login browser and try again.')
            self.acknowledge()
        self.resume()

    def status(self):
        with self.lock:
            return {'alert': self.active, 'message': self.message,
                    'monitoring': bool(self.worker and self.worker.poll() is None),
                    'login_open': bool(self.login and self.login.poll() is None)}


PAGE = '''<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Session Watch</title><style>body{font:17px system-ui;background:#102334;color:#eef6fa;margin:0;padding:40px}main{max-width:760px;margin:auto}section{background:#1b3548;padding:28px;border-radius:18px;margin:24px 0}button{font:inherit;padding:12px 18px;margin:6px;border:0;border-radius:9px;background:#8ad8ce;color:#102334;cursor:pointer}button:disabled{opacity:.5}#alert{font-size:24px;font-weight:650}small{color:#b8cbd6}a{color:#8ad8ce}</style>
<main><h1>Session Watch</h1><p>Your dashboard monitor and sound controls</p><section><p id="status">Connecting…</p><p id="alert"></p><p id="message"></p><button onclick="act('acknowledge')">Silence alert / acknowledge</button><p><small>Basso: sign-in needed · Glass: HTML or screenshot changed.<br>Sounds repeat until acknowledged. A new change can start a new alert.</small></p></section><section><h2>Sign in again</h2><p>Open the browser, complete sign-in yourself, then save the session.</p><button onclick="act('login')">1. Open login browser</button><button onclick="act('save-login')">2. Save session & resume</button><button onclick="act('resume')">Resume monitoring</button></section><p id="result" role="status"></p></main>
<script>const token='__TOKEN__';let version=null;let busy=false;async function refresh(){const r=await fetch('/status',{cache:'no-store'});const s=await r.json();version=s.alert?.version??null;document.getElementById('status').textContent=s.login_open?'Waiting for your sign-in':s.monitoring?'Monitoring is running':'Monitoring is paused';document.getElementById('alert').textContent=s.alert?(s.alert.kind==='login'?'Sign-in required — alert repeating':'Change detected — alert repeating'):'No active sound alert';document.getElementById('message').textContent=s.message||''}async function act(action){if(busy)return;busy=true;document.querySelectorAll('button').forEach(b=>b.disabled=true);document.getElementById('result').textContent='Working…';try{const r=await fetch('/'+action,{method:'POST',headers:{'Content-Type':'application/json','X-Session-Watch-Token':token},body:JSON.stringify({version})});const d=await r.json();if(!r.ok)throw Error(d.error);document.getElementById('result').textContent=action==='acknowledge'?'Alert acknowledged.':action==='login'?'Sign in in the opened browser, then save the session.':'Done.'}catch(e){document.getElementById('result').textContent=e.message}finally{busy=false;document.querySelectorAll('button').forEach(b=>b.disabled=false);await refresh()}}refresh();setInterval(()=>refresh().catch(()=>{document.getElementById('status').textContent='Control service is unavailable'}),2000);</script></html>'''


def handler_for(controller, token):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def reply(self, value, status=200, content_type='application/json'):
            body = value.encode() if isinstance(value, str) else json.dumps(value).encode()
            self.send_response(status)
            self.send_header('Content-Type', content_type)
            self.send_header('Content-Length', str(len(body)))
            self.send_header('Cache-Control', 'no-store')
            self.send_header('X-Frame-Options', 'DENY')
            self.send_header('X-Content-Type-Options', 'nosniff')
            self.end_headers()
            self.wfile.write(body)

        def valid_host(self):
            return self.headers.get('Host') == f'127.0.0.1:{self.server.server_port}'

        def do_GET(self):
            if not self.valid_host():
                return self.reply({'error': 'Invalid host'}, 403)
            if self.path == '/':
                return self.reply(PAGE.replace('__TOKEN__', token), content_type='text/html; charset=utf-8')
            if self.path == '/status':
                return self.reply(controller.status())
            self.reply({'error': 'Not found'}, 404)

        def do_POST(self):
            try:
                size = int(self.headers.get('Content-Length', '0'))
                if not 0 <= size <= 16384:
                    raise ValueError('Request too large')
                raw_body = self.rfile.read(size)
            except ValueError as exc:
                return self.reply({'error': str(exc)}, 400)
            origin = self.headers.get('Origin')
            expected = f'http://127.0.0.1:{self.server.server_port}'
            if (not self.valid_host() or self.headers.get('X-Session-Watch-Token') != token
                    or (origin is not None and origin != expected)):
                return self.reply({'error': 'Forbidden'}, 403)
            try:
                data = json.loads(raw_body or '{}')
                if not isinstance(data, dict):
                    raise ValueError('Expected a JSON object')
                if self.path == '/event':
                    controller.notify(data)
                elif self.path == '/acknowledge':
                    controller.acknowledge(data.get('version'))
                elif self.path == '/login':
                    controller.begin_login()
                elif self.path == '/save-login':
                    controller.save_login()
                elif self.path == '/resume':
                    controller.resume()
                else:
                    return self.reply({'error': 'Not found'}, 404)
                self.reply({'ok': True})
            except (ValueError, TypeError, OSError, subprocess.SubprocessError) as exc:
                self.reply({'error': str(exc)}, 400)
    return Handler


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--config', default='config.toml')
    parser.add_argument('--port', type=int, default=8765)
    args = parser.parse_args()
    os.umask(0o077)
    controller = Controller(args.config)
    with FileLock(str(controller.root / 'control.lock'), timeout=0):
        token = secrets.token_hex(32)
        server = ThreadingHTTPServer(('127.0.0.1', args.port), handler_for(controller, token))
        atomic_write(controller.root / 'control.json', json.dumps({'port': server.server_port, 'token': token}))
        atomic_write(controller.root / 'control.pid', str(os.getpid()))
        threading.Thread(target=controller.audio_loop, daemon=True).start()
        controller.resume()
        print(f'Control panel: http://127.0.0.1:{server.server_port}', flush=True)
        try:
            server.serve_forever()
        finally:
            controller.closed.set(); controller.wake.set(); server.server_close()
            for process in [controller.worker, controller.login]:
                if process and process.poll() is None:
                    process.send_signal(signal.SIGINT)


if __name__ == '__main__':
    main()
