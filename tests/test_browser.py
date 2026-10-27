"""Real Chromium tests; run after `playwright install chromium`."""
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Thread

import pytest
pytest.importorskip("playwright.sync_api")
from session_watch.browser import Browser
from session_watch.cli import check


@pytest.fixture
def website():
    class Handler(BaseHTTPRequestHandler):
        content = "Version one"
        expired = False

        def do_GET(self):
            if self.path == "/account" and (self.expired or "session=valid" not in self.headers.get("Cookie", "")):
                self.send_response(302)
                self.send_header("Location", "/login")
                self.end_headers()
            else:
                self.send_response(200)
                self.send_header("Content-Type", "text/html")
                self.end_headers()
                html = '<form>Sign in</form>' if self.path == "/login" else '<main id="account">' + self.content + '</main>'
                self.wfile.write(html.encode())

        def log_message(self, *args):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}", Handler
    finally:
        server.shutdown()
        server.server_close()
        thread.join()


def test_saved_login_content_change_and_expiry(website, tmp_path, monkeypatch):
    import httpx
    from unittest.mock import Mock
    origin, handler = website
    config = {"url": origin + "/account", "settle_ms": 0, "navigation_timeout_ms": 500,
              "authenticated_selector": "#account", "login_url_patterns": ["/login"],
              "llm": {"model": "test"}}
    response = Mock()
    response.json.return_value = {"message": {"content": json.dumps({
        "classification": "content_change", "confidence": 1, "reason": "Version updated"})}}
    monkeypatch.setattr(httpx.Client, "post", lambda *a, **k: response)
    # Simulate what a human's successful login stores, without automating a real login.
    with Browser(config, tmp_path) as browser:
        browser.context.add_cookies([{"name": "session", "value": "valid", "url": origin}])
        browser.page.goto(origin + "/account")
        browser.page.evaluate("sessionStorage.setItem('example', 'persisted')")
        browser.save()
    with Browser(config, tmp_path) as browser:
        assert check(config, tmp_path, browser) == "baseline_created"
        assert browser.page.evaluate("sessionStorage.getItem('example')") == "persisted"
        assert check(config, tmp_path, browser) == "unchanged"
        handler.content = "Version two"
        assert check(config, tmp_path, browser) == "content_change"
        baseline = (tmp_path / "baseline.json").read_text()
        handler.expired = True
        assert check(config, tmp_path, browser) == "auth_expired"
        assert (tmp_path / "baseline.json").read_text() == baseline
        handler.expired = False
        handler.content = "Version three"
        assert check(config, tmp_path, browser) == "content_change"
        assert "Version three" in (tmp_path / "baseline.json").read_text()
