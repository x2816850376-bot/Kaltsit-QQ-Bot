"""Native recipient spacing and contextual salutation hints; never adds a title."""
from collections import OrderedDict
from pathlib import Path
import json
import re
import time
from chat_context import GROUP

PRESET = 'kaltsit_arknights_standard'

class DoctorAddress:
    def __init__(self, path=None):
        self.path = Path(path) if path else None
        self.personas = {}
        self.last = {}
        self.prepared = OrderedDict()
        if self.path and self.path.exists():
            try:
                data = json.loads(self.path.read_text('utf-8'))
                self.last = {k:v for k,v in data.get('last', {}).items()
                             if time.time()-v.get('at', 0)<3600}
                self.prepared = OrderedDict((k,v) for k,v in data.get('prepared', [])
                                             if time.time()-v.get('at',0)<3600)
            except (OSError, ValueError, TypeError, KeyError):
                pass

    def observe(self, data):
        if not isinstance(data, dict):
            return
        session = data.get('session') or {}
        sid = session.get('id') or data.get('session_id')
        if sid and session.get('persona_preset'):
            self.personas[sid] = session['persona_preset']

    def hint(self, sid, message, pending, now=None):
        now = time.time() if now is None else now
        enabled = self.personas.get(sid) == PRESET and not message.get('is_self')
        recipient = str(message.get('sender_id', ''))
        previous = self.last.get(sid, {})
        gap = now-previous.get('at', 0)
        evidence = (message.get('reply_routing') or {}).get('address_evidence')
        omitted = previous.get('unaddressed_turns', 0) if recipient == previous.get('recipient') else 0
        recommended = enabled and bool(recipient) and (
            recipient != previous.get('recipient') or gap >= 300 or
            evidence == 'explicit_at_bot' and gap >= 60 or omitted >= 2)
        nickname = re.sub(r'[\r\n\t]+', ' ', str(message.get('sender') or '')).strip()[:200]
        named = nickname if nickname.endswith('博士') else nickname+'博士'
        other_titles=[]
        for (seen,_),person in pending.items():
            if seen==sid and str(person.get('sender_id',''))!=recipient:
                other_name=str(person.get('sender') or '').strip()
                if other_name:other_titles.append(other_name if other_name.endswith('博士') else other_name+'博士')
        title = '博士'
        numeric_recipient = recipient.isascii() and recipient.isdigit() and 0<int(recipient)<10**16
        active_people={str(row.get('sender_id','')) for (seen,eid),row in pending.items()
                       if seen==sid and not row.get('is_self') and type(eid)==int and eid>=message.get('id',0)-8}
        switch=bool(previous.get('recipient') and recipient!=previous['recipient'] and gap<300)
        mention_required=enabled and numeric_recipient and (switch or len(active_people)>1)
        mention_recommended=enabled and numeric_recipient and (mention_required or not previous or gap>=300)
        if GROUP.split(':')[1]=='direct':
            mention_required=mention_recommended=False
        return dict(enabled=enabled, required=False, recommended=recommended, recipient=recipient,
                    consecutive_omissions=omitted,
                    title=title, named_title=named if nickname else '',
                    other_named_titles=other_titles,
                    mention_required=bool(mention_required),mention_recommended=bool(mention_recommended),
                    mention_event_id=message.get('id') if mention_recommended else None,
                    reason='博士是日常称呼；恢复交谈、换对象或连续省略后优先自然用一次，句首句中句尾皆可。连续短答可省略，不固定前缀，不为了称呼扩写')

    def prepare(self, arguments, hint):
        args = dict(arguments)
        args.pop('mention_event_id',None)
        if not hint.get('enabled'):
            return args
        key = str(args.get('session_id'))+'\0'+str(args.get('idempotency_key'))
        text = args.get('text', '')
        eid = args.get('respond_to_event_id')
        if key in self.prepared:
            row = self.prepared[key]
            if row['original'] != text or row['event_id'] != eid:
                raise ValueError('同一发送编号不得改变文字或目标')
            args['text'] = row['text']
            if row.get('mention_event_id') is not None:args['mention_event_id']=row['mention_event_id']
            return args
        punctuation_only = not text.strip() or bool(re.fullmatch(r'[\s?？!！…。.,，]+', text))
        named_title=hint.get('named_title')
        for other_title in hint.get('other_named_titles',[]):
            if other_title!=named_title and re.match(r'^'+re.escape(other_title)+r'(?=$|[\s，,！？!?：:])',text):
                raise ValueError('正文称呼与绑定的提问者不一致；请绑定实际回应的消息并只称博士')
        if named_title and named_title!='博士':
            text=re.sub(r'^'+re.escape(named_title)+r'(?=$|[\s，,！？!?：:])','博士',text,count=1)
        # A native at segment has no trailing whitespace in the current sender.
        # Store the wire text once so retries retain their original signature.
        if hint.get('mention_event_id') is not None and text and not text[0].isspace():
            text=' '+text
        self.prepared[key] = dict(original=args.get('text'), text=text, event_id=eid,
                                  mention_event_id=hint.get('mention_event_id'),
                                  recipient=hint.get('recipient'), at=time.time(),
                                  spoken=not punctuation_only, addressed='博士' in text)
        while len(self.prepared)>128:
            self.prepared.popitem(last=False)
        self._save()
        args['text'] = text
        if hint.get('mention_event_id') is not None:args['mention_event_id']=hint['mention_event_id']
        return args

    def commit(self, arguments):
        sid = arguments.get('session_id')
        key = str(sid)+'\0'+str(arguments.get('idempotency_key'))
        row = self.prepared.get(key)
        if row and row.get('spoken') and not row.get('committed'):
            row['committed']=True
            previous=self.last.get(sid,{})
            omitted=previous.get('unaddressed_turns',0) if previous.get('recipient')==row['recipient'] else 0
            self.last[sid] = dict(recipient=row['recipient'], at=time.time(),
                                 unaddressed_turns=0 if row.get('addressed','博士' in row.get('text','')) else omitted+1)
            if len(self.last)>64:
                oldest=min(self.last,key=lambda k:self.last[k]['at'])
                del self.last[oldest]
            self._save()

    def enrich(self, data, pending):
        self.observe(data)
        if not isinstance(data, dict):
            return data
        sid = data.get('session_id') or (data.get('session') or {}).get('id')
        batches = [data.get('messages'), (data.get('context') or {}).get('messages')]
        for rows in batches:
            if isinstance(rows, list):
                for row in rows:
                    if isinstance(row, dict) and row.get('conversation_id')==GROUP and (sid,row.get('id')) in pending:
                        hint = self.hint(sid, row, pending)
                        if hint['enabled']:
                            row['role_address'] = {**{k:hint[k] for k in ('required','recommended','recipient','title','consecutive_omissions','reason','mention_required','mention_recommended')},'position':'contextual','native_at_sender':'contextual','applies_to':'direct_or_targeted_reply','proactive_required':False}
        if self.personas.get(sid)==PRESET:
            data['role_address_rules']='每组回应仍绑定respond_to_event_id的实际群友；@按语境，交错发言或切换对象优先首条原生@，清楚的连续对话通常省略。@与正文保留空白，后续气泡不重复@。博士是默认日常称呼，位置自由，一组不重复点名；连续短答可省略，不长期完全省略，不固定前缀、不为称呼扩写。程序不强加称谓，不用昵称＋博士、不手写@昵称或CQ码。主动评论全群不自动@，对象绑定仍保留。'
        return data

    def commit_group(self,arguments,group_key):
        rows=[self.prepared.get(str(a.get('session_id'))+'\0'+str(a.get('idempotency_key'))) for a in arguments]
        rows=[r for r in rows if r]
        if not rows:return
        sid=arguments[0]['session_id'];previous=self.last.get(sid,{})
        same=previous.get('response_group')==group_key
        addressed=any(r.get('addressed') for r in rows)
        omitted=previous.get('unaddressed_turns',0) if previous.get('recipient')==rows[0]['recipient'] else 0
        for row in rows:row['committed']=True
        self.last[sid]=dict(recipient=rows[0]['recipient'],at=time.time(),response_group=group_key,
                            unaddressed_turns=0 if addressed else omitted if same else omitted+1)
        self._save()

    def _save(self):
        if not self.path:
            return
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temp = self.path.with_suffix('.tmp')
        temp.write_text(json.dumps(dict(last=self.last, prepared=list(self.prepared.items())),
                                   ensure_ascii=False), 'utf-8')
        temp.replace(self.path)
