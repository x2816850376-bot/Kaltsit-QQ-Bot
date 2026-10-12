"""Package-owned supervisor; no account switching or global process killing."""
import argparse
import asyncio
import importlib.util
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import time
from bot_config import ROOT, load, connection

FLAGS=getattr(subprocess,'CREATE_NO_WINDOW',0)


def free_port(port):
    with socket.socket() as sock:
        try:sock.bind(('127.0.0.1',port))
        except OSError:raise ValueError(f'端口{port}已占用；请修改源码包的配置，不会停止其他程序') from None


def spawn(name,script,env):
    directory=ROOT/'runtime';directory.mkdir(exist_ok=True)
    with (directory/f'{name}.stdout.log').open('ab') as out,(directory/f'{name}.stderr.log').open('ab') as err:
        return subprocess.Popen([sys.executable,str(ROOT/script)],cwd=ROOT,env=env,
                                stdout=out,stderr=err,shell=False,creationflags=FLAGS)


async def stop_sessions():
    import httpx
    from mcp import ClientSession
    from mcp.client.streamable_http import streamable_http_client
    cfg=load();conn=connection()
    async with httpx.AsyncClient(headers={'Authorization':'Bearer '+conn['token']},timeout=12,trust_env=False) as http:
        async with streamable_http_client(conn['url'],http_client=http) as (r,w,_):
            async with ClientSession(r,w) as client:
                await client.initialize()
                result=await client.call_tool('list_chat_sessions',{})
                data=result.structuredContent
                if not isinstance(data,dict):data=json.loads(next(x.text for x in result.content if x.type=='text'))
                allowed={f"{cfg['account']}:group:{g}" for g in cfg['groups']}
                for row in data.get('sessions',[]):
                    if row.get('active') and row.get('conversation_id') in allowed:
                        await client.call_tool('stop_chat_session',{'session_id':row['id']})


def supervise():
    cfg=load();connection()
    directory=ROOT/'runtime';directory.mkdir(exist_ok=True)
    owner=directory/'owner.json'
    # Exclusive file creation blocks a second supervisor without trusting a stale PID.
    with owner.open('x',encoding='utf-8') as file:json.dump({'pid':os.getpid(),'started':time.time()},file)
    processes=[]
    try:
        free_port(cfg['mcp_port'])
        for marker in ('STOP','SERVICE_STOP','SHUTDOWN'):(directory/marker).unlink(missing_ok=True)
        env=dict(os.environ,PYTHONUTF8='1',PYTHONIOENCODING='utf-8')
        service=spawn('service','local_service.py',env);processes.append(service)
        import httpx
        for attempt in range(100):
            if service.poll() is not None:raise ValueError('本地服务启动失败，请查看 runtime/service.stderr.log')
            try:
                # Any HTTP response means the socket is serving. The authenticated worker
                # then performs SDK initialization before processing any QQ message.
                httpx.get(connection()['url'],timeout=.5,trust_env=False);break
            except httpx.HTTPError:time.sleep(.1)
        else:raise ValueError('本地服务启动超时')
        workers=[]
        for group in cfg['groups']:
            p=spawn('group-'+group,'luna-chat-runtime.py',dict(env,KALTSIT_GROUP=group));processes.append(p);workers.append(p)
        (directory/'supervisor-state.json').write_text(json.dumps({'status':'running','groups':cfg['groups'],'pid':os.getpid()},ensure_ascii=False),'utf-8')
        while not (directory/'SHUTDOWN').exists():
            if service.poll() is not None:raise ValueError('本地服务意外退出，群聊已停止')
            if all(p.poll() is not None for p in workers):
                print('所有群Worker已退出。请检查状态；可能是模型额度不足，未切换模型。');break
            time.sleep(.5)
    finally:
        (directory/'STOP').touch()
        try:asyncio.run(stop_sessions())
        except Exception:pass
        (directory/'SERVICE_STOP').touch()
        for p in reversed(processes):
            try:p.wait(timeout=15)
            except subprocess.TimeoutExpired:p.terminate();p.wait(timeout=5)
        owner.unlink(missing_ok=True)
        (directory/'supervisor-state.json').write_text('{"status":"stopped"}','utf-8')


def main():
    parser=argparse.ArgumentParser();parser.add_argument('action',choices=['start','stop','pause','status','supervise','test'])
    action=parser.parse_args().action
    if action=='supervise':supervise();return
    cfg=load();directory=ROOT/'runtime';directory.mkdir(exist_ok=True)
    if action in ('stop','pause'):
        (directory/'STOP').touch()
        try:asyncio.run(stop_sessions())
        except Exception:print('本地服务未连接；已设置停止标记。')
        if action=='stop':(directory/'SHUTDOWN').touch()
        print('已请求暂停回复' if action=='pause' else '已请求停止机器人；QQ不退出，记忆保留');return
    if action=='status':
        for file in sorted(directory.glob('group-*/state.json')):
            data=json.loads(file.read_text('utf-8'));print(file.parent.name,data.get('status'),data.get('model'),data.get('reasoning'))
        return
    if action=='start':
        if (directory/'owner.json').exists():raise ValueError('已有后台或未清理的状态文件。先停止并查看状态；不按PID盲杀其他进程')
        free_port(cfg['mcp_port']);connection()
        env=dict(os.environ,PYTHONUTF8='1',PYTHONIOENCODING='utf-8')
        with (directory/'supervisor.log').open('ab') as log:
            subprocess.Popen([sys.executable,str(ROOT/'control.py'),'supervise'],cwd=ROOT,env=env,
                             stdout=log,stderr=log,shell=False,creationflags=FLAGS)
        time.sleep(1)
        print('后台启动请求已提交。用 05-查看状态.cmd 检查实际状态；关闭此窗口不会停止后台。');return
    if action=='test':
        free_port(cfg['test_port'])
        spawn('test-window','dialogue-test-window/server.py',dict(os.environ,PYTHONUTF8='1',PYTHONIOENCODING='utf-8'))
        import webbrowser
        webbrowser.open(f"http://127.0.0.1:{cfg['test_port']}/")


if __name__=='__main__':
    try:main()
    except Exception as exc:print('操作未完成：'+str(exc));raise SystemExit(1)
