"""Offline fixed-corpus vector index. Never imports or summarizes user chats."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import sys
import uuid
ROOT=Path(__file__).resolve().parent.parent
sys.path.insert(0,str(ROOT))


def source_rows(root=ROOT):
    root=Path(root)
    path=root/'knowledge/terra-journey/index.sqlite3'
    with sqlite3.connect(path.resolve().as_uri()+'?mode=ro',uri=True) as db:
        for row in db.execute('SELECT page,file,text,chapter,verification,scope,speaker FROM pages ORDER BY page'):
            page,file,body,chapter,verification,scope,speaker=row
            if len(body.strip())>=30:
                yield {'domain':'world','record':'page:'+str(page),'scan_page':page,'file':file,'chapter':chapter,
                       'verification':verification,'scope':scope,'source_speaker':speaker,'text':body}
        for page,body,verification,scope,speaker in db.execute('SELECT page,text,verification,scope,speaker FROM handwritten_regions ORDER BY page'):
            yield {'domain':'world','record':'hand:'+str(page),'scan_page':page,'file':'handwritten:'+str(page),
                   'chapter':'','verification':verification,'scope':scope,'source_speaker':speaker,'text':body}
    path=root/'knowledge/kaltsit-corpus/index.sqlite3'
    with sqlite3.connect(path.resolve().as_uri()+'?mode=ro',uri=True) as db:
        for identity,file,kind,stage,speaker,scene,body,start,end,verification in db.execute('SELECT id,file,kind,stage,speaker,scene,text,start_char,end_char,verification FROM passages ORDER BY id'):
            yield {'domain':'canonical','record':'passage:'+str(identity),'file':file,'kind':kind,'stage':stage,
                   'source_speaker':speaker,'scene':scene,'verification':verification,
                   'source_start_char':start,'source_end_char':end,'text':body}


def chunks(row,size=320,overlap=48):
    body=row['text'];start=0
    while start<len(body):
        end=min(len(body),start+size)
        if end<len(body):
            boundary=max(body.rfind(mark,start+size//2,end) for mark in ('。','！','？','\n'))
            if boundary>=0:end=boundary+1
        part=body[start:end]
        if part.strip():
            yield {**{k:v for k,v in row.items() if k!='text'},'text':part,'chunk_start':start,'chunk_end':end,
                   'source_text_sha256':hashlib.sha256(body.encode()).hexdigest()}
        if end==len(body):break
        start=max(start+1,end-overlap)


def build(allow_download=False):
    from fastembed import TextEmbedding
    import numpy as np
    target=ROOT/'runtime/semantic';target.mkdir(parents=True,exist_ok=True)
    manifest=target/'index.json'
    sources={}
    for relative in ('knowledge/terra-journey/index.sqlite3','knowledge/kaltsit-corpus/index.sqlite3'):
        p=ROOT/relative;stat=p.stat()
        sources[relative]={'size':stat.st_size,'mtime_ns':stat.st_mtime_ns,'sha256':hashlib.sha256(p.read_bytes()).hexdigest()}
    version=hashlib.sha256(json.dumps({'sources':sources,'model':'BAAI/bge-small-zh-v1.5','size':320,'overlap':48},sort_keys=True).encode()).hexdigest()
    if manifest.exists() and json.loads(manifest.read_text('utf-8')).get('version')==version:
        print('Semantic index already current',flush=True);return
    rows=[part for row in source_rows() for part in chunks(row)]
    print('Preparing local embedding model; chunks='+str(len(rows)),flush=True)
    model=TextEmbedding('BAAI/bge-small-zh-v1.5',cache_dir=str(target/'models'),threads=2,
                        providers=['CPUExecutionProvider'],local_files_only=not allow_download)
    def chunk_key(row):
        return hashlib.sha256(json.dumps({k:v for k,v in row.items() if k!='source_text_sha256'},sort_keys=True,ensure_ascii=False).encode()).hexdigest()
    reused={}
    if manifest.exists():
        old=json.loads(manifest.read_text('utf-8'))
        if old.get('model')=='BAAI/bge-small-zh-v1.5':
            previous=json.loads((target/old['records']).read_text('utf-8'))
            vectors=np.load(target/old['matrix'],mmap_mode='r')
            reused={chunk_key(row):vectors[i] for i,row in enumerate(previous)}
    missing=[row for row in rows if chunk_key(row) not in reused]
    fresh={}
    for i,(row,value) in enumerate(zip(missing,model.embed([r['text'] for r in missing],batch_size=32))):
        fresh[chunk_key(row)]=value
        if (i+1)%256==0:print('Indexed '+str(i+1)+' / '+str(len(missing)),flush=True)
    values=[reused[chunk_key(row)] if chunk_key(row) in reused else fresh[chunk_key(row)] for row in rows]
    matrix=np.asarray(values,dtype=np.float32)
    matrix/=np.maximum(np.linalg.norm(matrix,axis=1,keepdims=True),1e-12)
    # Immutable generation files + atomic manifest switch leave readers usable.
    matrix_name='vectors-'+version[:16]+'.npy';records_name='records-'+version[:16]+'.json'
    with (target/(matrix_name+'.pending')).open('wb') as f:np.save(f,matrix)
    (target/(matrix_name+'.pending')).replace(target/matrix_name)
    (target/(records_name+'.pending')).write_text(json.dumps(rows,ensure_ascii=False),'utf-8')
    (target/(records_name+'.pending')).replace(target/records_name)
    result={'schema':1,'version':version,'model':'BAAI/bge-small-zh-v1.5','sources':sources,
            'matrix':matrix_name,'records':records_name,'chunks':len(rows),'dimension':512,'reused_chunks':len(rows)-len(missing)}
    pending=manifest.with_name('index-'+uuid.uuid4().hex+'.pending')
    pending.write_text(json.dumps(result,ensure_ascii=False,indent=2),'utf-8');pending.replace(manifest)
    print(json.dumps({k:result[k] for k in ('version','chunks','dimension')},ensure_ascii=False),flush=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--allow-download',action='store_true')
    args=parser.parse_args();build(args.allow_download)
