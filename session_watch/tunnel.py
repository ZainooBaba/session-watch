"""Own one on-demand Cloudflare Quick Tunnel for this control service."""
import re
import secrets
import shutil
import subprocess
import threading
from pathlib import Path


class Tunnel:
    def __init__(self, root):
        self.root, self.process, self.url, self.error = root, None, None, None
        self.secret = secrets.token_urlsafe(32)
        self.connected = False
        self.lock = threading.RLock()

    def status(self):
        with self.lock:
            running = bool(self.process and self.process.poll() is None)
            return {'running': running, 'url': self.url if running else None,
                    'access_url': self.url + '/?access=' + self.secret if running and self.url and self.connected else None,
                    'error': self.error, 'starting': running and not self.connected}

    def start(self, port):
        with self.lock:
            if self.process and self.process.poll() is None:
                return
            executable = shutil.which('cloudflared')
            if not executable:
                executable = next((str(p) for p in [Path('/opt/homebrew/bin/cloudflared'), Path('/usr/local/bin/cloudflared')] if p.is_file()), None)
            if not executable:
                raise ValueError('Install cloudflared, then start the tunnel again.')
            self.connected = False
            self.url, self.error, self.secret = None, None, secrets.token_urlsafe(32)
            self.process = subprocess.Popen([executable, 'tunnel', '--url', f'http://127.0.0.1:{port}', '--no-autoupdate'],
                stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                text=True, bufsize=1)
            threading.Thread(target=self._read, args=(self.process,), daemon=True).start()

    def _read(self, process):
        try:
            for line in process.stdout:
                if 'Registered tunnel connection' in line:
                    with self.lock:
                        if self.process is process:
                            self.connected, self.error = True, None
                match = re.search(r'https://[a-z0-9-]+\.trycloudflare\.com\b', line)
                if match:
                    with self.lock:
                        if self.process is process:
                            self.url = match.group(0)
            code = process.wait()
            with self.lock:
                if self.process is process and code:
                    self.error = 'Tunnel exited. Try starting it again.'
        finally:
            process.stdout.close()

    def stop(self):
        with self.lock:
            process, self.process = self.process, None
            self.url, self.error = None, None
            self.connected = False
            self.secret = secrets.token_urlsafe(32)
            if process and process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=5)
