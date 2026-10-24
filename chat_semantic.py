"""Optional, deadline-limited local semantic supplement. Host imports only stdlib."""
from collections import OrderedDict
from copy import deepcopy
import hashlib
import hmac
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import re
import secrets
import subprocess
import sys
import threading
import time
from urllib.request import build_opener, ProxyHandler, Request

ROOT=Path(__file__).resolve().parent
RUNTIME=ROOT/'runtime/semantic'
MODEL='BAAI/bge-small-zh-v1.5'
MAX_WAIT=.2
MIN_SCORE=.60
_rebuild_lock=threading.Lock()


def schedule_prepare(root):
    if not _rebuild_lock.acquire(blocking=False):return
    def run():
        try:ensure_worker(root)
        finally:_rebuild_lock.release()
    threading.Thread(target=run,daemon=True).start()


def current_sources(manifest,root=ROOT):
    try:
        return all((Path(root)/name).stat().st_size==info['size'] and (Path(root)/name).stat().st_mtime_ns==info['mtime_ns']
                   for name,info in manifest['sources'].items())
    except (KeyError,OSError,TypeError):return False


def should_search(message,payload):
    q=str(message.get('content','')).strip()
    if not 7<=len(q)<=500:return False
    if (message.get('reply_routing') or {}).get('address_evidence') in ('explicit_at_other','reply_to_other','unresolved_reply','self_echo'):return False
    if re.search(r'最新|现在.*活动|本期|新版本|当前版本|卡池|几点|天气|\bhttps?://',q):return False
    if re.fullmatch(r'(?:凯尔希[，,\s]*)?(?:你是谁|你是AI吗|在吗|下午好|晚上好|早上好|晚安|你好|我想你了)[？?！!。\s]*',q):return False
    if not re.search(r'为什么|为何|怎么|如何|什么|哪些|哪[个些种里儿]|谁|介绍|解释|由来|起源|历史|背景|意味着|记得|能否|可不可以',q):return False
    mentions=payload.get('operator_mentions') or message.get('operator_mentions') or []
    if any(m.get('canonical') not in ('凯尔希','凯尔希·思衡托') for m in mentions):return False
    if mentions and re.search(r'技能|模组|职业|天赋|生日|专精|攻击|生命值|防御|费用',q):return False
    world=payload.get('world_knowledge') or {}
    if world.get('event_card') or payload.get('story_progress'):return False
    canonical=payload.get('canonical_knowledge') or {}
    if any(p.get('scene') and p['scene'] in q for p in canonical.get('passages',[])):return False
    # A focused literal match takes the fast path; weak common-character hits
    # do not count as reliable coverage.
    words=re.sub(r'为什么|是什么|怎么|如何|请问|博士|凯尔希|能不能|可以|这个|那个|的|了|吗|呢|我|你',' ',q)
    grams={run[i:i+2] for run in re.findall(r'[\u3400-\u9fff]+',words) for i in range(len(run)-1)}
    evidence=' '.join(p.get('excerpt','') for p in canonical.get('passages',[])+world.get('pages',[]))
    if len(grams)>=3 and sum(g in evidence for g in grams)/len(grams)>=.7:return False
    return True


class SemanticClient:
    def __init__(self,root=ROOT,timeout=MAX_WAIT):
        self.root=Path(root);self.directory=self.root/'runtime/semantic';self.timeout=min(MAX_WAIT,max(.001,timeout))
        self.opener=build_opener(ProxyHandler({}))

    def query(self,query):
        start=time.monotonic()
        if os.environ.get('KALTSIT_SEMANTIC_DISABLED')=='1':return None
        try:
            state=json.loads((self.directory/'worker.json').read_text('utf-8'))
            manifest=json.loads((self.directory/'index.json').read_text('utf-8'))
            if state.get('status')!='ready':return None
            if state.get('version')!=manifest.get('version') or not current_sources(manifest,self.root):
                schedule_prepare(self.root);return None
            port=state['port']
            if type(port)!=int or not 1024<=port<=65535:return None
            raw=json.dumps({'query':query,'version':manifest['version']},ensure_ascii=False).encode()
            request=Request(f'http://127.0.0.1:{port}/search',raw,{'Content-Type':'application/json','Authorization':'Bearer '+state['token']})
            remaining=self.timeout-(time.monotonic()-start)
            if remaining<=0:return None
            with self.opener.open(request,timeout=remaining) as response:
                result=json.loads(response.read(30000))
            if time.monotonic()-start>self.timeout:return None
            if result.get('version')!=manifest['version']:return None
            return result
        except (OSError,ValueError,KeyError,TypeError,TimeoutError):return None

    def supplement(self,message,payload):
        if not should_search(message,payload):return payload
        found=self.query(str(message.get('content','')))
        if not found:return payload
        candidates=found.get('matches',[])
        if not candidates:return payload
        best=candidates[0]
        from chat_world import query_tokens,focus_tokens,TERMS
        subjects=list(dict.fromkeys(TERMS.findall(str(message.get('content','')))))
        focus=focus_tokens(str(message.get('content','')),subjects)
        coverage=sum(t in best['text'] for t in focus)/max(1,len(focus))
        # A narrowly separated near match is not evidence. Prefer the original
        # keyword result over a vague semantic hit; exact concepts add support.
        next_score=candidates[1]['score'] if len(candidates)>1 else 0
        if best['score']<MIN_SCORE or best['score']<.72 and best['score']-next_score<.045 and coverage<.35:return payload
        out=deepcopy(payload)
        from chat_corpus import RULES as CORPUS_RULES
        from chat_world import RULES as WORLD_RULES
        # Pick the best domain, never append another full knowledge payload.
        domain=candidates[0]['domain'];key='canonical_knowledge' if domain=='canonical' else 'world_knowledge'
        old=out.get(key) or {};field='passages' if domain=='canonical' else 'pages'
        limit=1000 if domain=='canonical' else 1200
        previous_budget=sum(len(r.get('excerpt','')) for r in old.get(field,[]))
        other_key='world_knowledge' if domain=='canonical' else 'canonical_knowledge'
        other_field='pages' if domain=='canonical' else 'passages'
        other_budget=sum(len(r.get('excerpt','')) for r in (out.get(other_key) or {}).get(other_field,[]))
        budget=min(limit,previous_budget or other_budget) if previous_budget or other_budget else limit
        selected=[];records=set()
        for row in candidates:
            if row['domain']!=domain or row['score']<max(MIN_SCORE,best['score']-.04) or row['record'] in records:continue
            part=row['text'][:budget]
            if not part:break
            records.add(row['record']);budget-=len(part)
            # Fixed, source-bound metadata only. No filename supplied by model.
            fields=('file','kind','stage','scene','source_speaker','verification','source_start_char','source_end_char') if domain=='canonical' else ('scan_page','file','chapter','verification','scope','source_speaker')
            metadata={k:row[k] for k in fields if k in row}
            if domain=='canonical':
                base=metadata.get('source_start_char')
                if isinstance(base,int):
                    metadata['source_start_char']=base+row.get('chunk_start',0)
                    metadata['source_end_char']=metadata['source_start_char']+len(part)
                metadata['truncated']=True
            selected.append({**metadata,'excerpt':part})
            if len(selected)==2 or budget<=0:break
        if not selected:return payload
        if not previous_budget and other_budget:out.pop(other_key,None)
        out[key]={'status':'ok','source':old.get('source','用户已提供的原作资料'),
                  'query':str(message.get('content','')),'rules':CORPUS_RULES if domain=='canonical' else WORLD_RULES,
                  field:selected}
        return out
    def enrich(self,packet):
        out=deepcopy(packet)
        # One supplement per incoming batch, and only for the actual last event.
        rows=[r for r in out.get('messages',[]) if isinstance(r,dict) and not r.get('is_self')]
        if rows and should_search(rows[-1],rows[-1]):
            rows[-1].update(self.supplement(rows[-1],rows[-1]))
        return out


def status(root=ROOT):
    try:
        directory=Path(root)/'runtime/semantic';state=json.loads((directory/'worker.json').read_text('utf-8'))
        manifest=json.loads((directory/'index.json').read_text('utf-8'))
        ready=state.get('status')=='ready' and state.get('version')==manifest.get('version') and current_sources(manifest,root)
        return {'state':'ready' if ready else 'fallback','model':MODEL,'chunks':manifest.get('chunks',0),'max_wait_ms':200}
    except (OSError,ValueError,KeyError):return {'state':'fallback','model':MODEL,'max_wait_ms':200}


def ensure_worker(root=ROOT):
    """Only explicit service startup invokes this. Chat requests never load models."""
    root=Path(root);directory=root/'runtime/semantic';manifest=directory/'index.json'
    if not manifest.exists():return False
    try:
        info=json.loads(manifest.read_text('utf-8'))
        valid=current_sources(info,root)
        state=json.loads((directory/'worker.json').read_text('utf-8'))
        request=Request(f"http://127.0.0.1:{state['port']}/health",headers={'Authorization':'Bearer '+state['token']})
        with build_opener(ProxyHandler({})).open(request,timeout=.1) as response:
            health=json.load(response)
        if valid and health.get('version')==info['version']:return True
    except (OSError,ValueError,KeyError,TypeError):pass
    python=root/'.semantic-venv/Scripts/pythonw.exe'
    if not python.exists():return False
    directory.mkdir(parents=True,exist_ok=True)
    from chat_social import write_lock
    with write_lock(directory/'launch'):
        # A fresh launching marker avoids concurrent launches during prewarm.
        try:
            state=json.loads((directory/'worker.json').read_text('utf-8'))
            if state.get('status')=='starting' and time.time()-state.get('at',0)<600:return False
        except (OSError,ValueError):pass
        (directory/'worker.json').write_text(json.dumps({'status':'starting','at':time.time()}),'utf-8')
        env=dict(os.environ,PYTHONUTF8='1',OMP_NUM_THREADS='2',OPENBLAS_NUM_THREADS='1',HF_HUB_OFFLINE='1')
        with (directory/'worker.stdout.log').open('ab') as out,(directory/'worker.stderr.log').open('ab') as err:
            subprocess.Popen([str(python),str(root/'chat_semantic.py'),'--prepare-worker'],cwd=root,env=env,
                             stdout=out,stderr=err,shell=False,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
    return False


def worker():
    from fastembed import TextEmbedding
    import numpy as np
    directory=RUNTIME;manifest=json.loads((directory/'index.json').read_text('utf-8'))
    if not current_sources(manifest):raise ValueError('Stale semantic source index')
    model=TextEmbedding(MODEL,cache_dir=str(directory/'models'),threads=2,
                        providers=['CPUExecutionProvider'],local_files_only=True)
    list(model.query_embed('预热'))
    matrix=np.load(directory/manifest['matrix'],mmap_mode='r')
    records=json.loads((directory/manifest['records']).read_text('utf-8'))
    cache=OrderedDict();gate=threading.Lock();token=secrets.token_urlsafe(32)
    class Handler(BaseHTTPRequestHandler):
        def log_message(self,*args):pass
        def send(self,status,value):
            body=json.dumps(value,ensure_ascii=False).encode();self.send_response(status)
            self.send_header('Content-Type','application/json');self.send_header('Content-Length',str(len(body)));self.end_headers()
            try:self.wfile.write(body)
            except (BrokenPipeError,ConnectionResetError,ConnectionAbortedError):pass
        def authorized(self):return hmac.compare_digest(self.headers.get('Authorization',''),'Bearer '+token)
        def do_GET(self):
            if not self.authorized():return self.send(403,{})
            if self.path!='/health':return self.send(404,{})
            return self.send(200,{'version':manifest['version'],'model':MODEL,'chunks':len(records)})
        def do_POST(self):
            if not self.authorized():return self.send(403,{})
            if self.path!='/search':return self.send(404,{})
            if not gate.acquire(blocking=False):return self.send(429,{})
            try:
                size=int(self.headers.get('Content-Length','0'))
                if not 0<size<=5000:raise ValueError('Invalid query')
                data=json.loads(self.rfile.read(size));query=data.get('query')
                if set(data)!={'query','version'} or data['version']!=manifest['version'] or not isinstance(query,str) or not 1<=len(query)<=500:raise ValueError('Invalid query')
                if not current_sources(manifest):return self.send(503,{})
                key=hashlib.sha256(query.encode()).hexdigest();start=time.monotonic();cached=False
                if key in cache and time.monotonic()-cache[key][0]<600:
                    matches=cache[key][1];cache.move_to_end(key);cached=True
                else:
                    embedding=np.asarray(next(iter(model.query_embed(query))),dtype=np.float32)
                    embedding/=max(float(np.linalg.norm(embedding)),1e-12)
                    scores=matrix@embedding
                    order=np.argsort(scores)[::-1][:6]
                    matches=[{**records[int(i)],'score':round(float(scores[i]),5)} for i in order]
                    cache[key]=(time.monotonic(),matches)
                    while len(cache)>256:cache.popitem(last=False)
                return self.send(200,{'version':manifest['version'],'matches':matches,'cached':cached,
                                      'milliseconds':round((time.monotonic()-start)*1000,2)})
            except (ValueError,KeyError,TypeError):return self.send(400,{})
            finally:gate.release()
    server=ThreadingHTTPServer(('127.0.0.1',0),Handler)
    state={'status':'ready','pid':os.getpid(),'port':server.server_port,'token':token,'at':time.time(),
           'version':manifest['version'],'model':MODEL,'chunks':len(records)}
    temporary=directory/'worker.pending';temporary.write_text(json.dumps(state),'utf-8');temporary.replace(directory/'worker.json')
    def retire_old():
        while True:
            time.sleep(5)
            try:
                published=json.loads((directory/'worker.json').read_text('utf-8'))
                if published.get('status')=='ready' and published.get('pid')!=os.getpid():server.shutdown();return
            except (OSError,ValueError):pass
    threading.Thread(target=retire_old,daemon=True).start()
    server.serve_forever()


if __name__=='__main__':
    if sys.argv[1:]==['--prepare-worker']:
        from scripts.build_semantic_index import build
        build(False);worker()
    elif sys.argv[1:]==['--worker']:worker()
