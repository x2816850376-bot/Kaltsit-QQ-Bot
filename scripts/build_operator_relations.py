"""Build a source-bound relation graph from the operator topic index.

This is deliberately conservative: a page mentioning another operator does
not become that operator's hobby. Only normalized concepts that passed their
source-specific guards become direct subject relations; user-confirmed
cross-references remain explicitly marked as mentions.
"""
import json
import re
from datetime import datetime, timezone
from pathlib import Path

ROOT=Path(__file__).resolve().parent.parent
CONCEPTS=ROOT/'knowledge/arknights/operator-topic-concepts.json'
LINKS=ROOT/'knowledge/arknights/operator-topic-links.json'
IDENTITIES=ROOT/'knowledge/arknights/operator-identities.json'
OUT=ROOT/'knowledge/arknights/operator-relations.json'

PREDICATES={
    '棋类/围棋':('can_play','棋手身份与对弈能力'),
    '蜜饼/饼':('preference','偏好蜜饼或相关糕点'),
    '糖果/棒棒糖':('topic_association','与糖果或棒棒糖有关'),
    '酸橙/柑橘味':('topic_association','与酸橙或柑橘味有关'),
    '酸味':('topic_association','与酸味有关'),
    '酒/调酒':('skill_or_preference','与酒或调酒有关'),
    '音乐':('topic_association','与音乐或乐曲有关'),
    '电影':('topic_association','与电影有关'),
    '书籍/阅读':('topic_association','与阅读或书籍有关'),
}

def main():
    concepts=json.loads(CONCEPTS.read_text('utf-8'))
    links=json.loads(LINKS.read_text('utf-8'))
    identity_by_member={}
    if IDENTITIES.exists():
        for group in json.loads(IDENTITIES.read_text('utf-8')).get('groups',[]):
            for member in group.get('members',[]):
                identity_by_member[member]=(group.get('identity_group'),group.get('canonical',member))
    relations=[];seen=set()
    for row in concepts.get('entries',[]):
        subject=str(row.get('canonical','')).strip(); concept=str(row.get('concept','')).strip()
        if not subject or (concept not in PREDICATES and not concept.startswith('动作/')):continue
        if concept in PREDICATES:
            predicate,label=PREDICATES[concept]
        else:
            predicate,label='character_detail','角色动作细节：'+concept.split('/',1)[1]
        key=(subject,concept,row.get('section',''),row.get('source_url',''))
        if key in seen:continue
        seen.add(key)
        confidence=0.92 if row.get('verification')=='prts_topic_extract' else 0.82
        if row.get('relation')=='档案或剧情关联':confidence=0.72
        if predicate=='can_play':confidence=0.96
        if predicate=='character_detail':confidence=0.88
        if predicate=='preference':
            if re.search(r'最爱|爱吃|爱好',row.get('evidence','')):confidence=0.96
            elif '喜欢' in row.get('evidence',''):confidence=0.90
            else:confidence=0.55
        if predicate=='skill_or_preference':
            confidence=0.94 if '擅长' in row.get('evidence','') else 0.70
        identity_group,identity_canonical=identity_by_member.get(subject,(None,subject))
        relations.append({'subject':identity_canonical,'identity_group':identity_group,'source_member':subject,
                          'predicate':predicate,'predicate_label':label,
                          'object':concept,'object_aliases':row.get('aliases',[]),
                          'source_operator':subject,'speaker':None,'evidence_role':'subject_direct',
                          'confidence':confidence,'evidence':row.get('evidence','')[:1000],
                          'section':row.get('section',''),'source_url':row.get('source_url'),
                          'verification':row.get('verification','prts_raw_archive')})
    # Keep explicit cross-references separate from direct abilities/preferences.
    for row in links.get('links',[]):
        if row.get('verification')!='user_confirmed':continue
        subject=row.get('canonical'); keyword=(row.get('keywords') or [''])[0]
        if not subject or not keyword:continue
        identity_group,identity_canonical=identity_by_member.get(subject,(None,subject))
        relations.append({'subject':identity_canonical,'identity_group':identity_group,'source_member':subject,
                          'predicate':'mentioned_as','predicate_label':row.get('relation','旁述关系'),
                          'object':keyword,'object_aliases':[keyword],
                          'source_operator':None,'speaker':None,'evidence_role':'cross_reference',
                          'confidence':0.96,'evidence':row.get('evidence','')[:1000],
                          'section':row.get('section',''),'source_url':row.get('source_url'),
                          'verification':'user_confirmed'})
    data={'schema_version':1,'retrieved_at':datetime.now(timezone.utc).isoformat(),
          'source':'由PRTS话题概念库生成；区分主体关系与旁述关系',
          'relation_count':len(relations),'relations':relations}
    OUT.write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n','utf-8')
    print(json.dumps({'relations':len(relations),'direct':sum(x['evidence_role']=='subject_direct' for x in relations),'cross_reference':sum(x['evidence_role']=='cross_reference' for x in relations)},ensure_ascii=False))

if __name__=='__main__':main()
