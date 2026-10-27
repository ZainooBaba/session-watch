import io
import threading
from http.server import ThreadingHTTPServer
from unittest.mock import Mock
import httpx
from session_watch.tunnel import Tunnel
from session_watch.control import Controller, handler_for


def test_tunnel_owns_one_process_and_stop_invalidates_link(tmp_path, monkeypatch):
    process = Mock(); process.poll.return_value = None
    process.stdout = io.StringIO('Quick Tunnel: https://sample-safe-name.trycloudflare.com\nRegistered tunnel connection\n')
    process.wait.return_value = 0
    spawn = Mock(return_value=process)
    monkeypatch.setattr('session_watch.tunnel.subprocess.Popen', spawn)
    monkeypatch.setattr('session_watch.tunnel.shutil.which', lambda name: '/usr/bin/cloudflared')
    monkeypatch.setattr('session_watch.tunnel.threading.Thread', Mock())
    tunnel = Tunnel(tmp_path)
    tunnel.start(8765); tunnel.start(8765)
    assert spawn.call_count == 1
    assert spawn.call_args.args[0] == ['/usr/bin/cloudflared', 'tunnel', '--url', 'http://127.0.0.1:8765', '--no-autoupdate']
    tunnel._read(process)
    assert tunnel.status()['access_url']=='https://sample-safe-name.trycloudflare.com'
    tunnel.stop()
    process.terminate.assert_called_once()
    assert not tunnel.status()['running'] and not tunnel.status()['url']


def test_public_tunnel_allows_full_app_actions_without_private_cookie(tmp_path):
    config=tmp_path/'config.toml';config.write_text('')
    controller=Controller(config)
    controller.notify({'classification':'content_change','reason':'Test change'})
    controller.tunnel.process=Mock();controller.tunnel.process.poll.return_value=None
    controller.tunnel.url='https://sample-safe-name.trycloudflare.com'
    server=ThreadingHTTPServer(('127.0.0.1',0),handler_for(controller,'csrf-test'))
    thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
    base=f'http://127.0.0.1:{server.server_port}'
    headers={'Host':'sample-safe-name.trycloudflare.com'}
    try:
        with httpx.Client(trust_env=False,follow_redirects=False) as client:
            page=client.get(base+'/',headers=headers)
            assert page.status_code==200 and "const token='csrf-test'" in page.text
            assert 'set-cookie' not in page.headers
            status=client.get(base+'/status',headers=headers)
            assert status.status_code==200
            item=status.json()['alerts'][0]
            payload={'id':item['id'],'revision':item['revision']}
            assert client.post(base+'/dismiss',json=payload,headers=headers).status_code==403
            headers['X-Session-Watch-Token']='csrf-test'
            headers['Origin']='https://unrelated.example'
            assert client.post(base+'/dismiss',json=payload,headers=headers).status_code==403
            headers['Origin']=controller.tunnel.url
            assert client.post(base+'/dismiss',json=payload,headers=headers).status_code==200
            assert client.get(base+'/status',headers=headers).json()['alerts'][0]['status']=='dismissed'
            assert client.post(base+'/event',json={'classification':'auth_expired'},headers=headers).status_code==403
            assert client.get(base+'/status',headers={'Host':'unrelated.example'}).status_code==403
            assert client.get(base+'/?access=old-link',headers=headers).status_code==200
    finally:
        server.shutdown();server.server_close();thread.join()
