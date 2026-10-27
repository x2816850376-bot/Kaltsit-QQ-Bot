"""Build a source-bound operator topic index from PRTS raw wikitext.

The generated index is compact: it keeps only archive excerpts and explicit
topic phrases, with the original PRTS page URL. It never sends the raw pages to
Luna and never changes the approved persona.
"""
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from html import unescape
import json
from pathlib import Path
import re
from urllib.parse import quote
from urllib.request import Request, urlopen

ROOT=Path(__file__).resolve().parent.parent
ROSTER=ROOT/'knowledge/arknights/operators.json'
OUT=ROOT/'knowledge/arknights/operator-topic-corpus.json'
LINKS=ROOT/'knowledge/arknights/operator-topic-links.json'
UA='KaltsitKnowledgeResearch/1.0 (local source index; contact via project owner)'
TRIGGER=re.compile(r'爱好|喜欢|不喜欢|习惯|擅长|感兴趣|热衷|着迷|食物|吃|喝|酒|糖|茶|咖啡|音乐|歌曲|电影|书|画|乐器|收藏|宠物|家人|父亲|母亲|兄|姐|弟|妹|朋友|搭档|队友|关系|游戏|玩耍|信物|物品|携带|随身|果子|水果|酸橙|酸味|橙味|棒棒糖|蜜饼|唇膏|味道|口味')
PHRASES=(
    re.compile(r'喜欢(?:做的事|的[^，。！？\n]{0,6})?[：:，,]?\s*([^。！？\n]{2,40})'),
    re.compile(r'爱好(?:是|为|：|:)?\s*([^。！？\n]{2,30})'),
    re.compile(r'习惯(?:是|于|：|:)?\s*([^。！？\n]{2,30})'),
    re.compile(r'对([^。！？\n]{2,20})(?:感兴趣|着迷|热衷)'),
)

def clean(value):
    value=unescape(re.sub(r'<[^>]+>','',value))
    value=re.sub(r'\{\{[^{}]{0,120}\}\}','',value)
    value=re.sub(r'\[\[[^]|]+\|([^]]+)\]\]',r'\1',value)
    value=re.sub(r'\[\[([^]]+)\]\]',r'\1',value)
    value=re.sub(r'\s+',' ',value).strip()
    return value

def fetch(name):
    url='https://prts.wiki/w/'+quote(name,safe='')+'?action=raw'
    last=''
    for attempt in range(3):
        try:
            req=Request(url,headers={'User-Agent':UA})
            raw=urlopen(req,timeout=25).read().decode('utf-8','replace')
            return name,url,raw,''
        except Exception as exc:
            last=type(exc).__name__+': '+str(exc)
    return name,url,'',last

def sections(raw):
    found=[]
    pattern=re.compile(r'^\|档案(\d+)文本=(.*?)(?=^\|档案\d+[^\n]*=|^\}\}|\Z)',re.M|re.S)
    for match in pattern.finditer(raw):
        text=clean(match.group(2))
        if text and TRIGGER.search(text):found.append({'section':'档案'+match.group(1),'text':text})
    for field in ('干员简介','干员简介补充','基础信息','信物描述','专属模组'):
        for match in re.finditer(r'^\|'+re.escape(field)+r'=(.*?)(?=^\||^\}\}|\Z)',raw,re.M|re.S):
            text=clean(match.group(1))
            if text and TRIGGER.search(text):found.append({'section':field,'text':text})
    return found

def phrases(text):
    out=[]
    for pattern in PHRASES:
        for match in pattern.finditer(text):
            value=match.group(1).strip(' ，,、:：')
            for part in re.split(r'[，,、；;。]',value):
                part=part.strip()
                if 2<=len(part)<=16 and not re.fullmatch(r'[的这那他她它其以及和与或及\s]+',part):out.append(part)
    return list(dict.fromkeys(out))[:12]

def main():
    roster=json.loads(ROSTER.read_text('utf-8'))['operators']
    names=[row['name'] for row in roster]
    results=[];failed=[]
    with ThreadPoolExecutor(max_workers=6) as pool:
        futures=[pool.submit(fetch,name) for name in names]
        for future in as_completed(futures):
            name,url,raw,error=future.result()
            if error:failed.append({'name':name,'url':url,'error':error});continue
            for section in sections(raw):
                results.append({'canonical':name,'section':section['section'],'text':section['text'],
                                'keywords':phrases(section['text']),'source_url':url,
                                'verification':'prts_raw_archive','retrieved_at':datetime.now(timezone.utc).isoformat()})
    index={'schema_version':1,'source':'PRTS raw wikitext；仅保留带话题触发词的档案片段，不替代完整干员资料',
           'retrieved_at':datetime.now(timezone.utc).isoformat(),'operator_count':len(names),
           'entry_count':len(results),'failed_count':len(failed),'failed':failed,'entries':results}
    OUT.write_text(json.dumps(index,ensure_ascii=False,indent=2)+'\n','utf-8')
    old=json.loads(LINKS.read_text('utf-8')) if LINKS.exists() else {'schema_version':1,'links':[]}
    links=[x for x in old.get('links',[]) if x.get('verification') not in ('prts_topic_extract','prts_raw_archive')]
    seen={(x.get('canonical'),tuple(x.get('keywords',[]))) for x in links}
    for row in results:
        for keyword in row['keywords']:
            key=(row['canonical'],(keyword,))
            if key in seen:continue
            links.append({'keywords':[keyword],'canonical':row['canonical'],'topic':'PRTS档案话题',
                          'relation':'档案中出现的兴趣、习惯或角色关联','evidence':row['text'][:500],
                          'verification':'prts_topic_extract','source_url':row['source_url']})
            seen.add(key)
    old.update({'schema_version':1,'retrieved_at':index['retrieved_at'],'source':'用户确认条目与PRTS原始档案提取','links':links})
    LINKS.write_text(json.dumps(old,ensure_ascii=False,indent=2)+'\n','utf-8')
    print(json.dumps({'operators':len(names),'entries':len(results),'links':len(links),'failed':len(failed)},ensure_ascii=False))

if __name__=='__main__':main()
