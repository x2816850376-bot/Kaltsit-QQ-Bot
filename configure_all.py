"""Explicit user-requested scope for this new account; never edits an old grant."""
from pathlib import Path
import json
from bot_config import ROOT,validate
from local_service import environment,create_access

def configure():
    config=json.loads((ROOT/'runtime/pending-connection.private.json').read_text('utf-8'))
    config.update(groups=[],codex_path='',node_path='')
    config=validate(config)
    environment(config)
    from chatlocal.onebot import Client
    client=Client(timeout=4)
    if client.login()!=config['account']:raise ValueError('Logged in account does not match current user request')
    groups=client.call('get_group_list',{})
    if not isinstance(groups,list):raise ValueError('Group list invalid')
    access=create_access(config)
    result=access.create(dict(name='凯尔希-全部群与好友私聊-2323968381',platforms=['qq'],
                             all_conversations=True,conversations=[],chat=True,send=True,
                             onebot=True,chat_images=True,chat_sticker_send=True,
                             chat_sticker_collect=False,manage=False))
    credential=dict(url=f"http://127.0.0.1:{config['mcp_port']}/mcp",token=result['token'],
                    grant_id=result['id'],account=config['account'],groups=[],
                    all_groups=True,private_chats=True)
    (ROOT/'config/config.json').write_text(json.dumps(config,ensure_ascii=False,indent=2),'utf-8')
    (ROOT/'runtime/connection.private.json').write_text(json.dumps(credential,ensure_ascii=False,indent=2),'utf-8')
    print(json.dumps(dict(account=config['account'],current_groups=len(groups),
                          scope='all_groups_and_friend_private_chats',model=config['model'],
                          reasoning=config['reasoning'],status='configured_not_replying'),ensure_ascii=False))

if __name__=='__main__':configure()
