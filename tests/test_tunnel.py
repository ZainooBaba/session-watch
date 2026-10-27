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
    assert tunnel.status()['access_url'].startswith('https://sample-safe-name.trycloudflare.com/?access=')
    secret = tunnel.secret
    tunnel.stop()
    process.terminate.assert_called_once()
    assert not tunnel.status()['running'] and not tunnel.status()['url']
    assert tunnel.secret != secret


def test_tunnel_requires_private_access_cookie_and_same_origin_writes(tmp_path):
    config = tmp_path/'config.toml';config.write_text('')
    controller = Controller(config)
    controller.tunnel.process = Mock();controller.tunnel.process.poll.return_value = None
    controller.tunnel.url = 'https://sample-safe-name.trycloudflare.com'
    server = ThreadingHTTPServer(('127.0.0.1', 0), handler_for(controller, 'csrf-test'))
    thread = threading.Thread(target=server.serve_forever, daemon=True);thread.start()
    base = f'http://127.0.0.1:{server.server_port}'
    headers = {'Host': 'sample-safe-name.trycloudflare.com'}
    try:
        with httpx.Client(trust_env=False, follow_redirects=False) as client:
            assert client.get(base+'/status',headers=headers).status_code == 403
            assert client.get(base+'/?access=wrong',headers=headers).status_code == 403
            bootstrap = client.get(base+'/?access='+controller.tunnel.secret,headers=headers)
            assert bootstrap.status_code == 303 and bootstrap.headers['location']=='/'
            assert 'HttpOnly' in bootstrap.headers['set-cookie'] and 'Secure' in bootstrap.headers['set-cookie']
            assert 'SameSite=Lax' in bootstrap.headers['set-cookie']
            headers['Cookie']='sw-access='+controller.tunnel.secret
            assert client.get(base+'/status',headers=headers).status_code == 200
            headers['X-Session-Watch-Token']='csrf-test';headers['Origin']='https://unrelated.example'
            assert client.post(base+'/acknowledge',json={},headers=headers).status_code==403
            headers['Origin']=controller.tunnel.url
            assert client.post(base+'/acknowledge',json={},headers=headers).status_code==200
            assert client.post(base+'/event',json={'classification':'auth_expired'},headers=headers).status_code==403
            controller.tunnel.secret='rotated'
            assert client.get(base+'/status',headers=headers).status_code==403
    finally:
        server.shutdown();server.server_close();thread.join()


def test_private_link_redirect_uses_browser_cookie_jar(tmp_path):
    config=tmp_path/'config.toml';config.write_text('')
    controller=Controller(config)
    controller.tunnel.process=Mock();controller.tunnel.process.poll.return_value=None
    controller.tunnel.url='https://private-test.trycloudflare.com'
    server=ThreadingHTTPServer(('127.0.0.1',0),handler_for(controller,'csrf-test'))
    thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
    class LocalOrigin(httpx.BaseTransport):
        def __init__(self):
            self.inner=httpx.HTTPTransport()
        def handle_request(self,request):
            # Keep HTTPS as the cookie-jar origin while reaching the local fixture over HTTP.
            forwarded=httpx.Request(request.method,request.url.copy_with(scheme='http',host='127.0.0.1',port=server.server_port),headers=request.headers,content=request.read())
            return self.inner.handle_request(forwarded)
        def close(self):
            self.inner.close()
    try:
        with httpx.Client(transport=LocalOrigin(),follow_redirects=True) as client:
            response=client.get(controller.tunnel.url+'/?access='+controller.tunnel.secret)
            assert [r.status_code for r in response.history]==[303]
            assert response.status_code==200
            assert 'Session Watch' in response.text
            assert client.get(controller.tunnel.url+'/status').status_code==200
            assert 'SameSite=Lax' in response.history[0].headers['set-cookie']
    finally:
        server.shutdown();server.server_close();thread.join()
