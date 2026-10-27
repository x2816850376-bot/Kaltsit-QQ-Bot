"""Group original and alter operators into one person identity.

English operator names are the most stable cross-stage key on PRTS: alter
forms use the same base name followed by “the ...” or “·...”. Chinese stage
suffixes and parenthesized class forms are retained as members, while the
shortest base name is used for neutral topic recommendations.
"""
import json,re
from pathlib import Path

ROOT=Path(__file__).resolve().parent.parent
ROSTER=ROOT/'knowledge/arknights/operators.json'
OUT=ROOT/'knowledge/arknights/operator-identities.json'

def identity_key(row):
    english=str(row.get('english','')).strip().casefold()
    english=re.split(r'\s+the\s+|·|\s+\(',english,1)[0].strip()
    if english:return english
    name=re.sub(r'\([^)]*\)','',str(row.get('name',''))).strip()
    name=re.sub(r'^(新约|耀骑士|烛|引星|赤刃明霄|假日威龙)','',name)
    return name

def main():
    roster=json.loads(ROSTER.read_text('utf-8'))['operators']
    groups={}
    for row in roster:groups.setdefault(identity_key(row),[]).append(row)
    result=[]
    for key,members in sorted(groups.items()):
        if len(members)<2:continue
        ordered=sorted(members,key=lambda x:(len(x['name']),x['name']))
        result.append({'identity_group':key,'canonical':ordered[0]['name'],
                       'members':[x['name'] for x in ordered],
                       'source_urls':[x.get('source_url') for x in ordered if x.get('source_url')]})
    OUT.write_text(json.dumps({'schema_version':1,'source':'由PRTS干员英文基名与阶段名称自动归并','groups':result},ensure_ascii=False,indent=2)+'\n','utf-8')
    print(json.dumps({'groups':len(result),'members':sum(len(x['members']) for x in result),'examples':result[:12]},ensure_ascii=False))

if __name__=='__main__':main()
