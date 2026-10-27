"""Account-isolated migration; original live install and published source stay intact."""
from pathlib import Path
ROOT=Path(__file__).resolve().parent

def edit(name, changes):
    file=ROOT/name
    text=file.read_text('utf-8')
    backup=ROOT/'runtime/source-baseline'/name
    backup.parent.mkdir(parents=True,exist_ok=True)
    if backup.exists():raise ValueError('Migration already attempted: '+name)
    backup.write_text(text,'utf-8')
    for old,new in changes:
        if text.count(old)!=1:raise ValueError('Unexpected source fragment: '+name+' '+old[:70])
        text=text.replace(old,new,1)
    file.write_text(text,'utf-8')

edit('bot_config.py',[
    ("'node_path'}", "'node_path','all_groups','private_chats'}"),
    ("    groups=data.get('groups')\n    if not isinstance(groups,list) or not 1<=len(groups)<=8:raise ValueError('请选择1至8个群号')",
     "    for flag in ('all_groups','private_chats'):\n        if type(data.setdefault(flag,False)) is not bool:raise ValueError('Invalid scope flag')\n    groups=data.get('groups',[])\n    if not isinstance(groups,list) or len(groups)>500 or (not groups and not data['all_groups'] and not data['private_chats']):raise ValueError('Select a conversation scope')"),
    ("    requested=os.environ.get('KALTSIT_GROUP')", "    cid=os.environ.get('KALTSIT_CONVERSATION')\n    if cid:\n        parts=cid.split(':')\n        if len(parts)!=3 or parts[0]!=config.get('account') or parts[1] not in ('group','direct'):raise ValueError('Invalid conversation account or kind')\n        decimal(parts[2],'Peer')\n        if parts[1]=='group' and not config.get('all_groups') and parts[2] not in config.get('groups',[]):raise ValueError('Group not authorized')\n        if parts[1]=='direct' and not config.get('private_chats'):raise ValueError('Private chats not authorized')\n        return cid\n    requested=os.environ.get('KALTSIT_GROUP')"),
    ("requested=requested or config['groups'][0]", "requested=requested or (config['groups'][0] if config['groups'] else '0')\n    if requested=='0':return f\"{config['account']}:group:0\""),
    ("    scope=group_id().split(':')[-1]\n    return ROOT/'runtime'/('group-'+scope)", "    _,kind,peer=group_id().split(':')\n    return ROOT/'runtime'/(kind+'-'+peer)"),
    ("data.get('groups')!=expected['groups']", "data.get('groups')!=expected['groups'] or data.get('all_groups',False)!=expected['all_groups'] or data.get('private_chats',False)!=expected['private_chats']")
])
edit('cli_config.py',[("'KALTSIT_GROUP':group_id().split(':')[-1]", "'KALTSIT_CONVERSATION':group_id()")])
edit('chat_context.py',[("        elif account in ats:address='explicit_at_bot'", "        elif GROUP.split(':')[1]=='direct':address='private_to_bot'\n        elif account in ats:address='explicit_at_bot'")])
edit('chat_participation.py',[("if evidence in ('explicit_at_bot', 'reply_to_bot'):", "if evidence in ('explicit_at_bot', 'reply_to_bot', 'private_to_bot'):")])
edit('chat_address.py',[("        return dict(enabled=enabled, required=False, recommended=recommended, recipient=recipient,", "        if GROUP.split(':')[1]=='direct':\n            mention_required=mention_recommended=False\n        return dict(enabled=enabled, required=False, recommended=recommended, recipient=recipient,")])
edit('vendor/Tulpa/chatlocal/mcp_chat.py',[
    ("category != 'group'", "category not in ('group','direct')"),
    ("event.get('message_type')!='group'", "event.get('message_type') not in ('group','private')"),
    ("        account, group = str(event.get('self_id','')), str(event.get('group_id',''))", "        account=str(event.get('self_id',''))\n        category='group' if event.get('message_type')=='group' else 'direct'\n        group=str(event.get('group_id','')) if category=='group' else str(event.get('target_id') if str(event.get('user_id',''))==account else event.get('user_id',''))"),
    ("        cid = f'{account}:group:{group}'", "        cid = f'{account}:{category}:{group}'"),
    ("        if qq_address(target)[1]!='group':raise ValueError('持续聊天目前只支持 QQ 群。')", "        if qq_address(target)[1] not in ('group','direct'):raise ValueError('Unsupported conversation')"),
    ("        if address['kind']!='group':raise ValueError('目标不是 QQ 群。')", "        if address['kind'] not in ('group','direct'):raise ValueError('Unsupported conversation')"),
    ("if db.execute('SELECT count(*) FROM chat_sessions WHERE active=1').fetchone()[0]>=8:", "if db.execute('SELECT count(*) FROM chat_sessions WHERE active=1').fetchone()[0]>=512:"),
    ("            send_args['mention_user_id']=uid", "            if row['conversation_id'].split(':')[1]=='group':send_args['mention_user_id']=uid"),
    ("receipt=result['result'];account,_,group=row['conversation_id'].split(':')", "receipt=result['result'];account,category,group=row['conversation_id'].split(':')"),
    ("self.receive(dict(post_type='message_sent',message_type='group',self_id=account,group_id=group,", "self.receive(dict(post_type='message_sent',message_type='group' if category=='group' else 'private',self_id=account,group_id=group,target_id=group,")
])
edit('luna-chat-runtime.py',[
    ("                groups=payload(await client.call_tool('list_chat_groups',{}))\n                if group_id() not in json.dumps(groups):\n                    raise RuntimeError('Target group not authorized')", "                # Scope, actual account and target membership are checked by backend.start.\n                # No first-page group-list check: private chats and >100 groups are supported."),
    ("    total_starts=0;acknowledge=None", "    total_starts=0;acknowledge=None\n    last_activity=time.monotonic()"),
    ("        action=input_wait_action(incoming)", "        action=input_wait_action(incoming)\n        if action=='idle' and time.monotonic()-last_activity>45:\n            state(status='idle',session_id=sid,runtime_starts=total_starts,waiting_without_model=True);return\n        if action=='ready':\n            last_activity=time.monotonic()\n            from conversation_decision import needs_generation\n            if not needs_generation(incoming,WORK_ROOT):\n                acknowledge=incoming.get('read_through_id');continue")
])
print('Scoped group/private migration completed in new account instance only')
