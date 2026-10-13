"""Own receiver/worker supervisor; never switches QQ or kills other apps."""
import argparse
import json
import os
import socket
import subprocess
import sys
import time
from bot_config import ROOT,load,connection

FLAGS=getattr(subprocess,'CREATE_NO_WINDOW',0)

def free_port(port):
    with socket.socket() as sock:
        try:sock.bind(('127.0.0.1',port))
        except OSError:raise ValueError(f'端口{port}已占用；请修改本副本配置，不会停止其他程序') from None

def spawn(name,script,env):
    directory=ROOT/'runtime';directory.mkdir(exist_ok=True)
    with (directory/f'{name}.stdout.log').open('ab') as out,(directory/f'{name}.stderr.log').open('ab') as err:
        return subprocess.Popen([sys.executable,str(ROOT/script)],cwd=ROOT,env=env,
                                stdout=out,stderr=err,shell=False,creationflags=FLAGS)

def main():
    parser=argparse.ArgumentParser();parser.add_argument('action',choices=['start','stop','pause','status','supervise','test'])
    action=parser.parse_args().action
    cfg=load();directory=ROOT/'runtime';directory.mkdir(exist_ok=True)
    if action=='supervise':
        from account_runtime import main as supervise
        supervise();return
    if action in ('stop','pause'):
        (directory/'STOP').touch()
        print('已请求停止本副本回复；后台会取消待发送内容，QQ保持登录，记忆保留')
        return
    if action=='status':
        file=directory/'account-state.json'
        if file.exists():
            state=json.loads(file.read_text('utf-8'))
            print('Account',state.get('account'),state.get('status'),'receiver',state.get('receiver',{}).get('state'))
        for file in sorted(directory.glob('*/state.json')):
            state=json.loads(file.read_text('utf-8'));print(file.parent.name,state.get('status'),state.get('model'),state.get('reasoning'))
        return
    env=dict(os.environ,PYTHONUTF8='1',PYTHONIOENCODING='utf-8')
    if action=='start':
        if any((directory/name).exists() for name in ('owner.json','account-owner.json')):
            raise ValueError('已有后台或残留状态文件；先查看状态并停止，不按PID盲杀其他进程')
        free_port(cfg['mcp_port']);connection()
        for name in ('STOP','SERVICE_STOP','SHUTDOWN'):(directory/name).unlink(missing_ok=True)
        spawn('account','account_runtime.py',env)
        time.sleep(1)
        print('后台启动请求已提交；用05-查看状态检查实际接收状态，关闭窗口不会停止后台')
        return
    if action=='test':
        free_port(cfg['test_port'])
        spawn('test-window','dialogue-test-window/server.py',env)
        import webbrowser
        webbrowser.open(f"http://127.0.0.1:{cfg['test_port']}/")

if __name__=='__main__':
    try:main()
    except Exception as exc:print('操作未完成：'+str(exc));raise SystemExit(1)
