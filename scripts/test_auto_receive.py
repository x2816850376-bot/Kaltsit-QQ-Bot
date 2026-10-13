"""Test real auto-session manager using synthetic endpoints and a nonexistent CLI."""
from pathlib import Path
import asyncio
ROOT=Path(__file__).resolve().parent.parent
text=(ROOT/'scripts/smoke_private_bridge.py').read_text('utf-8')
text=text.replace("str(stage/'local_service.py')", "str(stage/'account_runtime.py')")
text=text.replace("'test_port':port(),'all_groups':True", "'test_port':port(),'codex_path':'synthetic-do-not-run-model.exe','all_groups':True")
text=text.replace("(stage/'runtime/SERVICE_STOP').touch()", "(stage/'runtime/STOP').touch()")
text=text.replace("                sids=[]", '''                for _ in range(60):
                    if clients:break
                    await asyncio.sleep(.1)
                event={'post_type':'message','message_type':'group','self_id':int(ACCOUNT),'group_id':20000003,'message_id':91,'user_id':30000001,'time':int(time.time()),'sender':{'user_id':30000001,'nickname':'合成群友'},'message':[{'type':'text','data':{'text':'凯尔希，在吗'}}]}
                for ws in list(clients):await ws.send(json.dumps(event))
                auto=[]
                for _ in range(60):
                    auto=[s for s in data(await remote.call_tool('list_chat_sessions',{}))['sessions'] if s['conversation_id']==f'{ACCOUNT}:group:20000003']
                    if auto:break
                    await asyncio.sleep(.1)
                assert len(auto)==1 and auto[0]['active']
                context=data(await remote.call_tool('get_chat_session',{'session_id':auto[0]['id']}))
                assert any(m.get('onebot_message_id')=='91' for m in context['context']['messages'])
                assert auto[0]['persona_preset']=='kaltsit_arknights_standard'
                # The automatic worker has an explicitly nonexistent model executable.
                # The MCP packet/transport assertions below do not require an LLM.
                sids=[]''',1)
exec(compile(text,str(ROOT/'scripts/smoke_private_bridge.py'),'exec'),dict(__name__='__main__',__file__=str(ROOT/'scripts/smoke_private_bridge.py')))
