import json
from unittest.mock import Mock
import pytest
from session_watch import alert_store, pager
from session_watch.cli import check
from session_watch.control import Controller


def change(event_id='change-1', verdict='not_run'):
    return {'alert_id': event_id, 'classification': 'content_change',
            'stage1': {'classification': 'content_change', 'confidence': .95, 'reason': 'A new row appeared.'},
            'invite': {'classification': verdict, 'confidence': .95, 'reason': 'Second check explanation.', 'evidence': 'New invite'}}


def test_individual_dismissal_persists_without_affecting_new_alerts(tmp_path):
    alert_store.record(tmp_path, change())
    first = alert_store.read(tmp_path)[0]
    alert_store.record(tmp_path, change('change-2'))
    alert_store.dismiss(tmp_path, first['id'], first['revision'])
    records = alert_store.read(tmp_path)
    assert [a['status'] for a in records] == ['dismissed', 'open']
    assert records[0]['dismissed_at'] and records[0]['created_at'] and records[0]['reason']
    alert_store.record(tmp_path, change())
    assert alert_store.read(tmp_path)[0]['status'] == 'dismissed'
    assert (tmp_path / 'alert-inbox.json').stat().st_mode & 0o077 == 0


def test_stage_two_upgrades_same_object_and_reopens_if_previously_seen(tmp_path):
    alert_store.record(tmp_path, change())
    first = alert_store.read(tmp_path)[0]
    alert_store.dismiss(tmp_path, first['id'], first['revision'])
    alert_store.record(tmp_path, change(verdict='interview_invite'))
    upgraded = alert_store.read(tmp_path)
    assert len(upgraded) == 1 and upgraded[0]['category'] == 'interview_invite'
    assert upgraded[0]['status'] == 'open' and upgraded[0]['created_at'] == first['created_at']
    assert len(upgraded[0]['history']) == 2
    with pytest.raises(ValueError, match='new information'):
        alert_store.dismiss(tmp_path, first['id'], first['revision'])


def test_auth_dismissal_does_not_resume_or_allow_new_alerts(tmp_path, monkeypatch):
    config = tmp_path / 'config.toml'; config.write_text('')
    controller = Controller(config); root = controller.root
    controller.notify({'classification': 'auth_expired', 'reason': 'Login form is visible.'})
    item = controller.status()['alerts'][0]
    controller.dismiss(item['id'], item['revision'])
    controller.notify(change())
    controller.notify({'classification': 'auth_expired', 'reason': 'Still expired.'})
    assert len(controller.status()['alerts']) == 1
    assert controller.status()['alert'] is None
    assert controller.status()['indicator']['state'] == 'action'
    assert Controller(config).status()['auth_paused']
    with pytest.raises(ValueError, match='Sign in'):
        controller.resume()
    send = Mock(); monkeypatch.setattr('session_watch.pager.httpx.Client', send)
    pager.dispatch(root, {'pager': {'enabled': True, 'routing_key': 'x'*32}})
    send.assert_not_called()
    alert_store.resolve_auth(root)
    assert not controller.status()['auth_paused']
    assert controller.status()['alerts'][0]['status'] == 'resolved'
    controller.notify(change())
    assert controller.status()['alert']['kind'] == 'change'


def test_change_object_exists_before_second_llm_and_negative_stays_local(tmp_path, monkeypatch):
    old = {'html': '<main>Old</main>', 'url': 'https://example.com', 'status': 200}
    (tmp_path/'baseline.json').write_text(json.dumps(old))
    browser = Mock(); browser.capture.return_value = {**old, 'html': '<main>New</main>'}
    monkeypatch.setattr('session_watch.cli.decide', lambda *a: {**change(), 'advance': True})
    def classify(*args):
        item = alert_store.read(tmp_path)[0]
        assert item['status'] == 'open' and item['checking_invite']
        return {'classification': 'not_interview_invite', 'confidence': 1, 'reason': 'Schedule updated.'}
    monkeypatch.setattr('session_watch.invites.classify_invite', classify)
    check({'llm': {'model': 'test'}, 'invites': {'enabled': True}, 'alerts': {'enabled': False}}, tmp_path, browser)
    items = alert_store.read(tmp_path)
    assert len(items) == 1 and items[0]['stage2']['reason'] == 'Schedule updated.'
    assert items[0]['category'] == 'change' and items[0]['status'] == 'open'
    assert not list((tmp_path/'pager-outbox').glob('*.json'))


def test_uncertain_stage_one_cannot_page_even_with_positive_stage_two(tmp_path, monkeypatch):
    old = {'html': '<main>Old</main>', 'url': 'https://example.com', 'status': 200}
    (tmp_path/'baseline.json').write_text(json.dumps(old))
    browser = Mock(); browser.capture.return_value = {**old, 'html': '<main>New invite</main>'}
    monkeypatch.setattr('session_watch.cli.decide', lambda *a: {'classification': 'uncertain', 'advance': False, 'reason': 'Unsure'})
    monkeypatch.setattr('session_watch.invites.classify_invite', lambda *a: change(verdict='interview_invite')['invite'])
    check({'llm': {'model': 'test'}, 'invites': {'enabled': True}}, tmp_path, browser)
    assert alert_store.read(tmp_path)[0]['category'] == 'review_needed'
    assert not list((tmp_path/'pager-outbox').glob('*.json'))


def test_new_captures_and_unchanged_checks_do_not_dismiss_alert(tmp_path, monkeypatch):
    config = tmp_path / 'config.toml'; config.write_text('')
    controller = Controller(config)
    controller.notify(change())
    original = controller.status()['alerts'][0]
    (controller.root/'screenshots').mkdir()
    (controller.root/'screenshots/latest.png').write_bytes(b'new screenshot')
    controller.notify({'classification': 'unchanged'})
    current = controller.status()['alerts'][0]
    assert current['id'] == original['id'] and current['status'] == 'open'
    assert current['created_at'] == original['created_at']
    assert Controller(config).status()['indicator']['state'] == 'change'


def test_authenticated_dismiss_endpoint_only_changes_selected_object(tmp_path):
    import httpx
    import threading
    from http.server import ThreadingHTTPServer
    from session_watch.control import handler_for
    config = tmp_path / 'config.toml'; config.write_text('')
    controller = Controller(config)
    controller.notify(change()); controller.notify(change('change-2'))
    first = alert_store.read(controller.root)[0]
    server = ThreadingHTTPServer(('127.0.0.1', 0), handler_for(controller, 'test-secret'))
    thread = threading.Thread(target=server.serve_forever, daemon=True); thread.start()
    url = f'http://127.0.0.1:{server.server_port}'
    try:
        body = {'id': first['id'], 'revision': first['revision']}
        with httpx.Client(trust_env=False) as client:
            assert client.post(url+'/dismiss', json=body).status_code == 403
            assert client.post(url+'/dismiss', json=body, headers={'X-Session-Watch-Token': 'test-secret'}).status_code == 200
            records = client.get(url+'/status').json()['alerts']
            assert [a['status'] for a in records] == ['open', 'dismissed']
    finally:
        server.shutdown(); server.server_close(); thread.join()
