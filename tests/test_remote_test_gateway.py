"""Remote test gateway: auth, origin isolation, route scope and idempotent jobs."""
import hashlib,importlib.util,json,tempfile,threading,time,unittest
import re
from pathlib import Path
from unittest.mock import patch,Mock
from urllib.request import Request,build_opener,ProxyHandler,HTTPRedirectHandler
from urllib.error import HTTPError
from http.server import ThreadingHTTPServer

ROOT=Path(__file__).resolve().parent.parent
class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self,*args,**kwargs):return None

class RemoteGatewayTests(unittest.TestCase):
    def setUp(self):
        spec=importlib.util.spec_from_file_location('test_remote_gateway',ROOT/'dialogue-test-window/remote_gateway.py')
        self.module=importlib.util.module_from_spec(spec);spec.loader.exec_module(self.module)
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.cfg={'salt':'00'*16,'session_key':'11'*32,'public_origin':'https://mobile-test.example'}
        self.cfg['password_hash']=hashlib.pbkdf2_hmac('sha256',b'testpassword',bytes.fromhex(self.cfg['salt']),200000).hex()
        self.module.CONFIG=Path(self.temp.name)/'config.json';self.module.CONFIG.write_text(json.dumps(self.cfg),'utf-8')
        self.http=ThreadingHTTPServer(('127.0.0.1',0),self.module.Handler);self.module.PORT=self.http.server_port
        threading.Thread(target=self.http.serve_forever,daemon=True).start()
        self.addCleanup(self.http.server_close);self.addCleanup(self.http.shutdown)
        self.client=build_opener(ProxyHandler({}),NoRedirect());self.url='http://127.0.0.1:'+str(self.http.server_port)
        self.cookie=self.module.COOKIE+'='+self.module.session(self.cfg)
    def request(self,path,body=None,cookie=None,origin=None,headers=None):
        h=dict(headers or {})
        if cookie:h['Cookie']=cookie
        if body is not None:h.update(Origin=origin or self.url,**{'Content-Type':h.get('Content-Type','application/json')})
        req=Request(self.url+path,body,h)
        try:
            with self.client.open(req,timeout=4) as response:return response.status,response.read(),response.headers
        except HTTPError as response:return response.code,response.read(),response.headers
    def test_login_required_and_cookie_is_secure(self):
        self.assertEqual(self.request('/')[0],303)
        status,_,headers=self.request('/login',b'password=testpassword',headers={'Content-Type':'application/x-www-form-urlencoded'})
        self.assertEqual(status,303)
        for marker in ('Secure','HttpOnly','SameSite=Strict'):self.assertIn(marker,headers['Set-Cookie'])
    def test_wrong_origin_and_bad_password_are_rejected(self):
        self.assertEqual(self.request('/login',b'password=testpassword',origin='http://evil.invalid')[0],403)
        self.assertEqual(self.request('/login',b'password=wrong')[0],403)
        self.assertEqual(self.request('/remote/chat',b'{}',origin='http://evil.invalid',cookie=self.cookie)[0],403)
    def test_only_test_routes_are_exposed_and_backend_headers_are_host_owned(self):
        with patch.object(self.module,'backend',return_value=(200,b'{}','application/json')) as backend:
            self.assertEqual(self.request('/slang?scope=group-12345',cookie=self.cookie)[0],404)
            self.assertEqual(self.request('/config/config.json',cookie=self.cookie)[0],404)
            backend.assert_not_called()
            self.assertEqual(self.request('/health',cookie=self.cookie)[0],200)
            backend.assert_called_once_with('/health')
    def test_one_remote_request_does_not_start_two_model_jobs(self):
        body=b'{"nickname":"synthetic","message":"hello"}'
        h={'X-Test-Request-ID':'a'*32};fake=Mock(return_value=(200,b'{"reply":"ok"}','application/json'))
        with patch.object(self.module,'backend',fake):
            status,raw,_=self.request('/remote/chat',body,cookie=self.cookie,headers=h)
            self.assertEqual(status,202);identity=json.loads(raw)['id']
            self.assertEqual(self.request('/remote/chat',body,cookie=self.cookie,headers=h)[0],202)
            self.assertEqual(self.request('/remote/chat',b'{"message":"different"}',cookie=self.cookie,headers=h)[0],409)
            for _ in range(20):
                status,raw,_=self.request('/remote/jobs/'+identity,cookie=self.cookie)
                if json.loads(raw)['state']=='done':break
                threading.Event().wait(.01)
            self.assertEqual(json.loads(raw)['body']['reply'],'ok');self.assertEqual(fake.call_count,1)
            stranger=self.module.COOKIE+'='+self.module.session(self.cfg)
            self.assertEqual(self.request('/remote/jobs/'+identity,cookie=stranger)[0],404)
    def test_signed_session_cannot_be_forged_and_logout_revokes_it(self):
        self.assertIsNone(self.module.owner('forged.signature',self.cfg))
        self.assertEqual(self.request('/logout',b'x',cookie=self.cookie)[0],303)
        self.assertEqual(self.request('/health',cookie=self.cookie)[0],401)
    def test_safari_form_without_origin_requires_login_nonce(self):
        status,html,_=self.request('/login')
        nonce=re.search('name="login_csrf" value="([^"]+)"',html.decode()).group(1)
        from urllib.parse import urlencode
        body=urlencode({'password':'testpassword','login_csrf':nonce}).encode()
        request=Request(self.url+'/login',body,{'Content-Type':'application/x-www-form-urlencoded'})
        try:
            with self.client.open(request,timeout=4) as response:code=response.status
        except HTTPError as error:code=error.code
        self.assertEqual(code,303)
        self.assertIsNone(self.module.owner(nonce,self.cfg),'Public login nonce must never authenticate a session')
    def test_missing_origin_api_still_requires_authenticated_session_csrf(self):
        token=self.cookie.split('=',1)[1];user=self.module.owner(token,self.cfg)
        request=Request(self.url+'/social/reset',b'{}',{'Cookie':self.cookie,'Content-Type':'application/json'})
        with self.assertRaises(HTTPError) as error:self.client.open(request,timeout=4)
        self.assertEqual(error.exception.code,403)
        with patch.object(self.module,'backend',return_value=(200,b'{"ok":true}','application/json')):
            request=Request(self.url+'/social/reset',b'{}',{'Cookie':self.cookie,'Content-Type':'application/json','X-Test-CSRF':self.module.session_csrf(user,self.cfg)})
            with self.client.open(request,timeout=4) as response:self.assertEqual(response.status,200)

if __name__=='__main__':unittest.main()
