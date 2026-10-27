from pathlib import Path
ROOT=Path(__file__).resolve().parent

def change(name,old,new):
    path=ROOT/name;text=path.read_text('utf-8')
    if text.count(old)!=1:raise ValueError('Unexpected fragment in '+name)
    path.write_text(text.replace(old,new,1),'utf-8')

change('configure.py',"'all_conversations':False,'chat':True", "'all_conversations':config.get('all_groups',False) or config.get('private_chats',False),'chat':True")
change('configure.py',"'account':config['account'],'groups':config['groups']}", "'account':config['account'],'groups':config['groups'],'all_groups':config.get('all_groups',False),'private_chats':config.get('private_chats',False)}")
change('vendor/Tulpa/chatlocal/mcp_chat_media.py',
       "receipt=sender.call('send_group_msg',{'group_id':int(row['conversation_id'].split(':')[-1]),'message':[{'type':'image','data':payload}]},sending=True)",
       "category=row['conversation_id'].split(':')[1]\n                receipt=sender.call('send_group_msg' if category=='group' else 'send_private_msg',{'group_id' if category=='group' else 'user_id':int(row['conversation_id'].split(':')[-1]),'message':[{'type':'image','data':payload}]},sending=True)")

original=(ROOT/'scripts/smoke_fake_bridge.py').read_text('utf-8')
original=original.replace("elif action=='get_group_info':", "elif action=='get_friend_list':data=[{'user_id':30000001,'nickname':'合成好友'}]\n        elif action=='get_friend_msg_history':data={'messages':[]}\n        elif action=='send_private_msg':\n            assert args['user_id']==30000001\n            sent.append(args);data={'message_id':len(sent)+2000}\n        elif action=='get_group_info':",1)
original=original.replace("'test_port':port()}","'test_port':port(),'all_groups':True,'private_chats':True}",1)
original=original.replace("                for sid in sids:data(await remote.call_tool('stop_chat_session',{'session_id':sid}))",'''                private_cid=f'{ACCOUNT}:direct:30000001'
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
                for sid in sids+[private]:data(await remote.call_tool('stop_chat_session',{'session_id':sid}))''',1)
original=original.replace('Simulated OneBot HTTP/WS -> Tulpa MCP -> STDIO:', 'Simulated groups AND private HTTP/WS -> Tulpa MCP -> STDIO:')
(ROOT/'scripts/smoke_private_bridge.py').write_text(original,'utf-8')
print('Private friend transport and isolation regression prepared')
