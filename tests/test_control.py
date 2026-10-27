import json
import threading
import time
from http.server import ThreadingHTTPServer
from unittest.mock import Mock

import httpx
import pytest
from session_watch.control import Controller, handler_for


@pytest.fixture
def controller(tmp_path):
    config = tmp_path / 'config.toml'
    config.write_text('[alerts]\nenabled = true\nrepeat_seconds = 0.02\n')
    return Controller(config)


def test_alert_persists_until_acknowledged_and_login_has_priority(controller):
    controller.notify({'classification': 'content_change'})
    controller.notify({'classification': 'auth_expired'})
    controller.notify({'classification': 'content_change'})
    assert controller.status()['alert']['kind'] == 'login'
    restored = Controller(controller.path)
    assert restored.active == controller.active
    version = controller.active['version']
    with pytest.raises(ValueError):
        controller.acknowledge(version - 1)
    controller.acknowledge(version)
    assert controller.active is None
    assert Controller(controller.path).active is None
    controller.notify({'classification': 'content_change'})
    assert controller.active['kind'] == 'change'


def test_audio_repeats_and_acknowledgment_stops_it(controller, monkeypatch):
    player = Mock(return_value={'played': True})
    monkeypatch.setattr('session_watch.control.play_alert', player)
    controller.notify({'classification': 'auth_expired'})
    thread = threading.Thread(target=controller.audio_loop, daemon=True)
    thread.start()
    deadline = time.monotonic() + 1
    while player.call_count < 3 and time.monotonic() < deadline:
        time.sleep(0.005)
    assert player.call_count >= 3
    controller.acknowledge()
    time.sleep(0.03)
    count = player.call_count
    time.sleep(0.06)
    assert player.call_count == count
    controller.closed.set(); controller.wake.set(); thread.join(timeout=1)
    assert not thread.is_alive()


def test_control_http_rejects_unauthorized_and_cross_origin_writes(controller):
    server = ThreadingHTTPServer(('127.0.0.1', 0), handler_for(controller, 'secret'))
    thread = threading.Thread(target=server.serve_forever, daemon=True); thread.start()
    url = f'http://127.0.0.1:{server.server_port}'
    try:
        with httpx.Client(trust_env=False) as client:
            assert client.get(url + '/status').status_code == 200
            assert client.get(url, headers={'Host': 'evil.example'}).status_code == 403
            assert client.post(url + '/event', json={'classification': 'auth_expired'}).status_code == 403
            headers = {'X-Session-Watch-Token': 'secret'}
            assert client.post(url + '/event', headers={**headers, 'Origin': 'https://evil.example'}, json={}).status_code == 403
            assert client.post(url + '/event', headers=headers, json={'classification': 'auth_expired'}).status_code == 200
            from session_watch.alerts import play_alert
            (controller.root / 'control.json').write_text(json.dumps({'port': server.server_port, 'token': 'secret'}))
            delivery = play_alert({'alerts': {'enabled': True, 'persistent': True}},
                                  {'classification': 'content_change'}, controller.root)
            assert delivery['persistent'] and delivery['queued']
            version = client.get(url + '/status').json()['alert']['version']
            assert client.post(url + '/acknowledge', headers=headers, json={'version': version}).status_code == 200
            assert client.get(url + '/status').json()['alert'] is None
    finally:
        server.shutdown(); server.server_close(); thread.join()


def test_login_action_stops_watch_and_save_resumes(controller, monkeypatch):
    worker, login = Mock(), Mock()
    worker.poll.return_value = None
    login.poll.return_value = None
    login.wait.return_value = 0
    controller.worker = worker
    monkeypatch.setattr(controller, 'spawn', Mock(return_value=login))
    controller.notify({'classification': 'auth_expired'})
    controller.begin_login()
    worker.send_signal.assert_called_once()
    assert controller.active is None
    resume = Mock(); monkeypatch.setattr(controller, 'resume', resume)
    controller.save_login()
    login.stdin.write.assert_called_once_with(b'\n')
    resume.assert_called_once()


def test_latest_screenshot_metadata_timestamp_and_http_image(controller):
    from PIL import Image
    from datetime import datetime, timezone
    import os
    assert controller.status()['screenshot'] is None
    folder = controller.root / 'screenshots'
    folder.mkdir()
    image = folder / 'latest.png'
    Image.new('RGB', (25, 25), 'white').save(image)
    timestamp = 1793113200
    os.utime(image, (timestamp, timestamp))
    info = controller.status()['screenshot']
    assert datetime.fromisoformat(info['captured_at']) == datetime.fromtimestamp(timestamp, timezone.utc)
    server = ThreadingHTTPServer(('127.0.0.1', 0), handler_for(controller, 'secret'))
    thread = threading.Thread(target=server.serve_forever, daemon=True); thread.start()
    url = f'http://127.0.0.1:{server.server_port}'
    try:
        with httpx.Client(trust_env=False) as client:
            page = client.get(url).text
            assert 'Latest dashboard screenshot' in page
            assert "timeZone:'America/Chicago'" in page
            response = client.get(url + info['url'])
            assert response.status_code == 200
            assert response.headers['content-type'] == 'image/png'
            assert response.headers['cache-control'] == 'no-store'
            assert response.headers['cross-origin-resource-policy'] == 'same-origin'
            assert response.content == image.read_bytes()
            assert client.get(url + info['url'], headers={'Host': 'evil.example'}).status_code == 403
            previous = info['version']
            os.utime(image, (timestamp + 90, timestamp + 90))
            assert controller.status()['screenshot']['version'] != previous
            image.unlink()
            assert client.get(url + info['url']).status_code == 404
    finally:
        server.shutdown(); server.server_close(); thread.join()


def test_countdown_uses_only_current_watchers_schedule(controller):
    from session_watch.core import atomic_write
    worker = Mock()
    worker.pid = 123
    worker.poll.return_value = None
    controller.worker = worker
    state = {'pid': 123, 'phase': 'waiting', 'next_capture_at': 2000000000, 'interval_seconds': 90}
    atomic_write(controller.root / 'monitor-state.json', json.dumps(state))
    result = controller.status()
    assert result['timing'] == state
    assert isinstance(result['server_time'], float)
    worker.pid = 456
    assert controller.status()['timing'] is None


def test_indicator_stays_red_across_screenshots_checks_and_restart(controller):
    from PIL import Image
    worker = Mock(); worker.pid = 123; worker.poll.return_value = None
    controller.worker = worker
    assert controller.status()['indicator']['state'] == 'active'
    controller.notify({'classification': 'content_change'})
    folder = controller.root / 'screenshots'; folder.mkdir()
    for color in ['white', 'black']:
        Image.new('RGB', (10, 10), color).save(folder / 'latest.png')
        controller.notify({'classification': 'unchanged'})
        assert controller.status()['indicator']['state'] == 'change'
    restored = Controller(controller.path)
    assert restored.status()['indicator']['state'] == 'change'
    controller.acknowledge()
    assert controller.status()['indicator']['state'] == 'active'
    controller.worker = None
    assert controller.status()['indicator']['state'] == 'idle'


def test_signin_state_latches_after_browser_closes_and_takes_priority(controller):
    controller.set_attention('login')
    controller.notify({'classification': 'content_change'})
    assert controller.status()['indicator'] == {'state': 'action', 'label': 'Sign-in needed'}
    controller.acknowledge()
    controller.login = Mock(); controller.login.poll.return_value = None
    assert controller.status()['indicator']['state'] == 'action'
    controller.set_attention('login')
    controller.login.poll.return_value = 1
    assert controller.status()['indicator']['label'] == 'Sign-in needed'
    restored = Controller(controller.path)
    assert restored.status()['indicator']['state'] == 'action'
    controller.acknowledge()
    assert controller.status()['indicator']['state'] == 'idle'


def test_single_signin_button_follows_session_state(controller, monkeypatch):
    assert controller.session_info()['label'] == 'Sign in'
    open_login = Mock(); monkeypatch.setattr(controller, 'begin_login', open_login)
    controller.session_action('signin'); open_login.assert_called_once()
    login = Mock(); login.poll.return_value = None; controller.login = login
    assert controller.session_info()['label'] == "I'm signed in"
    with pytest.raises(ValueError):
        controller.session_action('signin')
    finish = Mock(); monkeypatch.setattr(controller, 'save_login', finish)
    controller.session_action('finish'); finish.assert_called_once()
    login.poll.return_value = 0
    (controller.root / 'storage.json').write_text('{}')
    assert controller.session_info()['label'] == 'Resume monitoring'
    resume = Mock(); monkeypatch.setattr(controller, 'resume', resume)
    controller.session_action('resume'); resume.assert_called_once()
    worker = Mock(); worker.poll.return_value = None; controller.worker = worker
    assert controller.session_info()['label'] == 'Sign in again'


def test_signout_stops_children_forgets_auth_and_preserves_history(controller):
    for name in ['storage.json', 'session.json', 'baseline.json', 'events.jsonl']:
        (controller.root / name).write_text('{}')
    worker, login = Mock(), Mock()
    worker.poll.return_value = None; login.poll.return_value = None
    controller.worker = worker; controller.login = login
    controller.notify({'classification': 'auth_expired'})
    controller.sign_out()
    worker.send_signal.assert_called_once(); worker.wait.assert_called_once()
    login.send_signal.assert_called_once(); login.wait.assert_called_once()
    assert not (controller.root / 'storage.json').exists()
    assert not (controller.root / 'session.json').exists()
    assert (controller.root / 'events.jsonl').exists()
    assert controller.status()['indicator'] == {'state': 'idle', 'label': 'Signed out'}
    assert controller.status()['screenshot'] is None
    assert controller.active is None and controller.attention is None
    assert controller.session_info()['label'] == 'Sign in'
    assert not controller.closed.is_set()


def test_stop_app_stops_processes_and_retains_saved_login(controller):
    (controller.root / 'storage.json').write_text('{}')
    worker = Mock(); worker.poll.return_value = None; controller.worker = worker
    controller.notify({'classification': 'content_change'})
    controller.stop_app()
    assert controller.closed.is_set() and controller.wake.is_set()
    assert controller.worker is None and controller.active is None
    worker.send_signal.assert_called_once()
    assert (controller.root / 'storage.json').exists()


def test_signed_out_screenshot_is_not_served_and_stop_endpoint_shuts_server(controller):
    folder = controller.root / 'screenshots'; folder.mkdir()
    (folder / 'latest.png').write_bytes(b'private image')
    controller.sign_out()
    server = ThreadingHTTPServer(('127.0.0.1', 0), handler_for(controller, 'secret'))
    thread = threading.Thread(target=server.serve_forever, daemon=True); thread.start()
    url = f'http://127.0.0.1:{server.server_port}'
    try:
        with httpx.Client(trust_env=False) as client:
            assert client.get(url + '/screenshot/latest.png').status_code == 403
            assert client.post(url + '/stop', json={}).status_code == 403
            response = client.post(url + '/stop', json={}, headers={'X-Session-Watch-Token': 'secret'})
            assert response.status_code == 200 and response.json()['stopped']
        thread.join(timeout=2)
        assert not thread.is_alive()
    finally:
        server.shutdown(); server.server_close(); thread.join()
