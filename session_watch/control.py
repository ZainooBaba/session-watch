"""Loopback control panel and persistent audio supervisor."""
import argparse
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlsplit
import json
import re
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
from . import pager, alert_store, reference
from .tunnel import Tunnel


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
        if self.active and not (self.root / 'alert-inbox.json').exists():
            legacy = self.active
            alert_store.record(self.root, {'classification': 'auth_expired' if legacy['kind'] == 'login' else 'content_change',
                'reason': 'Unresolved alert carried over from the previous app version.',
                'stage1': (legacy.get('review') or {}).get('stage1', {}),
                'invite': (legacy.get('review') or {}).get('stage2', {})})
        self.sync_alerts()
        self.tunnel = Tunnel(self.root)

    def sync_alerts(self):
        records = alert_store.read(self.root)
        opened = [a for a in records if a['status'] == 'open']
        if alert_store.paused(self.root):
            opened = [a for a in opened if a['category'] == 'auth_needed' and not a.get('silenced_at')]
        item = opened[-1] if opened else None
        self.active = ({'id': item['id'], 'category': item['category'], 'kind': 'login' if item['category'] == 'auth_needed' else 'change',
            'version': int(datetime.fromisoformat(item['updated_at']).timestamp() * 1000000),
            'since': item['created_at'], 'count': len(opened),
            'invite_classification': 'possible_invite' if item['category'] == 'review_needed' else item['stage2'].get('classification'),
            'review': {'time': item['created_at'], 'stage1': item['stage1'], 'stage2': item['stage2'],
                       'pager_event_id': item['pager_event_id']}} if item else None)
        return records

    def persist(self):
        atomic_write(self.root / 'active-alert.json', json.dumps(self.active))
        atomic_write(self.root / 'attention.json', json.dumps(self.attention))

    def notify(self, result):
        with self.lock:
            # Watcher has already persisted this event before advancing its baseline.
            if not result.get('alert_id') or not any(a['id'] == result['alert_id'] for a in alert_store.read(self.root)):
                alert_store.record(self.root, result)
            self.sync_alerts()
            self.persist()
        self.wake.set()

    def dismiss(self, event_id, revision):
        with self.lock:
            alert_store.dismiss(self.root, event_id, revision)
            self.sync_alerts()
            self.persist()
        self.wake.set()

    def set_attention(self, kind):
        with self.lock:
            self.attention = {'kind': kind}
            self.persist()

    def acknowledge(self, version=None):
        with self.lock:
            self.sync_alerts()
            if self.active and version is not None and version != self.active['version']:
                raise ValueError('A newer alert arrived. Review the panel and acknowledge again.')
            for item in alert_store.read(self.root):
                if item['status'] == 'open':
                    alert_store.dismiss(self.root, item['id'], item['revision'])
            self.sync_alerts()
            self.attention = None
            self.persist()
        self.wake.set()

    def audio_loop(self):
        audio_index = 0
        while not self.closed.is_set():
            self.wake.clear()
            with self.lock:
                records = self.sync_alerts()
                pending = [a for a in records if a['status'] == 'open']
                if alert_store.paused(self.root):
                    pending = [a for a in pending if a['category'] == 'auth_needed' and not a.get('silenced_at')]
                categories = list(dict.fromkeys(a['category'] for a in reversed(pending)))
                active = next((a for a in reversed(pending) if a['category'] == categories[audio_index % len(categories)]), None) if categories else None
                audio_index += 1
            if active:
                result = {'classification': 'auth_expired' if active['category'] == 'auth_needed' else 'content_change',
                          'alert_category': active['category'], 'invite': active['stage2']}
                settings = {**self.config, 'alerts': {**self.config.get('alerts', {}), 'persistent': False, 'invite_only': False}}
                played = play_alert(settings, result)
                with self.lock:
                    self.message = '' if played and played.get('played') else 'Sound could not play; check system audio.'
                self.wake.wait(self.config.get('alerts', {}).get('repeat_seconds', 8))
            else:
                self.wake.wait(2)

    def pager_loop(self):
        while not self.closed.is_set():
            try:
                pager.dispatch(self.root, self.config)
            except (OSError, ValueError, TypeError):
                pass
            self.closed.wait(15)

    def spawn(self, command, stdin=None):
        with (self.root / 'watch.log').open('a') as log:
            return subprocess.Popen([sys.executable, '-u', '-m', 'session_watch.cli', command,
                                     '--config', str(self.path)], cwd=self.path.parent,
                                    stdin=stdin or subprocess.DEVNULL, stdout=log, stderr=subprocess.STDOUT)

    def resume(self):
        with self.actions:
            if alert_store.paused(self.root):
                raise ValueError('Sign in to restore monitoring. Dismissing the alert does not restore authentication.')
            if not (self.root / 'storage.json').exists():
                raise ValueError('Sign in before starting monitoring.')
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
            alert_store.silence_auth(self.root)
            self.sync_alerts()
            self.wake.set()
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
            if (self.root / 'signed-out').exists():
                for name in ['baseline.json', 'recent-snapshots.json', 'capture-health.json', 'latest-analysis.json', 'screenshots/baseline.png', 'screenshots/latest.png',
                             'screenshots/previous.png', 'screenshots/latest-diff.png']:
                    (self.root / name).unlink(missing_ok=True)
                (self.root / 'signed-out').unlink()
            alert_store.resolve_auth(self.root)
            self.attention = None
            self.sync_alerts()
            self.persist()
            self.wake.set()
        self.resume()

    def stop_processes(self):
        for process in [self.worker, self.login]:
            if process and process.poll() is None:
                try:
                    process.send_signal(signal.SIGINT)
                    process.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    process.terminate()
                    try:
                        process.wait(timeout=5)
                    except subprocess.TimeoutExpired:
                        process.kill()
                        process.wait(timeout=5)
                except ProcessLookupError:
                    pass
        self.worker = self.login = None

    def sign_out(self):
        with self.actions:
            self.stop_processes()
            for name in ['storage.json', 'session.json']:
                (self.root / name).unlink(missing_ok=True)
            atomic_write(self.root / 'signed-out', datetime.now(timezone.utc).isoformat())
            self.acknowledge()
            alert_store.resolve_auth(self.root)
            self.message = ''

    def stop_app(self):
        self.tunnel.stop()
        self.closed.set()
        self.wake.set()
        with self.actions:
            self.stop_processes()
            # Stopping is not a dismissal: preserve unread alerts for the next launch.
            self.persist()

    def session_info(self):
        login_open = bool(self.login and self.login.poll() is None)
        monitoring = bool(self.worker and self.worker.poll() is None)
        needs_login = (alert_store.paused(self.root) or (self.active and self.active['kind'] == 'login')
                       or (self.attention and self.attention['kind'] == 'login'))
        if login_open:
            return {'step': 'finish', 'label': "I'm signed in",
                    'instruction': 'Finish signing in in the opened browser, then click “I’m signed in” here. We’ll save your session and restart monitoring.'}
        if not monitoring and not needs_login and (self.root / 'storage.json').exists():
            return {'step': 'resume', 'label': 'Resume monitoring',
                    'instruction': 'Your session is saved. Resume monitoring with one click.'}
        return {'step': 'signin', 'label': 'Sign in again' if monitoring else 'Sign in',
                'instruction': 'You’re signed in and monitoring. Only use this button if you need to sign in again.' if monitoring
                else 'Click Sign in. A browser will open for you to complete sign-in.'}

    def session_action(self, expected_step):
        step = self.session_info()['step']
        if step != expected_step:
            raise ValueError('The sign-in status changed. Follow the updated instruction and try again.')
        if step == 'finish':
            self.save_login()
        elif step == 'resume':
            self.resume()
        else:
            self.begin_login()

    def status(self):
        screenshot = self.root / 'screenshots' / 'latest.png'
        try:
            info = screenshot.stat()
            latest = {'captured_at': datetime.fromtimestamp(info.st_mtime, timezone.utc).isoformat(),
                      'version': str(info.st_mtime_ns),
                      'url': '/screenshot/latest.png?v=' + str(info.st_mtime_ns)}
        except FileNotFoundError:
            latest = None
        if (self.root / 'signed-out').exists():
            latest = None
        analysis = None
        try:
            if not (self.root / 'signed-out').exists():
                analysis = json.loads((self.root / 'latest-analysis.json').read_text())
        except (OSError, ValueError):
            pass
        timing = None
        try:
            data = json.loads((self.root / 'monitor-state.json').read_text())
            if self.worker and data.get('pid') == self.worker.pid:
                timing = data
        except (OSError, ValueError):
            pass
        with self.lock:
            inbox = self.sync_alerts()
            deliveries = {}
            for path in (self.root / 'pager-outbox').glob('*.json'):
                try:
                    entry = json.loads(path.read_text())
                    deliveries[entry['id']] = {k: entry.get(k) for k in ['status', 'error', 'accepted_at']}
                except (OSError, ValueError, KeyError):
                    continue
            for item in inbox:
                item['pager_delivery'] = deliveries.get(item.get('pager_event_id'))
            if self.active and self.active.get('review'):
                analysis = self.active['review']
            pager_info = pager.status(self.root, self.config, (analysis or {}).get('pager_event_id'))
            monitoring = bool(self.worker and self.worker.poll() is None)
            login_open = bool(self.login and self.login.poll() is None)
            needs_login = alert_store.paused(self.root) or login_open or (self.active and self.active['kind'] == 'login') or (self.attention and self.attention['kind'] == 'login')
            changed = (self.active and self.active['kind'] == 'change') or (self.attention and self.attention['kind'] == 'change')
            if needs_login:
                indicator = {'state': 'action', 'label': 'Sign-in needed'}
            elif self.active and self.active.get('category') == 'loading_stalled':
                indicator = {'state': 'action', 'label': 'Dashboard still loading'}
            elif changed:
                invite_type = (self.active or self.attention or {}).get('invite_classification')
                label = 'Interview invite' if invite_type == 'interview_invite' else 'Possible invite' if invite_type == 'possible_invite' else 'Change alert'
                indicator = {'state': 'change', 'label': label}
            elif self.attention:
                indicator = {'state': 'action', 'label': 'Action needed'}
            elif monitoring:
                indicator = {'state': 'active', 'label': 'Monitoring'}
            else:
                indicator = {'state': 'idle', 'label': 'Signed out' if (self.root / 'signed-out').exists() else 'Paused'}
            return {'alerts': [] if (self.root / 'signed-out').exists() else list(reversed(inbox)), 'auth_paused': alert_store.paused(self.root), 'alert': self.active, 'message': self.message, 'screenshot': latest,
                    'attention': self.attention, 'indicator': indicator,
                    'tunnel': self.tunnel.status(), 'session': self.session_info(), 'analysis': analysis, 'pager': pager_info, 'signed_out': (self.root / 'signed-out').exists(),
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
            self.send_header('Referrer-Policy', 'no-referrer')
            self.send_header('X-Frame-Options', 'DENY')
            self.send_header('Cross-Origin-Resource-Policy', 'same-origin')
            self.send_header('X-Content-Type-Options', 'nosniff')
            self.end_headers()
            self.wfile.write(body)

        def local_request(self):
            return self.headers.get('Host') == f'127.0.0.1:{self.server.server_port}'

        def valid_host(self):
            host = urlsplit(controller.tunnel.status().get('url') or '').netloc
            return self.local_request() or bool(host and self.headers.get('Host') == host)

        def do_GET(self):
            if not self.valid_host():
                return self.reply({'error': 'Invalid host'}, 403)
            parsed = urlsplit(self.path)
            if parsed.path == '/':
                return self.reply(PAGE.replace('__TOKEN__', token), content_type='text/html; charset=utf-8')
            if parsed.path == '/status':
                return self.reply(controller.status())
            if parsed.path == '/reference':
                return self.reply(reference.values(controller.path, controller.root, include_password=self.local_request()))
            if parsed.path.startswith('/alert-image/'):
                if (controller.root / 'signed-out').exists():
                    return self.reply({'error': 'Sign in to view alert images'}, 403)
                match = re.fullmatch(r'/alert-image/([A-Za-z0-9_-]{1,128})/(after|diff)\.png', parsed.path)
                if not match:
                    return self.reply({'error': 'Not found'}, 404)
                try:
                    data = (controller.root / 'alert-media' / match[1] / (match[2] + '.png')).read_bytes()
                except FileNotFoundError:
                    return self.reply({'error': 'No image saved for this alert'}, 404)
                return self.reply(data, content_type='image/png')
            if urlsplit(self.path).path == '/screenshot/latest.png':
                if (controller.root / 'signed-out').exists():
                    return self.reply({'error': 'Sign in to view dashboard screenshots'}, 403)
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
            expected = f'http://127.0.0.1:{self.server.server_port}' if self.local_request() else controller.tunnel.status().get('url')
            if (not self.valid_host() or self.headers.get('X-Session-Watch-Token') != token
                    or (origin is not None and origin != expected)):
                return self.reply({'error': 'Forbidden'}, 403)
            try:
                data = json.loads(raw_body or '{}')
                if not isinstance(data, dict):
                    raise ValueError('Expected a JSON object')
                if self.path == '/event':
                    if not self.local_request():
                        return self.reply({'error': 'Local monitor only'}, 403)
                    controller.notify(data)
                elif self.path == '/tunnel':
                    if data.get('action') == 'start':
                        controller.tunnel.start(self.server.server_port)
                    elif data.get('action') == 'stop':
                        controller.tunnel.stop()
                    else:
                        raise ValueError('Choose start or stop.')
                elif self.path == '/dismiss':
                    controller.dismiss(data.get('id'), data.get('revision'))
                elif self.path == '/acknowledge':
                    controller.acknowledge(data.get('version'))
                elif self.path == '/pager-config':
                    pager.save_settings(controller.root, data.get('routing_key'), data.get('enabled', True))
                elif self.path == '/signout':
                    controller.sign_out()
                elif self.path == '/stop':
                    controller.stop_app()
                    self.reply({'ok': True, 'stopped': True})
                    threading.Thread(target=self.server.shutdown, daemon=True).start()
                    return
                elif self.path == '/session':
                    controller.session_action(data.get('step'))
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
                if self.path in {'/login', '/save-login', '/resume', '/session'}:
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
        threading.Thread(target=controller.pager_loop, daemon=True).start()
        if (controller.root / 'storage.json').exists() and not (controller.root / 'signed-out').exists() and not alert_store.paused(controller.root):
            controller.resume()
        print(f'Control panel: http://127.0.0.1:{server.server_port}', flush=True)
        try:
            server.serve_forever()
        finally:
            controller.tunnel.stop()
            controller.closed.set(); controller.wake.set(); server.server_close()
            for process in [controller.worker, controller.login]:
                if process and process.poll() is None:
                    process.send_signal(signal.SIGINT)


if __name__ == '__main__':
    main()
