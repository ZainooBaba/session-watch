"""Loopback control panel and persistent audio supervisor."""
import argparse
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlsplit
import json
import os
from pathlib import Path
import secrets
import signal
import subprocess
import sys
import threading
import time
import tomllib

from filelock import FileLock
from .alerts import alert_kind, play_alert
from .core import atomic_write
from .panel import PAGE


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
        attention_file = self.root / 'attention.json'
        self.attention = json.loads(attention_file.read_text()) if attention_file.exists() else None
        saved = self.root / 'active-alert.json'
        self.active = json.loads(saved.read_text()) if saved.exists() else None
        if self.active:
            self.sequence = self.active['version']

    def persist(self):
        atomic_write(self.root / 'active-alert.json', json.dumps(self.active))
        atomic_write(self.root / 'attention.json', json.dumps(self.attention))

    def notify(self, result):
        kind = alert_kind(result)
        if kind is None:
            return
        with self.lock:
            self.sequence += 1
            if ((self.active and self.active['kind'] == 'login')
                    or (self.attention and self.attention['kind'] == 'login')):
                kind = 'login'
            self.active = {'kind': kind, 'version': self.sequence,
                           'since': self.active['since'] if self.active else datetime.now(timezone.utc).isoformat(),
                           'count': self.active['count'] + 1 if self.active else 1}
            self.attention = {'kind': kind}
            self.persist()
        self.wake.set()

    def set_attention(self, kind):
        with self.lock:
            self.attention = {'kind': kind}
            self.persist()

    def acknowledge(self, version=None):
        with self.lock:
            if self.active and version is not None and version != self.active['version']:
                raise ValueError('A newer alert arrived. Review the panel and acknowledge again.')
            self.active = None
            self.attention = None
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
            self.set_attention('login')

    def save_login(self):
        with self.actions:
            if not self.login or self.login.poll() is not None:
                raise ValueError('Open the login browser first.')
            self.login.stdin.write(b'\n')
            self.login.stdin.flush()
            code = self.login.wait(timeout=60)
            if code:
                self.set_attention('login')
                raise ValueError('Login was not confirmed. Open the login browser and try again.')
            self.acknowledge()
        self.resume()

    def status(self):
        screenshot = self.root / 'screenshots' / 'latest.png'
        try:
            info = screenshot.stat()
            latest = {'captured_at': datetime.fromtimestamp(info.st_mtime, timezone.utc).isoformat(),
                      'version': str(info.st_mtime_ns),
                      'url': '/screenshot/latest.png?v=' + str(info.st_mtime_ns)}
        except FileNotFoundError:
            latest = None
        timing = None
        try:
            data = json.loads((self.root / 'monitor-state.json').read_text())
            if self.worker and data.get('pid') == self.worker.pid:
                timing = data
        except (OSError, ValueError):
            pass
        with self.lock:
            monitoring = bool(self.worker and self.worker.poll() is None)
            login_open = bool(self.login and self.login.poll() is None)
            needs_login = login_open or (self.active and self.active['kind'] == 'login') or (self.attention and self.attention['kind'] == 'login')
            changed = (self.active and self.active['kind'] == 'change') or (self.attention and self.attention['kind'] == 'change')
            if needs_login:
                indicator = {'state': 'action', 'label': 'Sign-in needed'}
            elif changed:
                indicator = {'state': 'change', 'label': 'Change alert'}
            elif self.attention:
                indicator = {'state': 'action', 'label': 'Action needed'}
            elif monitoring:
                indicator = {'state': 'active', 'label': 'Monitoring'}
            else:
                indicator = {'state': 'idle', 'label': 'Paused'}
            return {'alert': self.active, 'message': self.message, 'screenshot': latest,
                    'attention': self.attention, 'indicator': indicator,
                    'timing': timing, 'server_time': time.time(),
                    'monitoring': monitoring, 'login_open': login_open}




def handler_for(controller, token):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def reply(self, value, status=200, content_type='application/json'):
            body = value if isinstance(value, bytes) else value.encode() if isinstance(value, str) else json.dumps(value).encode()
            self.send_response(status)
            self.send_header('Content-Type', content_type)
            self.send_header('Content-Length', str(len(body)))
            self.send_header('Cache-Control', 'no-store')
            self.send_header('X-Frame-Options', 'DENY')
            self.send_header('Cross-Origin-Resource-Policy', 'same-origin')
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
            if urlsplit(self.path).path == '/screenshot/latest.png':
                try:
                    data = (controller.root / 'screenshots' / 'latest.png').read_bytes()
                except FileNotFoundError:
                    return self.reply({'error': 'No dashboard screenshot has been captured yet'}, 404)
                return self.reply(data, content_type='image/png')
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
                if self.path in {'/login', '/save-login', '/resume'}:
                    controller.set_attention('login' if self.path != '/resume' else 'action')
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
