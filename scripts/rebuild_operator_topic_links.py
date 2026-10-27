"""Rebuild compact topic links from the already downloaded PRTS corpus."""
import json,re
from pathlib import Path

ROOT=Path(__file__).resolve().parent.parent
CORPUS=ROOT/'knowledge/arknights/operator-topic-corpus.json'
LINKS=ROOT/'knowledge/arknights/operator-topic-links.json'
CONCEPTS=ROOT/'knowledge/arknights/operator-topic-concepts.json'
STOP={'这些','这个','那个','她们','他们','自己','一位干员','罗德岛','加入罗德岛','个人爱好','很多事情','一些事情','这件事','这样的事情',
      '的事','的事情','的东西','的家伙','的地方','的人','的类型','的两人','的工作','的方式'}
LEADING={'的','了','着','过','与','和','在','这','那','一','上','将','把','用','为','从','对','于','跟','向','给','由','被','让','使','以','而','且','都','还','也','并','跟着'}
TRAILING={'的','了','着','过','吗','呢','吧','哦','啊','时','人','事','物','地方','家伙','方面','部分','一点','一个','一种','之后','以前','时候'}
SPLIT_RE=re.compile(r'[，,、；;。！？!？]|以及|并且|而且|但是|不过|只是|同时|然后|所以|因此|因为|以及|和|与|还|也|并|及')
# Concept families let a query use a natural variant (“酸橙味的糖果”)
# while keeping the source phrase and relation attached to each operator.
CONCEPT_GROUPS={
    '酸橙/柑橘味':('酸橙味','酸橙','橙味','酸橙汁','酸橙干','酸橙酱','酸橙粉'),
    '酸味':('酸味','酸味的','酸的'),
    '糖果/棒棒糖':('棒棒糖','糖果','甜食'),
    '蜜饼/饼':('蜜饼','蜜饼干'),
    '音乐':('音乐','乐曲','歌曲'),
    '电影':('电影','影片'),
    '书籍/阅读':('看书','阅读','书籍','读书'),
    '酒/调酒':('调酒','喝酒','酒'),
    '棋类/围棋':('围棋','下棋','对弈','棋手','棋道','棋局','棋盘','棋枰','棋子','棋盒'),
}
CONCEPT_QUERY_ALIASES={
    '棋类/围棋':('围棋','下棋','对弈','棋类','棋手'),
}
ACTION_RE=re.compile(r'(?:经常|喜欢|擅长|习惯|总是|会|我).{0,10}(跺脚|打拳|跑步|跳舞|唱歌|大笑|哭泣|喊叫|睡觉|喝酒|吃饭|画画|写字|读书)')
CONCEPT_GUARDS={
    # “臭棋篓子” or a general historical list must not be attributed to the
    # operator whose archive happens to quote it. Keep strong self-relation
    # phrases such as “无业棋手”“和望对弈” instead.
    '棋类/围棋':re.compile(r'棋手|棋道|棋枰|对弈|(?:喜欢|擅长|习惯|邀请|邀约).{0,8}下棋|和.{0,8}下棋'),
}

def concept_aliases(text):
    text=str(text)
    groups=[]
    for group,terms in CONCEPT_GROUPS.items():
        matched=[term for term in terms if term in text and len(term)>=2]
        if matched: groups.append((group,matched))
    for match in ACTION_RE.finditer(text):
        term=match.group(1).strip()
        if len(term)>=2 and term not in ('喜欢吃','喜欢喝','喜欢看','喜欢玩'):
            groups.append(('动作/'+term,[term]))
    return groups

def concept_allowed(group,text,canonical=''):
    if group.startswith('动作/'):
        term=group.split('/',1)[1]
        for m in re.finditer(re.escape(term),str(text)):
            lo=max(0,m.start()-60); hi=min(len(str(text)),m.end()+60)
            nearby=str(text)[lo:hi]
            if canonical and canonical in nearby and re.search(r'经常|喜欢|擅长|习惯|总是|我|她|他',nearby):return True
        return False
    guard=CONCEPT_GUARDS.get(group)
    if not guard:return True
    text=str(text); canonical=str(canonical)
    if group=='棋类/围棋' and canonical:
        c=re.escape(canonical)
        # Require a direct self relation. A screenplay saying “卡达和某人
        # 下棋” or a story mentioning “那名棋手” is not enough to recommend
        # that operator for a chess partner.
        strong=re.compile(rf'(?:{c}.{{0,24}}(?:棋手|棋道|棋枰|对弈|喜欢.{{0,8}}下棋|擅长.{{0,8}}下棋)|(?:棋手|棋道|棋枰|对弈).{{0,24}}{c})')
        return bool(strong.search(text))
    for match in guard.finditer(text):
        lo=max(0,match.start()-80); hi=min(len(text),match.end()+80)
        if canonical and canonical in text[lo:hi]:return True
    return False

def evidence_score(group, row, text=''):
    text=str(text or row.get('evidence',''))
    section=str(row.get('section',''))
    score=0
    if row.get('verification')=='user_confirmed':score+=100
    if section=='信物描述':score+=24
    if section=='基础信息':score+=4
    if re.search(r'最爱|爱吃|喜欢|擅长|爱好|热衷|习惯|感兴趣',text):score+=12
    if re.search(r'直接|明确|本人|亲自|不肯|不会拒绝|几乎不会',text):score+=5
    if group=='棋类/围棋':score+=sum(8 for term in ('国手','棋道','棋手','对弈','棋艺') if term in text)
    if group.startswith('动作/'):score+=8 if group.split('/',1)[1] in text else 0
    if len(text)>120:score+=2
    return score

def parts(text):
    return [x.strip() for x in re.split(r'[。！？\n]',text) if x.strip()]

def candidates(sentence,previous):
    values=[]
    # Prefer bounded expressions. The old extractor greedily consumed the
    # remainder of a sentence, producing false topics such as “吃好” or
    # “羽兽摄影的干员在附近发现”.
    strong_patterns=(
        r'(?:最爱|爱吃|爱喝|喜欢吃|喜欢喝|喜欢看|喜欢听|喜欢玩|喜欢收集|喜欢使用|喜欢用|喜欢做|喜欢|擅长|热衷于|热衷|习惯于|习惯|爱好)(?:是|为|：|:)?\s*([^，,、；;。！？!？\n]{2,24})',
        r'(?:最爱|爱吃|喜欢吃)[^。！？\n]{0,40}?选择\s*([^，,、；;。！？!？\n]{2,16})',
        r'喜欢\s*([^的，,、；;。！？!？\n]{2,12})的',
    )
    for pat in strong_patterns:
        values.extend(m.group(1) for m in re.finditer(pat,sentence))
    # A list after an em dash is commonly the concrete object of a later
    # “喜欢做的事” sentence (for example, food or daily activities).
    if '喜欢' in sentence and previous and '——' in previous:
        values.extend(re.split(r'[、，,]|以及|和',previous.split('——',1)[1]))
    out=[]
    for value in values:
        value=value.strip(' ，,、；;:：“”"\'')
        # Keep the first concrete noun phrase rather than the rest of the
        # clause. This preserves “蜜饼”“酸味的棒棒糖”“小型录音器”等具体话题。
        value=SPLIT_RE.split(value,1)[0].strip(' ，,、；;:：“”"\'')
        if value in STOP or not 2<=len(value)<=16:continue
        if value.startswith(tuple(LEADING)) or value.endswith(tuple(TRAILING)):continue
        if value.startswith(('所以','她','他','其','这些','那个','这位','这种','那些','其中')):continue
        if not any(ch in value for ch in '吃喝玩看听收集用做打睡唱跳酒糖茶咖啡食物蜜饼肉面奶果点心音乐歌曲电影书画乐器宠物朋友家人父母兄姐弟妹搭档队友'):
            continue
        if value not in out:out.append(value)
    return out[:12]

def main():
    corpus=json.loads(CORPUS.read_text('utf-8'));old=json.loads(LINKS.read_text('utf-8'))
    links=[x for x in old.get('links',[]) if x.get('verification')=='user_confirmed']
    seen={(x.get('canonical'),tuple(x.get('keywords',[]))) for x in links}
    for entry in corpus.get('entries',[]):
        rows=parts(entry.get('text',''))
        for i,row in enumerate(rows):
            if not re.search(r'喜欢|爱好|习惯|擅长|感兴趣|热衷|着迷|最爱|爱吃',row):continue
            for value in candidates(row,rows[i-1] if i else ''):
                key=(entry['canonical'],(value,))
                if key in seen:continue
                section=entry.get('section','')
                relation='信物或物品关联' if section in ('信物描述','基础信息') else '档案中出现的兴趣、习惯或角色关联'
                links.append({'keywords':[value],'canonical':entry['canonical'],'topic':'PRTS档案话题',
                              'relation':relation,'evidence':row[:700], 'section':section,
                              'verification':'prts_topic_extract','source_url':entry['source_url']})
                seen.add(key)
    data={'schema_version':1,'retrieved_at':corpus.get('retrieved_at'),'source':'用户确认条目与PRTS原始档案提取','links':links}
    LINKS.write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n','utf-8')
    concept_map={}
    def add_concept(row,group,aliases,*,topic,relation,evidence,section,source_url,verification):
        aliases=list(dict.fromkeys(list(aliases)+list(CONCEPT_QUERY_ALIASES.get(group,()))))
        key=(row.get('canonical'),group)
        candidate={'concept':group,'aliases':aliases,'canonical':row.get('canonical'),
                   'topic':topic,'relation':relation,'evidence':evidence or '',
                   'section':section or '','source_url':source_url,
                   'verification':verification or 'prts_topic_extract'}
        score=evidence_score(group,candidate,evidence)
        previous=concept_map.get(key)
        if previous is None or score>previous[0]:concept_map[key]=(score,candidate)
    for row in links:
        # A user-confirmed cross-reference such as “令称望为臭棋篓子” is
        # evidence about the target, but it must not become a direct hobby
        # relation for the page owner.
        if '旁述' in str(row.get('relation','')) or '称呼' in str(row.get('relation','')):continue
        source=' '.join([str(row.get('keywords','')),str(row.get('evidence',''))])
        for group,aliases in concept_aliases(source):
            if not concept_allowed(group,source,row.get('canonical','')):continue
            add_concept(row,group,aliases,topic=row.get('topic','角色细节'),
                        relation=row.get('relation','关联信息'),evidence=row.get('evidence',''),
                        section=row.get('section',''),source_url=row.get('source_url'),
                        verification=row.get('verification','prts_topic_extract'))
    # Artifact and story fields do not always contain a “喜欢/擅长” verb.
    # Read the corpus directly as well, so a signal item such as Angelina's
    # sour-orange lip balm becomes searchable without inventing a preference.
    def corpus_priority(row):
        text=str(row.get('text','')); section=row.get('section','')
        if section=='信物描述':return 0
        if section=='基础信息':return 1
        # For a repeated concept, prefer explicit ability/history evidence
        # such as “国手”“棋道”“对弈邀请” over a short roster summary.
        if any(term in text for term in ('国手','棋道','对弈的邀约','对弈邀请','棋艺')):return 2
        return 3
    for row in sorted(corpus.get('entries',[]), key=corpus_priority):
        section=row.get('section',''); text=row.get('text','')
        relation='信物或物品关联' if section in ('信物描述','基础信息') else '档案或剧情关联'
        for group,aliases in concept_aliases(text):
            if not concept_allowed(group,text,row.get('canonical','')):continue
            add_concept(row,group,aliases,topic='干员话题概念',relation=relation,
                        evidence=text[:700],section=section,source_url=row.get('source_url'),
                        verification='prts_raw_archive')
    concepts=[value for _,value in sorted(concept_map.values(),key=lambda item:(item[1].get('canonical',''),item[1].get('concept','')))]
    CONCEPTS.write_text(json.dumps({'schema_version':1,'retrieved_at':corpus.get('retrieved_at'),
                                    'source':'由PRTS话题关联自动归一化生成；保留原始证据与关系类型',
                                    'groups':list(CONCEPT_GROUPS),'entries':concepts},ensure_ascii=False,indent=2)+'\n','utf-8')
    print(json.dumps({'links':len(links),'concepts':len(concepts),'manual':sum(x.get('verification')=='user_confirmed' for x in links),'auto':sum(x.get('verification')=='prts_topic_extract' for x in links)},ensure_ascii=False))

if __name__=='__main__':main()
