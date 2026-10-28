import json
from pathlib import Path
from threading import Thread
from http.server import ThreadingHTTPServer
from unittest.mock import Mock
import httpx
from session_watch.reference import values
from session_watch.control import Controller,handler_for


def test_environment_overrides_ignored_file_and_secret_stays_local(tmp_path,monkeypatch):
    monkeypatch.setenv('SESSION_WATCH_EMAIL','env@example.invalid')
    monkeypatch.delenv('SESSION_WATCH_PASSWORD',raising=False)
    (tmp_path/'.env').write_text('SESSION_WATCH_EMAIL="file@example.invalid"\nSESSION_WATCH_PASSWORD="test-only-password"\n')
    root=tmp_path/'state';root.mkdir()
    (root/'reference.json').write_text(json.dumps({'availability':'Example availability'}))
    public=values(tmp_path/'config.toml',root)
    local=values(tmp_path/'config.toml',root,include_password=True)
    assert public['email']=='env@example.invalid' and public['availability']=='Example availability'
    assert public['password'] is None and public['password_local_only']
    assert local['password']=='test-only-password'


def test_reference_api_password_visibility_and_status_separation(tmp_path,monkeypatch):
    monkeypatch.setenv('SESSION_WATCH_EMAIL','test@example.invalid')
    monkeypatch.setenv('SESSION_WATCH_PASSWORD','test-only-password')
    config=tmp_path/'config.toml';config.write_text('')
    controller=Controller(config)
    controller.tunnel.process=Mock();controller.tunnel.process.poll.return_value=None
    controller.tunnel.url='https://test-reference.trycloudflare.com'
    server=ThreadingHTTPServer(('127.0.0.1',0),handler_for(controller,'test-csrf'))
    thread=Thread(target=server.serve_forever,daemon=True);thread.start()
    base=f'http://127.0.0.1:{server.server_port}'
    try:
        with httpx.Client(trust_env=False) as client:
            assert client.get(base+'/reference').json()['password']=='test-only-password'
            public=client.get(base+'/reference',headers={'Host':'test-reference.trycloudflare.com'})
            assert public.status_code==200 and public.json()['password'] is None
            assert 'test-only-password' not in public.text
            assert 'test-only-password' not in client.get(base).text
            assert 'test-only-password' not in client.get(base+'/status').text
    finally:
        server.shutdown();server.server_close();thread.join()
