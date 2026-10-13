"""One receiver and lazy conversation workers, with isolated data and bounded CPU/LLM."""
import hashlib
import json
import os
import subprocess
import sys
import threading
import time
from bot_config import ROOT,load,connection
from local_service import environment,create_access

RUNTIME=ROOT/'runtime'
FLAGS=getattr(subprocess,'CREATE_NO_WINDOW',0)
STOP=RUNTIME/'STOP'

def write_state(**values):
    config=load()
    values.update(account=config['account'],model=config['model'],reasoning=config['reasoning'],
                  pid=os.getpid(),updated=time.time())
    path=RUNTIME/'account-state.json'
    temporary=path.with_suffix('.pending')
    temporary.write_text(json.dumps(values,ensure_ascii=False,indent=2),'utf-8')
    temporary.replace(path)

def main():
    cfg=load();credential=connection();environment(cfg)
    owner=RUNTIME/'account-owner.json'
    with owner.open('x',encoding='utf-8') as handle:
        json.dump({'pid':os.getpid(),'account':cfg['account']},handle)
    access=create_access(cfg)
    grant=access.authorize(credential['token'],source=False)
    if grant['scope'].get('chat_account')!=cfg['account']:
        raise ValueError('Authorization does not match configured account')
    from chatlocal.mcp_server import MCPService
    from chatlocal.onebot import Client
    if Client(timeout=3).login()!=cfg['account']:raise ValueError('Actual QQ account changed')
    service=MCPService(access)
    chat=service.tools.chat
    base_receive=chat.receive
    counters=dict(received_events=0,ignored_events=0,session_failures=0)

    def receive(event):
        if STOP.exists() or event.get('post_type') not in ('message','message_sent'):return
        if str(event.get('self_id',''))!=cfg['account']:return
        kind=event.get('message_type')
        if kind not in ('group','private'):return
        uid=str(event.get('user_id',''))
        if kind=='private' and uid==cfg['account'] and not event.get('target_id'):return
        peer=str(event.get('group_id','')) if kind=='group' else str(event.get('target_id') if uid==cfg['account'] else uid)
        if not peer.isascii() or not peer.isdigit() or not 0<int(peer)<10**16:return
        if kind=='group' and not cfg['all_groups'] and peer not in cfg['groups']:return
        if kind=='private' and not cfg['private_chats']:return
        cid=f"{cfg['account']}:{'group' if kind=='group' else 'direct'}:{peer}"
        with access.connect() as db:
            row=db.execute('SELECT id FROM chat_sessions WHERE conversation_id=? AND active=1',(cid,)).fetchone()
        if not row:
            if uid==cfg['account']:return
            source=event.get('message')
            if not source:return
            try:
                catalog=chat.call(grant,'list_chat_personas',{},threading.Event())
                if not any(p.get('id')=='kaltsit_arknights_standard' for p in catalog.get('personas',[])):
                    raise ValueError('Persona missing')
                chat.start(grant,dict(conversation_id=cid,persona_preset='kaltsit_arknights_standard',
                           participation='quiet',idempotency_key='auto-'+hashlib.sha256(cid.encode()).hexdigest()[:32]+'-'+str(time.time_ns())),threading.Event())
            except Exception:
                counters['session_failures']+=1
                return
        base_receive(event)
        counters['received_events']+=1

    chat.receiver.on_event=receive
    service.start()
    if not service.status()['running']:raise ValueError('Account MCP failed to start')
    chat.receiver.start()
    children={};paused=False;last_write=0
    try:
        while not STOP.exists():
            for cid,child in list(children.items()):
                if child.poll() is None:continue
                _,kind,peer=cid.split(':')
                try:state=json.loads((RUNTIME/(kind+'-'+peer)/'state.json').read_text('utf-8'))
                except (OSError,ValueError):state={}
                if state.get('status')=='low_power' and state.get('reason') in ('model_unavailable_or_quota','runtime_failure'):
                    paused=True
                children.pop(cid)
            if not paused and chat.receiver.status()['state']=='connected':
                with access.connect() as db:
                    pending=db.execute('''SELECT DISTINCT s.id,s.conversation_id FROM chat_sessions s JOIN chat_inbox i
                                          ON i.session_id=s.id WHERE s.active=1 AND s.grant_id=? AND i.id>s.cursor
                                          ORDER BY s.updated LIMIT 32''',(grant['id'],)).fetchall()
                for row in pending:
                    cid=row['conversation_id']
                    if cid in children or len(children)>=4:continue
                    _,kind,peer=cid.split(':')
                    folder=RUNTIME/(kind+'-'+peer);folder.mkdir(exist_ok=True)
                    env=dict(os.environ,PYTHONUTF8='1',PYTHONIOENCODING='utf-8',KALTSIT_CONVERSATION=cid,KALTSIT_SESSION_ID=row['id'])
                    with (folder/'worker.stdout.log').open('ab') as out,(folder/'worker.stderr.log').open('ab') as err:
                        children[cid]=subprocess.Popen([sys.executable,str(ROOT/'luna-chat-runtime.py')],
                            cwd=ROOT,env=env,stdout=out,stderr=err,shell=False,creationflags=FLAGS)
            if time.monotonic()-last_write>2:
                write_state(status='low_power' if paused else 'listening',
                            receiver=chat.receiver.status(),active_workers=len(children),
                            all_groups=cfg['all_groups'],private_chats=cfg['private_chats'],**counters)
                last_write=time.monotonic()
            time.sleep(.3)
    finally:
        STOP.touch()
        for child in children.values():
            try:child.wait(timeout=12)
            except subprocess.TimeoutExpired:child.terminate();child.wait(timeout=5)
        service.stop()
        write_state(status='stopped',active_workers=0,**counters)
        owner.unlink(missing_ok=True)

if __name__=='__main__':
    try:main()
    except FileExistsError:
        print('Account runtime already owned; no second receiver started')
    except Exception as exc:
        write_state(status='blocked',error_type=type(exc).__name__)
        raise
    finally:
        owner=RUNTIME/'account-owner.json'
        try:
            if json.loads(owner.read_text('utf-8')).get('pid')==os.getpid():owner.unlink()
        except (OSError,ValueError):pass
