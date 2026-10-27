"""Complete, source-bound historical event units; no invented story completion."""
from contextlib import closing
import hashlib
import json
from pathlib import Path
import re
import secrets
import sqlite3

STORY_USAGE=(
    '检索到的片段只用于定位对应的完整事件或历史段落，不能直接拿片段拼成故事。'
    '先沿同一主题、章节、来源页或事件卡补齐前因、行动、冲突、结果和时间范围，再开始叙述；找不到完整对应内容就换一段资料完整的往事，或明确停在已知事实，不补缺口。'
    'event_card给出同一历史片段的完整事实链，不是要逐项宣读的提纲。'
    '选择卡中一个有依据的具体细节作为切入点，让听者先进入当时的处境，再随主体的选择、阻力和后果往下听；'
    '可改变揭示顺序、取舍旁支和组织句子，不照卡片分点，不按国家百科的语气罗列年份和定义。'
    '让前一件事真实地推动后一件事，结尾回到开头的具体事物或这个选择的实际代价；没有依据的因果不能用“于是”补上。'
    '族群和国家也可以作主体，无须编造一个见证人。只用卡中事实及对应证据，不添加对白、路人、事故、心理或结局，'
    '尤其不把忘记、没有记载或一方的行动扩写成双方故意如此；短评价也不能绕过事实边界。'
    '范围边界和不确定性必须保留：宗教宣传不变成真实起源，可能不变成已证实，后果未记载就不补造。'
    '以凯尔希第一人称立场讲述，不假称亲历所有事件，不播报来源或卡片。可以直接停在后果，也可留一句短判断，'
    '判断必须落在这次选择付出的代价上，不用抽象道理代替结尾，不套固定罪因。只发送完整故事正文。')


def documented_event(root,query,max_chars,generic=False,*,event_id=None):
    root=Path(root);path=root/'story-events.json';index=root/'index.sqlite3'
    if not path.exists() or not index.exists():return None
    try:
        catalog=json.loads(path.read_text('utf-8'))
        if catalog.get('schema_version')!=1:return None
        candidates=[]
        with closing(sqlite3.connect(index.resolve().as_uri()+'?mode=ro',uri=True)) as db:
            for card in catalog.get('events',[]):
                if event_id is not None and card['id']!=event_id:continue
                tags=card['tags'];score=sum(len(t) for t in tags if t in query)
                if event_id is None and not generic and not score:continue
                sources={};valid=True
                for ref in card['sources']:
                    hand=ref['scope']=='handwritten_annotation_only'
                    table='handwritten_regions' if hand else 'pages'
                    row=db.execute(f'SELECT text,verification,scope,speaker FROM {table} WHERE page=?',(ref['scan_page'],)).fetchone()
                    if not row or row[1] not in ('user_transcribed','user_transcribed_handwriting','curated_summary') or row[2]!=ref['scope'] or hashlib.sha256(row[0].encode('utf-8')).hexdigest()!=ref['text_sha256']:
                        valid=False;break
                    sources[ref['scan_page']]=row
                if not valid:continue
                facts=card['facts']
                if not facts or any(f['scan_page'] not in sources or f['support_quote'] not in sources[f['scan_page']][0] for f in facts):continue
                if sum(len(f['text']) for f in facts)>max_chars:continue
                if set(card['sequence'])!={f['id'] for f in facts}:continue
                candidates.append((score,card,sources))
        if not candidates:return None
        best=max(row[0] for row in candidates)
        _,card,sources=secrets.choice([row for row in candidates if row[0]==best])
        facts=[{'id':f['id'],'text':f['text'],'scan_page':f['scan_page']} for f in card['facts']]
        budget=max_chars-sum(len(f['text']) for f in facts)
        excerpts=[]
        # Evidence excerpts are secondary to the complete fact chain; retain
        # each source's exact scope rather than silently merging page regions.
        per_source=max(0,budget//len(sources))
        for page,row in sources.items():
            text,verification,scope,speaker=row
            quotes=[f['support_quote'] for f in card['facts'] if f['scan_page']==page]
            position=min((text.index(q) for q in quotes),default=0)
            start=max(0,position-30);excerpt=text[start:start+per_source]
            excerpts.append({'scan_page':page,'verification':verification,'scope':scope,'source_speaker':speaker,'excerpt':excerpt})
        return {'status':'ok','source':'明日方舟：大地巡旅（已校对片段的事实摘要）','query':query,
                'mode':'documented_story','story_topic':card['id'],'usage':STORY_USAGE,
                'retrieval_scope':'complete_event','full_context_required':False,
                'event_card':{'id':card['id'],'title':card['title'],'starting_detail':card['starting_detail'],
                              'narrative_focus':card['narrative_focus'],'facts':facts,'sequence':card['sequence'],
                              'boundaries':card['boundaries'],'sources':card['sources']},
                'pages':excerpts,'verified_summaries':[]}
    except (OSError,ValueError,KeyError,TypeError,sqlite3.Error):
        return None
