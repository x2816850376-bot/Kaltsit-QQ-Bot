"""Return only a confirmed complete model turn; reap CLI cleanup separately."""
import json
import os
from pathlib import Path
import subprocess
import threading
import time
import sys
sys.path.insert(0,str(Path(__file__).resolve().parent.parent))

def validate_reply(text):
    try:value=json.loads(text)
    except (ValueError,TypeError):return False
    from chat_social import response_object
    try:response_object(value)
    except (ValueError,TypeError):return False
    return (isinstance(value,dict) and
            isinstance(value['bubbles'],list) and 1<=len(value['bubbles'])<=3 and
            all(isinstance(s,str) and s.strip() and len(s)<=4000 for s in value['bubbles']))

class WebBudgetExceeded(RuntimeError):pass

def run_turn(args,prompt,*,cwd,env,log_dir,timeout=150,popen=subprocess.Popen,reply_validator=None,web_budget=None):
    start=time.monotonic();events=[];reply='';finished=False
    log_dir=Path(log_dir);log_dir.mkdir(parents=True,exist_ok=True)
    stamp=str(time.time_ns());err=(log_dir/(stamp+'.stderr.log')).open('wb')
    try:
        child=popen(args,stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=err,
                    cwd=cwd,env=env,shell=False,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
    except BaseException:err.close();raise
    timer=threading.Timer(timeout,child.kill);timer.daemon=True;timer.start()
    trace=[];web_seen=set();web_pending=[];web_count=0
    try:
        child.stdin.write(prompt.encode('utf-8'));child.stdin.close()
        for line in child.stdout:
            try:event=json.loads(line)
            except (ValueError,TypeError):continue
            item=event.get('item') or {}
            if web_budget is not None and item.get('type')=='web_search' and event.get('type') in ('item.started','item.completed'):
                identity=item.get('id')
                if identity and identity in web_seen:
                    if event['type']=='item.completed' and identity in web_pending:web_pending.remove(identity)
                elif event['type']=='item.completed' and web_pending and (identity is None or None in web_pending):
                    web_pending.remove(None) if identity and None in web_pending else web_pending.pop(0)
                    if identity:web_seen.add(identity)
                else:
                    web_count+=1
                    if identity:web_seen.add(identity)
                    if event['type']=='item.started':web_pending.append(identity)
                if web_count>web_budget:raise WebBudgetExceeded('Native web activity exceeded the per-turn budget')
            trace.append(dict(seconds=round(time.monotonic()-start,3),type=event.get('type'),item_type=item.get('type')))
            if event.get('type')=='item.completed' and item.get('type')=='agent_message':reply=item.get('text','')
            # Keep only response and tool type metadata, never private reasoning.
            if item.get('type') not in ('reasoning',):events.append(event)
            if event.get('type') in ('turn.failed','error'):
                raise RuntimeError('Model turn failed; no model switched')
            if event.get('type')=='turn.completed':
                if not (reply_validator or validate_reply)(reply):raise RuntimeError('Model did not complete the required bubbles object')
                finished=True
                elapsed=time.monotonic()-start
                with (log_dir/'latency.jsonl').open('a',encoding='utf-8') as log:
                    log.write(json.dumps(dict(request=stamp,seconds=round(elapsed,3),trace=trace,
                                              usage=event.get('usage',{}),prompt_chars=len(prompt)))+'\n')
                return reply,events,elapsed
        if time.monotonic()-start>=timeout:raise subprocess.TimeoutExpired(args,timeout)
        raise RuntimeError('CLI exited without a complete model reply')
    finally:
        timer.cancel()
        if not finished:
            if child.poll() is None:child.terminate()
            try:child.wait(timeout=5)
            except subprocess.TimeoutExpired:child.kill();child.wait(timeout=5)
            err.close()
        else:
            def reap():
                try:
                    child.wait(timeout=12)
                except subprocess.TimeoutExpired:
                    child.terminate()
                    try:child.wait(timeout=3)
                    except subprocess.TimeoutExpired:child.kill();child.wait(timeout=3)
                finally:
                    child.stdout.close();err.close()
            threading.Thread(target=reap,name='completed-cli-cleanup',daemon=True).start()
