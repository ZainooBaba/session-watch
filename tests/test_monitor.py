import json
from unittest.mock import Mock

import pytest
from session_watch.cli import check


CONFIG = {"llm": {"model": "test"}}


def snapshot(html, auth_signals=None):
    return {"html": html, "url": "https://example.com/account", "status": 200,
            "auth_signals": auth_signals or []}


def test_relogin_preserves_comparison_baseline(tmp_path, monkeypatch):
    browser = Mock()
    browser.capture.return_value = snapshot("old")
    assert check(CONFIG, tmp_path, browser) == "baseline_created"
    baseline = (tmp_path / "baseline.json").read_text()
    browser.capture.return_value = snapshot("login", ["Login redirect"])
    monkeypatch.setattr("session_watch.cli.decide", lambda *a: {"classification": "auth_expired", "advance": False})
    assert check(CONFIG, tmp_path, browser) == "auth_expired"
    assert (tmp_path / "baseline.json").read_text() == baseline
    browser.capture.return_value = snapshot("updated while logged out")
    monkeypatch.setattr("session_watch.cli.decide", lambda before, after, config: {
        "classification": "content_change" if before["html"] == "old" else "uncertain", "advance": True})
    assert check(CONFIG, tmp_path, browser) == "content_change"
    assert json.loads((tmp_path / "baseline.json").read_text())["html"] == "updated while logged out"


def test_session_save_failure_does_not_advance_baseline(tmp_path, monkeypatch):
    previous = snapshot("old")
    (tmp_path / "baseline.json").write_text(json.dumps(previous))
    browser = Mock()
    browser.capture.return_value = snapshot("new")
    browser.save.side_effect = OSError("disk failure")
    monkeypatch.setattr("session_watch.cli.decide", lambda *a: {"classification": "content_change", "advance": True})
    with pytest.raises(OSError):
        check(CONFIG, tmp_path, browser)
    assert json.loads((tmp_path / "baseline.json").read_text()) == previous
