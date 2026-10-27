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
