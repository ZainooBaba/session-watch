import json
from unittest.mock import Mock
import httpx
import pytest
from session_watch.core import atomic_write, classify, decide, evidence, normalized, redact

CONFIG = {"llm": {"model": "test", "minimum_confidence": 0.8}}


def page(html="<main>old</main>", **kwargs):
    return {"html": html, "url": "https://example.com/account", "status": 200, "auth_signals": [], **kwargs}


def model(monkeypatch, result=None, failure=False):
    response = Mock()
    response.json.return_value = {"message": {"content": json.dumps(result)}}
    if failure:
        response.raise_for_status.side_effect = httpx.ConnectError("offline")
    monkeypatch.setattr(httpx.Client, "post", lambda *a, **k: response)


def test_initial_and_unchanged_never_call_llm():
    def unexpected(*args):
        raise AssertionError("LLM should not be called")
    assert decide(None, page(), CONFIG, unexpected)["advance"]
    assert decide(page(), page(), CONFIG, unexpected)["classification"] == "unchanged"


def test_initial_auth_screen_never_becomes_baseline():
    assert not decide(None, page(auth_signals=["login"]), CONFIG)["advance"]


@pytest.mark.parametrize("label,advance", [("auth_expired", False), ("uncertain", False), ("content_change", True)])
def test_baseline_policy(label, advance):
    result = decide(page(), page("new"), CONFIG, lambda *a: {"classification": label})
    assert result["advance"] == advance


def test_llm_offline_retains_baseline(monkeypatch):
    model(monkeypatch, failure=True)
    assert not decide(page(), page("new"), CONFIG)["advance"]


def test_auth_signals_override_model(monkeypatch):
    model(monkeypatch, {"classification": "content_change", "confidence": 1, "reason": "changed"})
    assert classify(page(), page("login", auth_signals=["401"]), CONFIG)["classification"] == "auth_expired"


@pytest.mark.parametrize("result", [None, {}, {"classification": "wrong", "confidence": 1, "reason": "x"},
    {"classification": "content_change", "confidence": True, "reason": "x"},
    {"classification": "content_change", "confidence": 0.4, "reason": "x"}])
def test_bad_or_low_confidence_output(monkeypatch, result):
    model(monkeypatch, result)
    assert classify(page(), page("new"), CONFIG)["classification"] == "uncertain"


def test_redaction():
    result = redact('<script>SECRET</script><input value="SECRET"><a href="/x?token=SECRET" data-token="SECRET">OK</a>')
    assert "SECRET" not in result
    assert "OK" in result


def test_normalize_is_opt_in():
    html = '<main nonce="1"><span class="clock">123</span>data</main>'
    assert normalized(html, {}) == html
    assert normalized(html, {"ignore_selectors": [".clock"], "ignore_attributes": ["nonce"]}) == "<main>data</main>"


def test_truncated_payload(monkeypatch):
    model(monkeypatch, {"classification": "content_change", "confidence": 1, "reason": "x"})
    config = {"llm": {"model": "test", "max_input_chars": 1024}}
    before, after = page("a" * 10000), page("b" * 10000)
    assert evidence(before, after, 1024)["truncated"]
    assert classify(before, after, config)["classification"] == "uncertain"


def test_atomic_private_write(tmp_path):
    path = tmp_path / "nested" / "state.json"
    atomic_write(path, "secret")
    assert path.read_text() == "secret"
    assert path.stat().st_mode & 0o077 == 0


def test_minified_page_diff_keeps_changes_beyond_large_header():
    header = "<header>" + "<span>Unchanged navigation</span>" * 1000 + "</header>"
    before = page(header + "<main>One appointment</main>")
    after = page(header + "<main>Two appointments</main>")
    payload = evidence(before, after, 8000)
    assert "Two appointments" in payload["diff"]
    assert "One appointment" in payload["diff"]


def test_verified_dashboard_prevents_soft_auth_guess_from_hiding_change(monkeypatch):
    model(monkeypatch, {'classification':'auth_expired','confidence':.95,'reason':'Might be sign-in'})
    result=classify(page(),page('New invitation',authenticated_verified=True),CONFIG)
    assert result['classification']=='uncertain'
