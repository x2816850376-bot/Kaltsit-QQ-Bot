"""Full fake transport: send from prefetched packet without model get/wait."""
from pathlib import Path
ROOT=Path(__file__).resolve().parent.parent
text=(ROOT/'scripts/smoke_private_bridge.py').read_text('utf-8')
marker="                params=StdioServerParameters(command=sys.executable,args=[str(stage/'mcp-stdio-proxy.py')],cwd=str(stage),env=dict(env,KALTSIT_GROUP=GROUPS[0]))"
assert text.count(marker)==1
replacement='''                event={'post_type':'message','message_type':'group','self_id':int(ACCOUNT),'group_id':int(GROUPS[0]),'message_id':101,'user_id':30000001,'time':int(time.time()),'sender':{'user_id':30000001,'nickname':'测试群友'},'message':[{'type':'at','data':{'qq':ACCOUNT}},{'type':'text','data':{'text':'凯尔希，在吗？'}}]}
                for ws in list(clients):await ws.send(json.dumps(event))
                incoming=data(await remote.call_tool('wait_chat_messages',{'session_id':sids[0],'timeout_seconds':3,'quiet_seconds':0,'limit':15}))
                snapshot=data(await remote.call_tool('get_chat_session',{'session_id':sids[0]}))
                snapshot.update({k:incoming[k] for k in ('messages','session_id','read_through_id')})
                seed_path=stage/'runtime'/('group-'+GROUPS[0])/'model-seed.private.json'
                seed_path.parent.mkdir(exist_ok=True)
                seed_path.write_text(json.dumps(snapshot,ensure_ascii=False),'utf-8')
                eid=next(r['id'] for r in incoming['messages'] if not r.get('is_self'))
                params=StdioServerParameters(command=sys.executable,args=[str(stage/'mcp-stdio-proxy.py')],cwd=str(stage),env=dict(env,KALTSIT_GROUP=GROUPS[0],KALTSIT_SEED_PACKET_FILE=str(seed_path),KALTSIT_REPLY_IDS=json.dumps([eid])))'''
text=text.replace(marker,replacement)
marker="                        assert 'send_chat_message' in tools and 'get_world_knowledge' in tools and 'get_canonical_knowledge' in tools and 'read_file_chunks' not in tools"
text=text.replace(marker,marker+'''
                        # No model-visible get_chat_session or wait call before this send.
                        seeded=data(await proxy.call_tool('send_chat_message',{'session_id':sids[0],'respond_to_event_id':eid,'bubbles':['在，博士','先把你的阵容发来'],'participation_mode':'direct','idempotency_key':'synthetic-bubbles-one'}))
                        assert seeded['state']=='SUCCEEDED' and len(sent)==2
                        print('Prefetched packet -> bound bubbles send passed without model get/wait')''')
exec(compile(text,str(ROOT/'scripts/smoke_private_bridge.py'),'exec'),dict(__name__='__main__',__file__=str(ROOT/'scripts/smoke_private_bridge.py')))
