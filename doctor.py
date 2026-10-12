"""Read-only connection checks; model smoke is explicit and never sends QQ text."""
import argparse
import importlib.util
import json
import shutil
import subprocess
import sys
from bot_config import ROOT,load


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--model-test',action='store_true');args=parser.parse_args()
    cfg=load()
    from cli_config import cli_program,capabilities
    program=cli_program(cfg);capabilities(program)
    for command in ([program,'--version'],[program,'login','status']):
        r=subprocess.run(command,capture_output=True,timeout=20,shell=False)
        if r.returncode:raise ValueError('Codex登录或版本检查失败；请执行 codex login')
        # CLI status text is shown, never auth.json or a login token.
        print(r.stdout.decode('utf-8','replace').strip())
    if not(cfg['node_path'] or shutil.which('node')):raise ValueError('缺少Node.js')
    from configure import verify_bridge
    verify_bridge(cfg);print('QQ账号及所有群号核验通过（没有发送群消息）')
    from chat_dialogue import read_dialogue_skill,read_coherence_skill
    read_dialogue_skill();read_coherence_skill()
    from chat_knowledge import OperatorKnowledge
    knowledge=OperatorKnowledge(ROOT/'knowledge/arknights/operators.json');print('干员条目：',len(knowledge.operators))
    from chat_corpus import CanonicalKnowledge
    corpus=CanonicalKnowledge().retrieve('任命助理',500);print('原作语料：',corpus['status'])
    from chat_world import TerraKnowledge
    result=TerraKnowledge().retrieve('萨科塔故事',1600)
    if result['status']!='ok':raise ValueError('世界观全文索引未就绪')
    print('世界观全文、原作语料、故事事件卡、两份表达Skill检查通过')
    if args.model_test:
        spec=importlib.util.spec_from_file_location('model_smoke',ROOT/'luna-chat-runtime.py')
        worker=importlib.util.module_from_spec(spec);spec.loader.exec_module(worker)
        command=worker.cli_args();command[-1:-1]=['-c','mcp_servers.kaltsit_bot.enabled=false']
        work=ROOT/'runtime/diagnostics/empty-work';work.mkdir(parents=True,exist_ok=True)
        import os
        env={k:v for k,v in os.environ.items() if 'API_KEY' not in k.upper() and not k.startswith(('CODEX_THREAD','CODEX_TURN','CODEX_TASK','CODEX_RUN','CODEX_DAEMON'))}
        r=subprocess.run(command,input='独立模型接入检查，不调用任何工具，仅输出：连接正常'.encode('utf-8'),capture_output=True,cwd=work,env=env,timeout=150,shell=False)
        if r.returncode:raise ValueError('实际Luna调用失败或额度不足；未切换模型，群聊未启动')
        events=[json.loads(line) for line in r.stdout.decode('utf-8','replace').splitlines() if line.strip().startswith('{')]
        if not any(e.get('type')=='item.completed' and e.get('item',{}).get('type')=='agent_message' for e in events):raise ValueError('模型没有返回正文')
        print('真实GPT-6 Luna调用通过；本次消耗一次模型调用，没有QQ群发送')
    else:print('尚未实际调用模型。模型可用性和额度可用 --model-test 验证。')


if __name__=='__main__':
    try:main()
    except Exception as exc:print('检查未通过：'+str(exc));raise SystemExit(1)
