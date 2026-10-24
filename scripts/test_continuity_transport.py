"""Actual fake HTTP/WS/MCP transport of continuity metadata; no model or real QQ."""
from pathlib import Path
ROOT=Path(__file__).resolve().parent.parent
source=(ROOT/'scripts/test_social_transport.py').read_text('utf-8')
before="['在，博士','先把你的阵容发来']"
after="['最初的发掘让许多提卡兹付出了生命，博士','律法带来了共同认知，也带来了分离。阵容调整好后发来']"
source=source.replace("'凯尔希，在吗？测试梗何意味？'","'凯尔希，在吗？我调整阵容，一会发给你。测试梗何意味？'")
marker="                        seeded=data(await proxy.call_tool('send_chat_message',"
assert source.count(marker)==1
source=source.replace(marker,"""                        offered=data(await proxy.call_tool('get_world_knowledge',{'session_id':sids[0],'query':'讲个萨科塔的故事','max_chars':2000}))
                        card=offered['event_card']
                        assert card['id']=='faceless-saints' and len(offered['event_version'])==64
"""+marker)
marker="'slang_candidates':[{'term':'测试梗','meaning':'仅合成测试词义','usage':'合成语境'}]"
assert source.count(marker)==1
source=source.replace(marker,marker+",'continuity_update':{'followups':[{'topic':'阵容','awaiting':'调整后的阵容截图','user_quote':'一会发给你','status':'pending','bubble':1}],'story':{'event_id':card['id'],'version':offered['event_version'],'completed':True,'parts':[{'bubble':0,'fact_ids':['f1']},{'bubble':1,'fact_ids':['f2']}]}}")
source=source.replace(before,after)
marker="                        assert social_data['terms'][0]['status']=='candidate'"
assert source.count(marker)==1
source=source.replace(marker,marker+"""
                        continuity_path=seed_path.parent/'conversation-continuity.private.json'
                        continuity=json.loads(continuity_path.read_text('utf-8'))
                        assert continuity['followups'][0]['speaker_id']=='30000001'
                        assert continuity['stories'][0]['told_fact_ids']==['f1','f2']
                        assert continuity['stories'][0]['completed']
                        bad_story=await proxy.call_tool('send_chat_message',{'session_id':sids[0],'respond_to_event_id':eid,'bubbles':['未发送'],'participation_mode':'direct','idempotency_key':'synthetic-bad-story','continuity_update':{'story':{'event_id':card['id'],'version':offered['event_version'],'completed':True,'parts':[{'bubble':0,'fact_ids':['invented-ending']}]}}})
                        assert bad_story.isError and len(sent)==2
                        print('Continuity passed real synthetic transport: scoped pending exchange, source/version-bound facts, confirmed delivery; invented fact rejected without sending')""")
source=source.replace('exec(compile(text,','text=text.replace('+repr(before)+','+repr(after)+')\nexec(compile(text,')
exec(compile(source,str(ROOT/'scripts/test_social_transport.py'),'exec'),dict(__name__='__main__',__file__=str(ROOT/'scripts/test_social_transport.py')))
