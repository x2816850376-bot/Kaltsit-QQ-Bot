"""Create a checked source ZIP next to the clean source folder; never deletes data."""
import hashlib
import json
from pathlib import Path
import sys
import zipfile
import argparse
from datetime import date
import uuid
sys.dont_write_bytecode=True
from check_release import ROOT, findings, source_files

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--replace',action='store_true');parser.add_argument('--prepared-date',default=date.today().isoformat())
    options=parser.parse_args();date.fromisoformat(options.prepared_date)
    issues=findings()
    if issues:raise ValueError('请从干净源码副本打包，检查未通过：'+str(issues[:8]))
    manifest=ROOT/'release-manifest.json'
    records=[]
    for path in source_files():
        if path.is_file() and path!=manifest:
            body=path.read_bytes()
            records.append({'path':path.relative_to(ROOT).as_posix(),'size':len(body),'sha256':hashlib.sha256(body).hexdigest()})
    world=json.loads((ROOT/'knowledge/terra-journey/manifest.json').read_text('utf-8'))
    corpus=json.loads((ROOT/'knowledge/kaltsit-corpus/manifest.json').read_text('utf-8'))
    manifest.write_bytes(json.dumps({'edition':'full-knowledge-source','prepared_date':options.prepared_date,'model':'gpt-6-luna','reasoning':'high','fast':False,'personal_data_included':False,'group_memory_included':False,'full_indexed_book_text_included':True,'scan_images_included':False,'optional_embedding_model':'BAAI/bge-small-zh-v1.5','embedding_assets_included':False,'exchange_clock_state_included':False,'world_indexed_pages':world['indexed_pages'],'handwritten_regions':world['searchable_handwriting_passages'],'canonical_source_files':corpus['source_files'],'manifest_self_excluded':True,'files':records},ensure_ascii=False,indent=2).encode('utf-8'))
    target=ROOT.with_name('凯尔希QQ机器人-完整知识库版.zip')
    if target.exists() and not options.replace:raise ValueError('同名ZIP已存在；明确要更新时传入--replace，校验新包后才替换')
    temporary=target.with_name(target.name+'.'+uuid.uuid4().hex+'.pending')
    if temporary.resolve().parent!=ROOT.resolve().parent or target.resolve().parent!=ROOT.resolve().parent:raise ValueError('压缩包目标路径不在源码目录同级')
    with zipfile.ZipFile(temporary,'x',compression=zipfile.ZIP_DEFLATED,compresslevel=9) as archive:
        for path in source_files():
            if path.is_file():archive.write(path,(Path(ROOT.name)/path.relative_to(ROOT)).as_posix())
    with zipfile.ZipFile(temporary) as archive:
        if archive.testzip() is not None:raise ValueError('ZIP完整性校验失败')
        for record in records:
            body=archive.read(ROOT.name+'/'+record['path'])
            if hashlib.sha256(body).hexdigest()!=record['sha256']:raise ValueError('ZIP文件校验失败')
    temporary.replace(target)
    print(json.dumps({'archive':str(target),'source_files':len(records)+1,'source_bytes':sum(r['size'] for r in records),'archive_bytes':target.stat().st_size,'archive_sha256':hashlib.sha256(target.read_bytes()).hexdigest()},ensure_ascii=False))

if __name__=='__main__':main()
