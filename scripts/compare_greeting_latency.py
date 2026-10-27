"""Synthetic greeting only; same persona, no QQ tools, no messages sent to QQ."""
from concurrent.futures import ThreadPoolExecutor
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import threading
import time

ROOT=Path(__file__).resolve().parent.parent
spec=importlib.util.spec_from_file_location('latency_window',ROOT/'dialogue-test-window/server.py')
window=importlib.util.module_from_spec(spec);spec.loader.exec_module(window)
worker=window.load_current_runtime()
base=worker.cli_args()
base[-1:-1]=['-c','mcp_servers.kaltsit_bot.enabled=false','-c','model_instructions_file='+json.dumps(str(ROOT/'dialogue-test-window/test-policy.txt'))]
prompt=window.build_prompt({'nickname':'测试博士','message':'下午好凯尔希','history':[],'context':''})
env={k:v for k,v in os.environ.items() if 'API_KEY' not in k.upper() and not k.startswith(('CODEX_THREAD','CODEX_TURN','CODEX_TASK','CODEX_RUN','CODEX_DAEMON'))}
env.update(PYTHONUTF8='1',PYTHONIOENCODING='utf-8')
output=ROOT/'runtime/diagnostics/greeting-latency';output.mkdir(parents=True,exist_ok=True)

def run(effort):
    args=list(base);args[-1:-1]=['-c','model_reasoning_effort='+json.dumps(effort)]
    start=time.monotonic();trace=[];stderr=[];reply='';usage={}
    with (output/(effort+'.stderr.log')).open('wb') as err:
        child=subprocess.Popen(args,cwd=window.prepare_test_work(),env=env,stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=err,
                               shell=False,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
        timer=threading.Timer(150,child.kill);timer.start()
        try:
            child.stdin.write(prompt.encode('utf-8'));child.stdin.close()
            for line in child.stdout:
                try:event=json.loads(line)
                except ValueError:continue
                item=event.get('item') or {}
                trace.append(dict(seconds=round(time.monotonic()-start,3),type=event.get('type'),item_type=item.get('type')))
                if event.get('type')=='item.completed' and item.get('type')=='agent_message':reply=item.get('text','')
                if event.get('type')=='turn.completed':usage=event.get('usage',{})
            code=child.wait()
        finally:timer.cancel()
    result=dict(reasoning=effort,seconds=round(time.monotonic()-start,3),exit_code=code,trace=trace,usage=usage,
                reply=reply,prompt_chars=len(prompt),persona_sha256=window.current_metadata(worker)['persona_sha256'])
    (output/(effort+'.json')).write_text(json.dumps(result,ensure_ascii=False,indent=2),'utf-8')
    return result

if __name__=='__main__':
    with ThreadPoolExecutor(max_workers=2) as pool:
        for result in pool.map(run,['high','low']):print(json.dumps(result,ensure_ascii=False),flush=True)
