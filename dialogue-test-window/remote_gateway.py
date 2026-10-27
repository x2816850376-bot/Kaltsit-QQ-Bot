"""Authenticated loopback gateway for the isolated test window, never QQ tools."""
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from http.cookies import SimpleCookie
from urllib.parse import urlsplit,parse_qs
from urllib.request import Request,build_opener,ProxyHandler
from urllib.error import HTTPError
from pathlib import Path
import base64,hashlib,hmac,json,secrets,threading,time,unicodedata
import html

ROOT=Path(__file__).resolve().parent.parent
CONFIG=ROOT/'runtime/remote-test/config.private.json'
BACKEND='http://127.0.0.1:18885'
PORT=18886
COOKIE='__Host-kaltsit_test'
LOCK=threading.RLock();JOBS={};REQUESTS={};FAILS={};CHAT_TIMES=[];REVOKED=set()
OPENER=build_opener(ProxyHandler({}))
GET_PATHS={'/','/index.html','/health'}
POST_PATHS={'/chat/ack','/social/reset','/voice-preview/mode'}
LOGIN='''<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>凯尔希远程测试</title><style>body{font:16px system-ui;background:#101816;color:#e7eeea;padding:12vh 22px}main{max-width:420px;margin:auto}input,button{font:inherit;padding:14px;border-radius:8px;box-sizing:border-box;width:100%;margin:10px 0}p{color:#a3b4a9}</style><main><h2>凯尔希 · 远程测试</h2><p>输入本机生成的访问口令。这里仅供人格测试，不发送QQ群消息</p><form method="post" action="/login"><input name="password" type="password" autocomplete="current-password" placeholder="访问口令" required><button>进入测试窗口</button></form></main></html>'''
REMOTE_SCRIPT=r'''<script>
(()=>{const nativeFetch=window.fetch.bind(window);const csrf=__SESSION_CSRF__;const realFetch=(input,init)=>{
 const options={...(init||{})};if(typeof input==='string'&&input.startsWith('/')&&!input.startsWith('//')&&(options.method||'GET').toUpperCase()==='POST')options.headers={...(options.headers||{}),'X-Test-CSRF':csrf};return nativeFetch(input,options);
};window.fetch=async(input,init)=>{
 if(input!=='/chat'||init?.method!=='POST')return realFetch(input,init);
 const requestId=crypto.randomUUID().replaceAll('-','');
 const options={...init,headers:{...init.headers,'X-Test-Request-ID':requestId}};
 let start;try{start=await realFetch('/remote/chat',options);}catch{start=await realFetch('/remote/chat',options);}
 if(!start.ok)return start;const job=await start.json();
 for(let i=0;i<180;i++){await new Promise(resolve=>setTimeout(resolve,1000));const response=await realFetch('/remote/jobs/'+job.id);if(!response.ok)return response;const state=await response.json();if(state.state==='done')return new Response(JSON.stringify(state.body),{status:state.status,headers:{'Content-Type':'application/json'}});}
 return new Response(JSON.stringify({error:'回复仍在处理，请暂勿重复提交同一问题'}),{status:504,headers:{'Content-Type':'application/json'}});
};})();</script>'''

def config():return json.loads(CONFIG.read_text('utf-8'))
def normalise(password):return ''.join(c for c in unicodedata.normalize('NFKC',password).casefold() if c in 'abcdefghijklmnopqrstuvwxyz0123456789')
def password_ok(password,cfg):
    digest=hashlib.pbkdf2_hmac('sha256',normalise(password).encode(),bytes.fromhex(cfg['salt']),200000).hex()
    return hmac.compare_digest(digest,cfg['password_hash'])
def session(cfg):
    body=base64.urlsafe_b64encode(json.dumps({'exp':int(time.time()+86400),'nonce':secrets.token_hex(16)},separators=(',',':')).encode()).decode().rstrip('=')
    return body+'.'+hmac.new(bytes.fromhex(cfg['session_key']),body.encode(),hashlib.sha256).hexdigest()
def owner(raw,cfg):
    try:
        body,signature=raw.split('.',1)
        if not hmac.compare_digest(signature,hmac.new(bytes.fromhex(cfg['session_key']),body.encode(),hashlib.sha256).hexdigest()):return None
        value=json.loads(base64.urlsafe_b64decode(body+'='*(-len(body)%4)))
        if not time.time()<value['exp']<=time.time()+86500 or value['nonce'] in REVOKED:return None
        return value['nonce']
    except (ValueError,TypeError,KeyError):return None

def session_csrf(user,cfg):return hmac.new(bytes.fromhex(cfg['session_key']),('csrf:'+user).encode(),hashlib.sha256).hexdigest()
def login_csrf(cfg):
    body=base64.urlsafe_b64encode(json.dumps({'exp':int(time.time()+600),'nonce':secrets.token_hex(16)}).encode()).decode().rstrip('=')
    return body+'.'+hmac.new(bytes.fromhex(cfg['session_key']),('login:'+body).encode(),hashlib.sha256).hexdigest()
def login_csrf_ok(token,cfg):
    try:
        body,signature=token.split('.',1)
        expected=hmac.new(bytes.fromhex(cfg['session_key']),('login:'+body).encode(),hashlib.sha256).hexdigest()
        value=json.loads(base64.urlsafe_b64decode(body+'='*(-len(body)%4)))
        return hmac.compare_digest(signature,expected) and time.time()<value['exp']<=time.time()+610
    except (ValueError,TypeError,KeyError):return False

def backend(path,body=None,content_type='application/json'):
    headers={'Host':'127.0.0.1:18885','Origin':BACKEND}
    if body is not None:headers['Content-Type']=content_type
    request=Request(BACKEND+path,body,headers)
    try:
        with OPENER.open(request,timeout=160) as response:return response.status,response.read(2*1024*1024),response.headers.get('Content-Type','application/json')
    except HTTPError as response:return response.code,response.read(100000),response.headers.get('Content-Type','application/json')

def complete_job(identity,body):
    try:
        status,raw,_=backend('/chat',body);value=json.loads(raw)
    except Exception:status=503;value={'error':'远程连接没有收到完整回复，请先检查本机测试窗口状态'}
    with LOCK:JOBS[identity].update(state='done',status=status,body=value)

class Handler(BaseHTTPRequestHandler):
    def log_message(self,*args):pass
    def send(self,status,body,kind='application/json; charset=utf-8',headers=None):
        raw=body if isinstance(body,bytes) else (body.encode() if isinstance(body,str) else json.dumps(body,ensure_ascii=False).encode())
        self.send_response(status);self.send_header('Content-Type',kind);self.send_header('Content-Length',str(len(raw)))
        for name,value in {'Cache-Control':'no-store','Referrer-Policy':'no-referrer','X-Content-Type-Options':'nosniff','X-Frame-Options':'DENY',**(headers or {})}.items():self.send_header(name,value)
        self.end_headers()
        try:self.wfile.write(raw)
        except (BrokenPipeError,ConnectionResetError,ConnectionAbortedError):pass
    def valid_host(self,cfg):
        public=urlsplit(cfg.get('public_origin','')).netloc
        return self.headers.get('Host') in (f'127.0.0.1:{PORT}',public) and bool(self.headers.get('Host'))
    def valid_origin(self,cfg):
        origin=self.headers.get('Origin')
        return bool(origin) and origin in (f'http://127.0.0.1:{PORT}',cfg.get('public_origin'))
    def authenticated(self,cfg):
        try:cookie=SimpleCookie(self.headers.get('Cookie',''));return owner(cookie[COOKIE].value,cfg) if COOKIE in cookie else None
        except Exception:return None
    def do_GET(self):
        cfg=config()
        if not self.valid_host(cfg):return self.send(403,{'error':'Host rejected'})
        path=urlsplit(self.path).path
        if path=='/login':
            html=LOGIN.replace('<input name="password"','<input type="hidden" name="login_csrf" value="'+login_csrf(cfg)+'"><input name="password"',1)
            return self.send(200,html,'text/html; charset=utf-8')
        user=self.authenticated(cfg)
        if not user:
            if path.startswith('/remote/') or path=='/health':return self.send(401,{'error':'请重新输入访问口令'})
            return self.send(303,b'',headers={'Location':'/login'})
        if path=='/evaluation':
            report=ROOT/'runtime/voice-preview/eval/系统调试报告.txt'
            body=report.read_text('utf-8') if report.exists() else '报告正在整理'
            page='<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><style>body{background:#101816;color:#e7eeea;font:16px system-ui;margin:20px}pre{white-space:pre-wrap;line-height:1.8}a{color:#b4d1bc}</style><a href="/">返回测试窗口</a><pre>'+html.escape(body)+'</pre>'
            return self.send(200,page,'text/html; charset=utf-8')
        if path.startswith('/remote/jobs/'):
            identity=path.rsplit('/',1)[1]
            with LOCK:job=dict(JOBS[identity]) if identity in JOBS else None
            if not job or job['owner']!=user:return self.send(404,{'error':'Unknown test request'})
            return self.send(200,{k:v for k,v in job.items() if k in ('state','status','body')})
        if path not in GET_PATHS:return self.send(404,{'error':'仅开放独立测试窗口'})
        status,raw,kind=backend(path)
        if path in ('/','/index.html') and status==200:
            text=raw.decode('utf-8')
            import re
            text=re.sub(r'<a href="/slang\.html"[^>]*>.*?</a>','',text)
            text=text.replace('<header>','<div><a href="/evaluation" style="color:#b0cdb8">查看本轮调试报告</a></div><header>',1)
            script=REMOTE_SCRIPT.replace('__SESSION_CSRF__',json.dumps(session_csrf(user,cfg)))
            text=text.replace('</head>',script+'</head>',1)
            raw=text.encode()
        return self.send(status,raw,kind)
    def do_POST(self):
        cfg=config()
        if not self.valid_host(cfg):return self.send(403,{'error':'Host rejected'})
        origin=self.headers.get('Origin')
        if origin and origin!='null' and not self.valid_origin(cfg):return self.send(403,{'error':'Origin rejected'})
        try:
            size=int(self.headers.get('Content-Length','0'))
            if not 0<size<=65536:raise ValueError()
            body=self.rfile.read(size)
        except (ValueError,OSError):return self.send(400,{'error':'Invalid request'})
        path=urlsplit(self.path).path
        if path=='/login':
            try:form=parse_qs(body.decode())
            except (ValueError,UnicodeError):return self.send(400,{'error':'Invalid login form'})
            if not self.valid_origin(cfg) and not login_csrf_ok(form.get('login_csrf',[''])[0],cfg):
                return self.send(403,{'error':'登录页校验已失效，请刷新登录页后重新输入口令'})
            key=self.headers.get('CF-Connecting-IP',self.client_address[0]);now=time.time()
            with LOCK:
                attempts=[t for t in FAILS.get(key,[]) if now-t<300];FAILS[key]=attempts
                if len(attempts)>=5:return self.send(429,'尝试次数较多，请五分钟后重试','text/plain; charset=utf-8')
            password=form.get('password',[''])[0]
            if not password_ok(password,cfg):
                with LOCK:FAILS[key].append(now)
                return self.send(403,'口令不正确，请返回重试','text/plain; charset=utf-8')
            token=session(cfg)
            return self.send(303,b'',headers={'Location':'/','Set-Cookie':COOKIE+'='+token+'; Path=/; Secure; HttpOnly; SameSite=Strict; Max-Age=86400'})
        user=self.authenticated(cfg)
        if not user:return self.send(401,{'error':'请重新输入访问口令'})
        if not self.valid_origin(cfg) and not hmac.compare_digest(self.headers.get('X-Test-CSRF',''),session_csrf(user,cfg)):
            return self.send(403,{'error':'请求校验失效，请刷新测试页后重试'})
        if path=='/logout':
            REVOKED.add(user)
            return self.send(303,b'',headers={'Location':'/login','Set-Cookie':COOKIE+'=; Path=/; Secure; HttpOnly; SameSite=Strict; Max-Age=0'})
        if path=='/remote/chat':
            identity=self.headers.get('X-Test-Request-ID','')
            if len(identity)!=32 or any(c not in '0123456789abcdef' for c in identity):return self.send(400,{'error':'Invalid request identity'})
            digest=hashlib.sha256(body).hexdigest();key=(user,identity);now=time.time()
            with LOCK:
                previous=REQUESTS.get(key)
                if previous:
                    if previous['digest']!=digest:return self.send(409,{'error':'Request identity conflict'})
                    return self.send(202,{'id':previous['job']})
                CHAT_TIMES[:]=[t for t in CHAT_TIMES if now-t<3600]
                if len(CHAT_TIMES)>=40 or sum(now-t<60 for t in CHAT_TIMES)>=6:return self.send(429,{'error':'远程测试请求较多，请稍后再试'})
                for job_id,job in list(JOBS.items()):
                    if now-job['at']>7200:JOBS.pop(job_id,None)
                if sum(job['state']=='pending' for job in JOBS.values())>=1:return self.send(429,{'error':'上一条还在回复，请稍等'})
                job_id=secrets.token_hex(16);JOBS[job_id]={'owner':user,'at':now,'state':'pending'};REQUESTS[key]={'digest':digest,'job':job_id};CHAT_TIMES.append(now)
                if len(REQUESTS)>200:REQUESTS.pop(next(iter(REQUESTS)))
            threading.Thread(target=complete_job,args=(job_id,body),daemon=True).start()
            return self.send(202,{'id':job_id})
        if path not in POST_PATHS:return self.send(404,{'error':'仅开放独立测试操作'})
        if self.headers.get('Content-Type','').split(';')[0]!='application/json':return self.send(415,{'error':'JSON required'})
        status,raw,kind=backend(path,body)
        return self.send(status,raw,kind)

if __name__=='__main__':
    cfg=config();password_ok('',cfg)  # Validate local config before listening.
    ThreadingHTTPServer(('127.0.0.1',PORT),Handler).serve_forever()
