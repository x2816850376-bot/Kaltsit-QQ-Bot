"""One real Luna generation, synthetic QQ HTTP/WS only, production worker path."""
from pathlib import Path
import shutil
ROOT=Path(__file__).resolve().parent.parent
text=(ROOT/'scripts/smoke_private_bridge.py').read_text('utf-8')
begin=text.index('async def check(');end=text.index('async def main():',begin)
check='''async def check(stage,cfg,env):
    until=time.monotonic()+10
    while not clients and time.monotonic()<until:await asyncio.sleep(.1)
    assert clients,'Synthetic receiver did not connect'
    started=time.monotonic()
    event={'post_type':'message','message_type':'group','self_id':int(ACCOUNT),'group_id':int(GROUPS[0]),'message_id':101,'user_id':30000001,'time':int(time.time()),'sender':{'user_id':30000001,'nickname':'测试博士'},'message':[{'type':'at','data':{'qq':ACCOUNT}},{'type':'text','data':{'text':'下午好凯尔希'}}]}
    for ws in list(clients):await ws.send(json.dumps(event))
    deadline=time.monotonic()+100
    first=None
    while time.monotonic()<deadline:
        if sent and first is None:first=round(time.monotonic()-started,3)
        folder=stage/'runtime'/('group-'+GROUPS[0])
        state_file=folder/'state.json'
        if state_file.exists():
            state=json.loads(state_file.read_text('utf-8'))
            if state.get('status')=='low_power':raise AssertionError('Actual model unavailable: '+state.get('reason',''))
        events=[]
        for file in (folder/'logs').glob('*.jsonl'):
            for line in file.read_text('utf-8',errors='replace').splitlines():
                try:events.append(json.loads(line))
                except ValueError:pass
        if first is not None and any(e.get('type')=='turn.completed' for e in events):break
        await asyncio.sleep(.2)
    else:
        backup=ROOT/'runtime/diagnostics/prefetched-failure';backup.mkdir(parents=True,exist_ok=True)
        for log in (folder/'logs').glob('*'):
            if log.is_file():shutil.copyfile(log,backup/log.name)
        if state_file.exists():shutil.copyfile(state_file,backup/'state.json')
        raise AssertionError('Synthetic real-model response timed out')
    calls=[e['item'].get('tool') for e in events if e.get('type')=='item.started' and e.get('item',{}).get('type')=='mcp_tool_call']
    assert 'get_chat_session' not in calls and 'wait_chat_messages' not in calls,calls
    assert 'send_chat_message' in calls and str(sent[0].get('group_id'))==GROUPS[0]
    result={'first_reply_seconds':first,'model_calls':calls,'reasoning':'high','real_qq_messages_sent':0,'reply':''.join(s['data'].get('text','') for s in sent[0]['message'] if s['type']=='text')}
    report=ROOT/'runtime/diagnostics/prefetched-greeting.json';report.parent.mkdir(exist_ok=True)
    report.write_text(json.dumps(result,ensure_ascii=False,indent=2),'utf-8')
    print(json.dumps(result,ensure_ascii=False),flush=True)

'''
text=text[:begin]+check+text[end:]
text=text.replace("str(stage/'local_service.py')","str(stage/'account_runtime.py')")
text=text.replace("'test_port':port(),'all_groups':True", "'test_port':port(),'codex_path':"+repr(shutil.which('codex.exe'))+",'all_groups':True")
text=text.replace("(stage/'runtime/SERVICE_STOP').touch()", "(stage/'runtime/STOP').touch()")
text=text.replace("print('Simulated groups AND private HTTP/WS -> Tulpa MCP -> STDIO: receive, group isolation, knowledge, bubbles, native @ spacing, idempotency, stop all passed. No Codex/model/real QQ used.')", "print('Real Luna production-worker test completed on synthetic QQ transport only.')")
exec(compile(text,str(ROOT/'scripts/smoke_private_bridge.py'),'exec'),dict(__name__='__main__',__file__=str(ROOT/'scripts/smoke_private_bridge.py')))
