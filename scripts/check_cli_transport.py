"""Offline CLI config parser test with a temporary synthetic Codex home."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
ROOT=Path(__file__).resolve().parent.parent
sys.path.insert(0,str(ROOT))
from cli_config import settings_args

def main():
    program=shutil.which('codex.exe') or shutil.which('codex')
    if not program:raise ValueError('需要原生Codex CLI才能执行配置解析测试')
    with tempfile.TemporaryDirectory(prefix='kaltsit-cli-config-') as temp:
        home=Path(temp)
        (home/'config.toml').write_text('[mcp_servers.tulpa]\nurl="http://127.0.0.1:39999/mcp"\nenabled=false\n[mcp_servers.unrelated]\ncommand="synthetic-unrelated"\nenabled=false\n','utf-8')
        env=dict(os.environ,CODEX_HOME=str(home));env.pop('KALTSIT_CONFIG',None);env.pop('KALTSIT_GROUP',None)
        # Source defaults are disabled until configured. This only asks CLI to
        # parse settings and list transports, never starts a server or a model.
        result=subprocess.run([program,*settings_args(['get_chat_session']),'mcp','list','--json'],env=env,capture_output=True,timeout=20,shell=False)
        if result.returncode:raise ValueError('CLI配置解析失败：'+result.stderr.decode('utf-8','replace')[:800])
        rows=json.loads(result.stdout)
        row=next(r for r in rows if r['name']=='kaltsit_bot')
        transport=row['transport']
        if transport.get('type')!='stdio' or 'url' in transport:raise ValueError('全局HTTP配置没有被覆盖，禁止启用')
        old=next(r for r in rows if r['name']=='tulpa')
        assert old['transport']['url']=='http://127.0.0.1:39999/mcp'
        print('Codex invocation-local STDIO uses isolated kaltsit_bot name; old HTTP definition unchanged, no global config edited, no model started.')

if __name__=='__main__':main()
