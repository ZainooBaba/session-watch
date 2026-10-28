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


def test_loading_cannot_advance_baseline_or_trigger_classification(tmp_path,monkeypatch):
    old=snapshot('Fully loaded dashboard');(tmp_path/'baseline.json').write_text(json.dumps(old))
    browser=Mock();browser.capture.return_value=snapshot('<div aria-busy="true">Loading</div>')
    classify=Mock();monkeypatch.setattr('session_watch.cli.decide',classify)
    with pytest.raises(RuntimeError,match='still loading'):
        check(CONFIG,tmp_path,browser)
    classify.assert_not_called()
    assert json.loads((tmp_path/'baseline.json').read_text())==old
    assert not (tmp_path/'alert-inbox.json').exists()


def test_loading_baseline_is_recovered_without_treating_existing_rows_as_new(tmp_path,monkeypatch):
    (tmp_path/'baseline.json').write_text(json.dumps(snapshot('<div aria-busy="true">Loading</div>')))
    browser=Mock();browser.capture.return_value=snapshot('No invites yet. Existing scheduled interviews.')
    assert check(CONFIG,tmp_path,browser)=='baseline_created'
    assert not (tmp_path/'alert-inbox.json').exists()


def test_a_b_a_repeat_suppresses_models_alerts_and_pager(tmp_path,monkeypatch):
    browser=Mock()
    classify=Mock(return_value={'classification':'content_change','advance':True,'reason':'Changed'})
    monkeypatch.setattr('session_watch.cli.decide',classify)
    browser.capture.return_value=snapshot('State A')
    check(CONFIG,tmp_path,browser)
    browser.capture.return_value=snapshot('State B')
    check(CONFIG,tmp_path,browser)
    before=len(json.loads((tmp_path/'alert-inbox.json').read_text()))
    classify.reset_mock()
    browser.capture.return_value=snapshot('State A')
    assert check(CONFIG,tmp_path,browser)=='repeat_snapshot'
    classify.assert_not_called()
    assert len(json.loads((tmp_path/'alert-inbox.json').read_text()))==before
    assert not list((tmp_path/'pager-outbox').glob('*.json'))
    assert json.loads((tmp_path/'baseline.json').read_text())['html']=='State A'


def test_three_loading_failures_create_one_local_alert_and_success_resets_streak(tmp_path,monkeypatch):
    from session_watch.browser import DashboardLoadingError
    from session_watch import alert_store
    browser=Mock();browser.capture.side_effect=DashboardLoadingError('Still loading')
    for _ in range(2):
        with pytest.raises(DashboardLoadingError):check(CONFIG,tmp_path,browser)
    assert not alert_store.read(tmp_path)
    for _ in range(3):
        with pytest.raises(DashboardLoadingError):check(CONFIG,tmp_path,browser)
    items=alert_store.read(tmp_path)
    assert len(items)==1 and items[0]['category']=='loading_stalled'
    assert items[0]['pager_event_id'] is None
    assert not list((tmp_path/'pager-outbox').glob('*.json'))
    alert_store.dismiss(tmp_path,items[0]['id'],items[0]['revision'])
    with pytest.raises(DashboardLoadingError):check(CONFIG,tmp_path,browser)
    assert len(alert_store.read(tmp_path))==1
    browser.capture.side_effect=None;browser.capture.return_value=snapshot('Fully loaded')
    check(CONFIG,tmp_path,browser)
    assert json.loads((tmp_path/'capture-health.json').read_text())['consecutive_loading']==0
    browser.capture.side_effect=DashboardLoadingError('Still loading')
    for _ in range(3):
        with pytest.raises(DashboardLoadingError):check(CONFIG,tmp_path,browser)
    assert len(alert_store.read(tmp_path))==2
