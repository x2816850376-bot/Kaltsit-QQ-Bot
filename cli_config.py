"""Invocation-local MCP wiring; never edits the user's Codex configuration."""
from functools import lru_cache
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
from bot_config import ROOT, CONFIG_PATH, load, group_id
SERVER_NAME='kaltsit_bot'


def cli_program(settings=None):
    settings=load(False) if settings is None else settings
    value=settings.get('codex_path') or shutil.which('codex.exe') or shutil.which('codex')
    if not value:
        # npm's Windows shim is not used as a shell command; find its native executable.
        shim=shutil.which('codex.cmd')
        if shim:
            candidates=list((Path(shim).parent/'node_modules/@openai/codex').glob('**/codex.exe'))
            if candidates:value=str(candidates[0])
    if not value:raise ValueError('未找到Codex CLI。请安装并执行 codex login，或在配置中填写codex_path')
    if str(value).lower().endswith(('.bat','.cmd')):raise ValueError('codex_path请填原生codex.exe，不能是批处理脚本')
    return str(value)


@lru_cache(maxsize=4)
def capabilities(program):
    output=''
    for arguments in ([program,'--help'],[program,'exec','--help']):
        result=subprocess.run(arguments,capture_output=True,timeout=15,shell=False,
                              creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
        if result.returncode:raise ValueError('Codex CLI自检失败')
        output+=result.stdout.decode('utf-8','replace')
    flags=set(re.findall(r'--[a-z][a-z-]+',output))
    if not {'--ephemeral','--skip-git-repo-check','--json'}<=flags:
        raise ValueError('Codex CLI缺少本项目所需exec参数，请更新后重试；不会切换模型')
    return flags


def toml(value):
    if isinstance(value,dict):return '{'+','.join(json.dumps(k)+ '='+toml(v) for k,v in value.items())+'}'
    if isinstance(value,list):return '['+','.join(toml(v) for v in value)+']'
    return json.dumps(value,ensure_ascii=False)


def settings_args(tools,global_servers=None,runtime_env=None):
    stanza={'command':sys.executable,'args':[str(ROOT/'mcp-stdio-proxy.py')],
            'enabled':True,'enabled_tools':tools,'startup_timeout_sec':30,'tool_timeout_sec':240,
            'env':{'KALTSIT_CONVERSATION':group_id(),'KALTSIT_CONFIG':str(CONFIG_PATH)}}
    # Codex overrides merge maps. A separate name avoids inheriting the user's
    # existing Tulpa HTTP transport; cli_args rejects collisions with this name.
    stanza['tools']={name:{'approval_mode':'approve'} for name in tools}
    # MCP subprocesses do not inherit arbitrary environment variables from CLI.
    # Explicitly pass only this worker's immutable batch/path bindings.
    for key in ('KALTSIT_REPLY_IDS','KALTSIT_SEED_PACKET_FILE'):
        if key in (runtime_env or {}):stanza['env'][key]=runtime_env[key]
    servers={name:dict(spec,enabled=False) for name,spec in (global_servers or {}).items()}
    servers[SERVER_NAME]=stanza
    return ['-c','mcp_servers='+toml(servers)]
