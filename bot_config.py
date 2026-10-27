"""Portable, validated settings. Importing modules does not connect or send."""
import json
import os
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parent
PRESET = 'kaltsit_arknights_standard'
CONFIG_PATH = Path(os.environ.get('KALTSIT_CONFIG') or ROOT/'config/config.json')


def decimal(value, label):
    if not isinstance(value, str) or not value.isascii() or not value.isdigit() or not 5 <= len(value) <= 16 or int(value) <= 0:
        raise ValueError(label+'必须是5至16位数字字符串')
    return value


def local_url(value, schemes, label):
    p = urlparse(value if isinstance(value,str) else '')
    if p.scheme not in schemes or p.hostname not in ('127.0.0.1','localhost','::1') or p.username or p.password or p.query or p.fragment:
        raise ValueError(label+'必须是本机地址，不能包含密码、查询参数或远程主机')
    try: port=p.port
    except ValueError:raise ValueError(label+'端口无效') from None
    if port is None or not 1024<=port<=65535:raise ValueError(label+'需要1024至65535端口')
    return value.rstrip('/')


def validate(data):
    if not isinstance(data,dict):raise ValueError('配置必须是JSON对象')
    data=dict(data)
    allowed={'account','groups','onebot_http_url','onebot_ws_url','onebot_token','mcp_port','test_port','model','reasoning','fast','max_parallel_groups','codex_path','node_path','all_groups','private_chats'}
    if set(data)-allowed:raise ValueError('存在未知配置字段')
    decimal(data.get('account'),'QQ账号')
    for flag in ('all_groups','private_chats'):
        if type(data.setdefault(flag,False)) is not bool:raise ValueError('Invalid scope flag')
    groups=data.get('groups',[])
    if not isinstance(groups,list) or len(groups)>500 or (not groups and not data['all_groups'] and not data['private_chats']):raise ValueError('Select a conversation scope')
    data['groups']=list(dict.fromkeys(decimal(v,'群号') for v in groups))
    for key,schemes in [('onebot_http_url',('http','https')),('onebot_ws_url',('ws','wss'))]:
        data[key]=local_url(data.get(key),schemes,key)
    if not isinstance(data.get('onebot_token'),str) or not 16<=len(data['onebot_token'])<=200 or any(ord(c)<33 for c in data['onebot_token']):raise ValueError('OneBot Token需为16至200位无空白字符串')
    for key,default in [('mcp_port',18778),('test_port',18883)]:
        value=data.setdefault(key,default)
        if type(value)!=int or not 1024<=value<=65535:raise ValueError('端口无效')
    if data['mcp_port']==data['test_port']:raise ValueError('MCP和测试窗口端口不能相同')
    data.setdefault('model','gpt-6-luna');data.setdefault('reasoning','high');data.setdefault('fast',False)
    if data['model']!='gpt-6-luna':raise ValueError('本发行版固定GPT-6 Luna，不自动切换模型')
    if data['reasoning'] not in ('low','medium','high'):raise ValueError('推理强度需为low/medium/high')
    if type(data['fast'])!=bool:raise ValueError('fast需要布尔值')
    if type(data.setdefault('max_parallel_groups',1))!=int or not 1<=data['max_parallel_groups']<=2:raise ValueError('模型并发只能为1或2')
    for key in ('codex_path','node_path'):
        if not isinstance(data.setdefault(key,''),str):raise ValueError('程序路径必须是字符串')
    return data


def load(required=True):
    if not CONFIG_PATH.exists():
        if required:raise ValueError('请先运行 02-配置机器人.cmd')
        return {}
    return validate(json.loads(CONFIG_PATH.read_text('utf-8-sig')))


def group_id(config=None):
    config=load(False) if config is None else config
    cid=os.environ.get('KALTSIT_CONVERSATION')
    if cid:
        parts=cid.split(':')
        if len(parts)!=3 or parts[0]!=config.get('account') or parts[1] not in ('group','direct'):raise ValueError('Invalid conversation account or kind')
        decimal(parts[2],'Peer')
        if parts[1]=='group' and not config.get('all_groups') and parts[2] not in config.get('groups',[]):raise ValueError('Group not authorized')
        if parts[1]=='direct' and not config.get('private_chats'):raise ValueError('Private chats not authorized')
        return cid
    requested=os.environ.get('KALTSIT_GROUP')
    if not config:
        if requested:raise ValueError('没有已核验配置，不能选择聊天群')
        return '0:group:0'  # Disabled import-only state, never an authorized QQ target.
    requested=requested or (config['groups'][0] if config['groups'] else '0')
    if requested=='0':return f"{config['account']}:group:0"
    if requested not in config['groups']:raise ValueError('此群不在配置的白名单内')
    return f"{config['account']}:group:{requested}"


def runtime_dir():
    _,kind,peer=group_id().split(':')
    return ROOT/'runtime'/(kind+'-'+peer)


def connection():
    data=json.loads((ROOT/'runtime/connection.private.json').read_text('utf-8'))
    expected=load()
    if data.get('account')!=expected['account'] or data.get('groups')!=expected['groups'] or data.get('all_groups',False)!=expected['all_groups'] or data.get('private_chats',False)!=expected['private_chats']:raise ValueError('配置已变化，请重新配置授权，不能沿用旧账号或旧群权限')
    return data
