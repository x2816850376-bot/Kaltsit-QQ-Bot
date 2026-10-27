"""Real HTTP/WS/MCP/STDIO integration against synthetic OneBot only; no model."""
import asyncio
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import shutil
import socket
import subprocess
import sys
import tempfile
import threading
import time
import httpx
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from mcp.client.streamable_http import streamable_http_client
from websockets.asyncio.server import serve

ROOT=Path(__file__).resolve().parent.parent
ACCOUNT='10000001';GROUPS=['20000001','20000002'];TOKEN='synthetic-test-only'
sent=[];clients=set()

def port():
    with socket.socket() as sock:
        sock.bind(('127.0.0.1',0));return sock.getsockname()[1]

class HTTP(BaseHTTPRequestHandler):
    def log_message(self,*args):pass
    def do_POST(self):
        if self.headers.get('Authorization')!='Bearer '+TOKEN:
            self.send_error(401);return
        args=json.loads(self.rfile.read(int(self.headers['Content-Length'])))
        action=self.path.strip('/')
        if action=='get_login_info':data={'user_id':int(ACCOUNT),'nickname':'合成机器人'}
        elif action=='get_group_list':data=[{'group_id':int(g),'group_name':'合成测试群'} for g in GROUPS]
        elif action=='get_friend_list':data=[{'user_id':30000001,'nickname':'合成好友'}]
        elif action=='get_friend_msg_history':data={'messages':[]}
        elif action=='send_private_msg':
            assert args['user_id']==30000001
            sent.append(args);data={'message_id':len(sent)+2000}
        elif action=='get_group_info':data={'group_id':args['group_id'],'group_name':'合成测试群'}
        elif action=='get_group_member_info':data={'user_id':args['user_id'],'nickname':'测试群友','card':'测试群友'}
        elif action=='get_version_info':data={'app_name':'synthetic-onebot','app_version':'1','protocol_version':'v11'}
        elif action=='get_group_msg_history':data={'messages':[]}
        elif action=='send_group_msg':
            assert str(args['group_id']) in GROUPS
            sent.append(args);data={'message_id':len(sent)+1000}
        else:
            self.send_error(404);return
        raw=json.dumps({'status':'ok','retcode':0,'data':data}).encode()
        self.send_response(200);self.send_header('Content-Type','application/json');self.send_header('Content-Length',str(len(raw)));self.end_headers();self.wfile.write(raw)

async def ws_handler(ws):
    if ws.request.headers.get('Authorization')!='Bearer '+TOKEN:
        await ws.close();return
    clients.add(ws)
    try:
        while True:
            await ws.send(json.dumps({'post_type':'meta_event','meta_event_type':'heartbeat','self_id':int(ACCOUNT),'status':{'online':True,'good':True}}))
            await asyncio.sleep(.2)
    except Exception:pass
    finally:clients.discard(ws)

def data(result):
    if result.isError:raise AssertionError('MCP tool rejected: '+str(result.content)[:500])
    value=result.structuredContent
    return value if isinstance(value,dict) else json.loads(next(p.text for p in result.content if p.type=='text'))

async def check(stage,cfg,env):
    connection=json.loads((stage/'runtime/connection.private.json').read_text('utf-8'))
    async with httpx.AsyncClient(headers={'Authorization':'Bearer '+connection['token']},timeout=15,trust_env=False) as http:
        async with streamable_http_client(connection['url'],http_client=http) as (r,w,_):
            async with ClientSession(r,w) as remote:
                await remote.initialize()
                sids=[]
                for group in GROUPS:
                    result=data(await remote.call_tool('start_chat_session',{'conversation_id':f'{ACCOUNT}:group:{group}','persona_preset':'kaltsit_arknights_standard','participation':'quiet','idempotency_key':'synthetic-start-'+group}))
                    sids.append(result['session']['id'])
                assert len(clients)==1
                params=StdioServerParameters(command=sys.executable,args=[str(stage/'mcp-stdio-proxy.py')],cwd=str(stage),env=dict(env,KALTSIT_GROUP=GROUPS[0]))
                async with stdio_client(params) as (pr,pw):
                    async with ClientSession(pr,pw) as proxy:
                        await proxy.initialize()
                        tools={t.name for t in (await proxy.list_tools()).tools}
                        assert 'send_chat_message' in tools and 'get_world_knowledge' in tools and 'get_canonical_knowledge' in tools and 'read_file_chunks' not in tools
                        assert (await proxy.call_tool('get_chat_session',{'session_id':sids[1]})).isError
                        data(await proxy.call_tool('get_chat_session',{'session_id':sids[0]}))
                        event={'post_type':'message','message_type':'group','self_id':int(ACCOUNT),'group_id':int(GROUPS[0]),'message_id':101,'user_id':30000001,'time':int(time.time()),'sender':{'user_id':30000001,'nickname':'测试群友'},'message':[{'type':'at','data':{'qq':ACCOUNT}},{'type':'text','data':{'text':'凯尔希，在吗？'}}]}
                        for ws in list(clients):await ws.send(json.dumps(event))
                        packet=data(await proxy.call_tool('wait_chat_messages',{'session_id':sids[0],'timeout_seconds':3,'quiet_seconds':0,'limit':15}))
                        messages=[m for m in packet['messages'] if not m.get('is_self')]
                        assert len(messages)==1 and '在吗' in messages[0]['content']
                        evidence=data(await proxy.call_tool('get_world_knowledge',{'session_id':sids[0],'query':'讲个萨科塔的故事','max_chars':1600}))
                        assert evidence['status']=='ok' and evidence['mode']=='documented_story'
                        canonical=data(await proxy.call_tool('get_canonical_knowledge',{'session_id':sids[0],'query':'任命助理','max_chars':500}))
                        assert canonical['status']=='ok' and sum(len(p['excerpt']) for p in canonical['passages'])<=500
                        assert (await proxy.call_tool('get_canonical_knowledge',{'session_id':sids[1],'query':'任命助理'})).isError
                        assert (await proxy.call_tool('get_canonical_knowledge',{'session_id':sids[0],'query':'任命助理','path':'auth.json'})).isError
                        send={'session_id':sids[0],'respond_to_event_id':messages[0]['id'],'bubbles':['在，博士','先把你的阵容发来'],'participation_mode':'direct','idempotency_key':'synthetic-bubbles-one'}
                        receipt=data(await proxy.call_tool('send_chat_message',send))
                        assert receipt['state']=='SUCCEEDED' and receipt['sent_parts']==2
                        count=len(sent)
                        again=data(await proxy.call_tool('send_chat_message',send))
                        assert again['state']=='SUCCEEDED' and len(sent)==count==2
                        first=sent[0]['message'];assert any(s['type']=='at' and s['data']['qq']=='30000001' for s in first)
                        assert next(s['data']['text'] for s in first if s['type']=='text').startswith(' ')
                        assert all(s['type']!='at' for s in sent[1]['message'])
                other=data(await remote.call_tool('get_chat_session',{'session_id':sids[1]}))
                assert not other.get('context',{}).get('messages')
                private_cid=f'{ACCOUNT}:direct:30000001'
                private=data(await remote.call_tool('start_chat_session',{'conversation_id':private_cid,'persona_preset':'kaltsit_arknights_standard','participation':'quiet','idempotency_key':'private-synthetic-start'}))['session']['id']
                params=StdioServerParameters(command=sys.executable,args=[str(stage/'mcp-stdio-proxy.py')],cwd=str(stage),env=dict(env,KALTSIT_CONVERSATION=private_cid))
                async with stdio_client(params) as (pr,pw):
                    async with ClientSession(pr,pw) as proxy:
                        await proxy.initialize()
                        assert (await proxy.call_tool('get_chat_session',{'session_id':sids[0]})).isError
                        data(await proxy.call_tool('get_chat_session',{'session_id':private}))
                        event={'post_type':'message','message_type':'private','self_id':int(ACCOUNT),'message_id':201,'user_id':30000001,'time':int(time.time()),'sender':{'user_id':30000001,'nickname':'合成好友'},'message':[{'type':'text','data':{'text':'在吗'}}]}
                        for ws in list(clients):await ws.send(json.dumps(event))
                        packet=data(await proxy.call_tool('wait_chat_messages',{'session_id':private,'timeout_seconds':3,'quiet_seconds':0}))
                        rows=[r for r in packet['messages'] if not r.get('is_self')]
                        assert len(rows)==1 and rows[0]['conversation_id']==private_cid
                        assert rows[0]['reply_routing']['address_evidence']=='private_to_bot'
                        send={'session_id':private,'respond_to_event_id':rows[0]['id'],'bubbles':['在，博士'],'participation_mode':'direct','idempotency_key':'private-synthetic-send'}
                        receipt=data(await proxy.call_tool('send_chat_message',send))
                        assert receipt['state']=='SUCCEEDED' and receipt['sent_parts']==1
                        assert sent[-1]['user_id']==30000001 and 'group_id' not in sent[-1]
                        assert all(s['type']!='at' for s in sent[-1]['message'])
                        count=len(sent)
                        data(await proxy.call_tool('send_chat_message',send))
                        assert len(sent)==count
                        state=data(await proxy.call_tool('get_chat_session',{'session_id':private}))
                        assert any(r.get('is_self') for r in state['context']['messages'])
                for sid in sids+[private]:data(await remote.call_tool('stop_chat_session',{'session_id':sid}))
                assert (data(await remote.call_tool('get_chat_session',{'session_id':sids[0]})))['session']['active'] is False

async def main():
    http=ThreadingHTTPServer(('127.0.0.1',0),HTTP)
    thread=threading.Thread(target=http.serve_forever,daemon=True);thread.start()
    try:
        async with serve(ws_handler,'127.0.0.1',0) as ws_server:
            ws_port=ws_server.sockets[0].getsockname()[1]
            with tempfile.TemporaryDirectory(prefix='kaltsit-fake-onebot-') as temp:
                stage=Path(temp)/'source'
                shutil.copytree(ROOT,stage,ignore=shutil.ignore_patterns('__pycache__','.venv','.semantic-venv','runtime','private-knowledge','data','.tmp','.cache','imports','.git'))
                cfg={'account':ACCOUNT,'groups':GROUPS,'onebot_http_url':f'http://127.0.0.1:{http.server_port}','onebot_ws_url':f'ws://127.0.0.1:{ws_port}','onebot_token':TOKEN,'mcp_port':port(),'test_port':port(),'all_groups':True,'private_chats':True}
                config=stage/'config/config.json';config.write_text(json.dumps(cfg),'utf-8')
                env=dict(os.environ,KALTSIT_CONFIG=str(config),KALTSIT_GROUP=GROUPS[0],PYTHONUTF8='1',PYTHONIOENCODING='utf-8')
                result=await asyncio.to_thread(subprocess.run,[sys.executable,'-c','from configure import write_configuration; from bot_config import load; write_configuration(load())'],cwd=stage,env=env,capture_output=True,timeout=20)
                assert result.returncode==0,result.stderr.decode('utf-8','replace')
                with (Path(temp)/'service.log').open('wb') as log:
                    process=subprocess.Popen([sys.executable,str(stage/'local_service.py')],cwd=stage,env=env,stdout=log,stderr=log,shell=False,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
                    try:
                        for _ in range(100):
                            assert process.poll() is None,(Path(temp)/'service.log').read_text('utf-8',errors='replace')[-1200:]
                            try:
                                with socket.create_connection(('127.0.0.1',cfg['mcp_port']),timeout=.1):break
                            except OSError:await asyncio.sleep(.1)
                        else:raise AssertionError('MCP startup timeout')
                        await check(stage,cfg,env)
                    finally:
                        (stage/'runtime/SERVICE_STOP').touch()
                        try:await asyncio.to_thread(process.wait,timeout=10)
                        except subprocess.TimeoutExpired:process.terminate();await asyncio.to_thread(process.wait,timeout=5)
        print('Simulated groups AND private HTTP/WS -> Tulpa MCP -> STDIO: receive, group isolation, knowledge, bubbles, native @ spacing, idempotency, stop all passed. No Codex/model/real QQ used.')
    finally:http.shutdown();http.server_close()

if __name__=='__main__':asyncio.run(main())
