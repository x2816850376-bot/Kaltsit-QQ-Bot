"""User-operated local setup, verifies account/groups before granting send access."""
import getpass
import json
import secrets
from bot_config import ROOT, CONFIG_PATH, load, validate


def verify_bridge(config):
    from local_service import environment
    environment(config)
    from chatlocal.onebot import Client
    client=Client()
    if client.login()!=config['account']:raise ValueError('OneBot登录的账号与填写账号不同，未授权')
    groups={str(g['group_id']) for g in client.call('get_group_list',{})}
    missing=set(config['groups'])-groups
    if missing:raise ValueError('此QQ不在指定群中：'+','.join(sorted(missing)))


def write_configuration(config):
    # Network verification has no sends. Invalid/account-mismatched configs are not persisted.
    config=validate(config);verify_bridge(config)
    from local_service import create_access
    access=create_access(config)
    result=access.create({'name':'凯尔希群聊机器人','platforms':['qq'],
                         'conversations':[] if config.get('all_groups') or config.get('private_chats') else [['qq',f"{config['account']}:group:{g}"] for g in config['groups']],
                         'all_conversations':config.get('all_groups',False) or config.get('private_chats',False),'chat':True,'send':True,'onebot':True,
                         'chat_images':True,'chat_sticker_send':True,'chat_sticker_collect':False})
    # Revoke old package grants so removing a group/rotating credentials takes effect.
    with access.connect() as db:db.execute('UPDATE grants SET revoked=1 WHERE id<>?',(result['id'],))
    runtime=ROOT/'runtime';runtime.mkdir(exist_ok=True)
    connection={'url':f"http://127.0.0.1:{config['mcp_port']}/mcp",'token':result['token'],
                'account':config['account'],'groups':config['groups'],'all_groups':config.get('all_groups',False),'private_chats':config.get('private_chats',False)}
    (runtime/'connection.private.json').write_text(json.dumps(connection,ensure_ascii=False,indent=2),'utf-8')
    CONFIG_PATH.parent.mkdir(parents=True,exist_ok=True)
    CONFIG_PATH.write_text(json.dumps(config,ensure_ascii=False,indent=2),'utf-8')
    print('已核验QQ账号与群列表。配置和授权仅保存在本机，尚未启动回复。')


def main():
    if (ROOT/'runtime/owner.json').exists():raise ValueError('请先运行停止脚本，再修改账号、群或授权')
    template=json.loads((ROOT/'config/config.example.json').read_text('utf-8'))
    if CONFIG_PATH.exists():template.update(load())
    print('先在NapCat/OneBot中登录自己的QQ，开启HTTP和正向WebSocket，设置同一个Token。')
    template['account']=input('QQ账号：').strip()
    template['groups']=[v.strip() for v in input('群号（多个用英文逗号隔开）：').split(',') if v.strip()]
    for key,label in [('onebot_http_url','HTTP地址'),('onebot_ws_url','正向WebSocket地址')]:
        template[key]=input(f"{label} [{template[key]}]：").strip() or template[key]
    template['onebot_token']=getpass.getpass('OneBot Token（输入不显示）：').strip()
    print('确认将允许机器人在上述群持续收消息、看图和发送消息，不授权群管理或收藏。')
    if input('输入 YES 保存并授权：').strip()!='YES':print('未保存');return
    write_configuration(template)


if __name__=='__main__':
    try:main()
    except Exception as exc:print('配置未完成：'+str(exc));raise SystemExit(1)
