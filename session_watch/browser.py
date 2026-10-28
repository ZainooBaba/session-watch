from __future__ import annotations
import json
from pathlib import Path
from urllib.parse import urlsplit

from .core import atomic_write, normalized

# Playwright restores cookies/localStorage/IndexedDB; explicitly restore sessionStorage.
RESTORE_SESSION = """data => {
  const values = data[location.origin];
  if (values && !sessionStorage.getItem('__session_watch_restored')) {
    for (const [key, value] of Object.entries(values)) sessionStorage.setItem(key, value);
    sessionStorage.setItem('__session_watch_restored', '1');
  }
}"""


class DashboardLoadingError(RuntimeError):
    pass


class Browser:
    def __init__(self, config: dict, root: Path, headed: bool = False):
        self.config, self.root, self.headed = config, root, headed

    def __enter__(self):
        from playwright.sync_api import sync_playwright
        self.playwright = sync_playwright().start()
        try:
            self.browser = self.playwright.chromium.launch(headless=not self.headed)
            # Keep website rollout decisions consistent between login and monitoring.
            # Derive the identity from this installed browser, rather than pinning a version.
            probe = self.browser.new_page()
            user_agent = probe.evaluate("navigator.userAgent").replace("HeadlessChrome/", "Chrome/")
            probe.context.close()
            state = self.root / "storage.json"
            self.context = self.browser.new_context(viewport={"width": 1280, "height": 900}, device_scale_factor=1, user_agent=user_agent, storage_state=str(state) if state.exists() else None)
            session = self.root / "session.json"
            if session.exists():
                self.context.add_init_script("(" + RESTORE_SESSION + ")(" + session.read_text() + ")")
            self.page = self.context.new_page()
            self.page.set_default_timeout(self.config.get("navigation_timeout_ms", 30000))
            return self
        except Exception:
            self.playwright.stop()
            raise

    def __exit__(self, *args):
        self.browser.close()
        self.playwright.stop()

    def screenshot(self):
        return self.page.screenshot(full_page=True, animations="disabled", caret="hide")

    def save(self):
        atomic_write(self.root / "storage.json", json.dumps(self.context.storage_state(indexed_db=True)))
        sessions = {}
        for page in self.context.pages:
            if page.url.startswith(("http://", "https://")):
                origin, values = page.evaluate("() => [location.origin, {...sessionStorage}]")
                values.pop("__session_watch_restored", None)
                sessions[origin] = values
        atomic_write(self.root / "session.json", json.dumps(sessions))

    def capture(self):
        response = self.page.goto(self.config["url"], wait_until="domcontentloaded")
        if response is None:
            raise RuntimeError("Navigation did not return a document response")
        status = response.status
        if status >= 400 and status not in (401, 403):
            raise RuntimeError(f"HTTP {status}; baseline retained")
        self.page.wait_for_timeout(self.config.get("settle_ms", 1500))
        signals = []
        if status in (401, 403):
            signals.append(f"HTTP {status}: human login/access review required")
        path = urlsplit(self.page.url).path.lower()
        if any(pattern.lower() in path for pattern in self.config.get("login_url_patterns", [])):
            signals.append("Redirected to a configured login URL")
        login = self.config.get("login_selector")
        if login and self.page.locator(login).first.is_visible():
            signals.append("Configured login element is visible")
        auth = self.config.get("authenticated_selector")
        if auth:
            try:
                self.page.locator(auth).first.wait_for(state="visible")
            except Exception as exc:
                from playwright.sync_api import TimeoutError
                if not isinstance(exc, TimeoutError):
                    raise
                signals.append("Authenticated element is absent")
        ready = self.config.get("ready_selector")
        if ready and not signals:
            self.page.locator(ready).first.wait_for(state="visible")
        if not signals:
            # Authentication can be ready while the dashboard's data is still loading.
            selector = self.config.get('loading_selector', '[aria-busy="true"], [id$="-loading-container"]')
            stable_ms = self.config.get('content_stable_ms', 1000)
            self.page.evaluate("() => { window.__sessionWatchContent = null; }")
            try:
                self.page.wait_for_function("""({selector, stableMs}) => {
                  const busy = [...document.querySelectorAll(selector)].some(el => {
                    const style = getComputedStyle(el);
                    return el.getClientRects().length && style.display !== 'none' && style.visibility !== 'hidden';
                  });
                  if (busy) { window.__sessionWatchContent = null; return false; }
                  const text = document.body.innerText;
                  const previous = window.__sessionWatchContent;
                  if (!previous || previous.text !== text) {
                    window.__sessionWatchContent = {text, since: performance.now()};
                    return stableMs === 0;
                  }
                  return performance.now() - previous.since >= stableMs;
                }""", arg={'selector': selector, 'stableMs': stable_ms},
                    timeout=self.config.get('navigation_timeout_ms', 30000))
            except Exception as exc:
                from playwright.sync_api import TimeoutError
                if not isinstance(exc, TimeoutError):
                    raise
                raise DashboardLoadingError('Dashboard is still loading or changing; capture skipped and previous baseline retained.') from None
        return {"loading": False, "url": self.page.url, "status": status, "auth_signals": signals,
                "authenticated_verified": bool(auth and not signals),
                "html": normalized(self.page.content(), self.config)}
