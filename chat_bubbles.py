"""Bounded response groups, sequential sends and durable per-part receipts."""
import asyncio
import hashlib
import json
from pathlib import Path
import re
import time
from chat_completion import require_complete_text
from chat_style import normalize_outgoing_text

MAX_BUBBLES=3

def validate_bubbles(value):
    if not isinstance(value,list) or not 1<=len(value)<=MAX_BUBBLES:
        raise ValueError('一次回应需为1至3个完整气泡')
    if any(not isinstance(s,str) or not s.strip() or len(s)>4000 or any(ord(c)<32 and c not in '\n\t' for c in s) for s in value):
        raise ValueError('气泡需为非空正文，每条最多4000字')
    bubbles=[normalize_outgoing_text(s.strip()) for s in value]
    if any(not s.strip() for s in bubbles) or sum(map(len,bubbles))>6000:
        raise ValueError('整组回应为空或过长')
    if len(set(bubbles))!=len(bubbles):raise ValueError('同一组不能重复发送相同气泡')
    if any(re.match(r'^@|\[CQ:at,',s) for s in bubbles):raise ValueError('请用本地对象绑定，不手写@')
    complete=False
    for bubble in bubbles:
        try:require_complete_text(bubble);complete=True
        except ValueError:pass
    if not complete:raise ValueError('整组只有重说承诺，没有实际正文')
    require_complete_text('\n'.join(bubbles))
    return bubbles

def parse_window_bubbles(text):
    raw=text.strip()
    if raw.startswith('```json') and raw.endswith('```'):raw=raw[7:-3].strip()
    try:value=json.loads(raw)
    except ValueError:
        # Preserve plain-text compatibility; never split by sentence length.
        if raw.startswith(('{','[')):raise ValueError('无效气泡协议')
        return validate_bubbles([raw])
    if not isinstance(value,dict) or set(value)!={'bubbles'}:raise ValueError('无效气泡协议')
    return validate_bubbles(value['bubbles'])

def tool_data(result):
    if isinstance(result.structuredContent,dict):return result.structuredContent
    for part in result.content:
        if part.type=='text':
            try:data=json.loads(part.text)
            except ValueError:continue
            if isinstance(data,dict):return data
    return {}

class BubbleSender:
    def __init__(self,path=None):
        self.path=Path(path) if path else None;self.rows={};self.lock=asyncio.Lock()
        if self.path and self.path.exists():
            try:self.rows=json.loads(self.path.read_text('utf-8')).get('rows',{})
            except (OSError,ValueError,TypeError):pass

    def save(self):
        if len(self.rows)>256:
            self.rows=dict(sorted(self.rows.items(),key=lambda p:p[1]['at'])[-256:])
        if self.path:
            self.path.parent.mkdir(parents=True,exist_ok=True)
            temp=self.path.with_suffix('.tmp')
            temp.write_text(json.dumps({'rows':self.rows},ensure_ascii=False),'utf-8');temp.replace(self.path)

    @staticmethod
    def interrupted(context,trigger):
        if (context.get('session') or {}).get('active') is False:return True
        rows=context.get('messages',[])+(context.get('context') or {}).get('messages',[])
        for row in rows:
            if row.get('is_self') or row.get('sender_id')!=trigger.get('sender_id') or type(row.get('id'))!=int or row['id']<=trigger['id']:continue
            if row.get('conversation_id') and trigger.get('conversation_id') and row['conversation_id']!=trigger['conversation_id']:continue
            segments=row.get('segments',[])
            text=(''.join(str(s.get('text','')) for s in segments if s.get('type')=='text') if any(s.get('type')=='text' for s in segments) else str(row.get('content',''))).strip()
            if re.search(r'^(?:凯尔希[，, ]*)?(?:不用(?:讲|说|答|发|了)|别(?:讲|说|答|发)了|停一下|先停|停止|算了|等下|等一下|先别|换个话题|换一个话题)',text):return True
        return False

    def summary(self,row):
        return {'state':row.get('state','PENDING'),'sent_parts':sum(p['state']=='SUCCEEDED' for p in row['parts']),
                'total_parts':len(row['parts']),'parts':[{'index':i+1,'state':p['state'],'operation_id':p.get('operation_id')} for i,p in enumerate(row['parts'])],
                'instruction':'整组已记录。成功气泡不重发；UNKNOWN须核对原操作回执，不换编号。中断后不继续旧话头，等待下一条新消息。'}

    async def send(self,args,quotes,addresses,participation,upstream,expression_history=None):
        if set(args)-{'session_id','bubbles','respond_to_event_id','participation_mode','idempotency_key','mention_policy'}:
            raise ValueError('无效气泡发送参数')
        bubbles=validate_bubbles(args.get('bubbles'))
        sid=args.get('session_id');eid=args.get('respond_to_event_id');mode=args.get('participation_mode','direct');policy=args.get('mention_policy','auto')
        if not isinstance(sid,str) or type(eid)!=int or policy not in ('auto','omit') or mode not in ('direct','proactive'):
            raise ValueError('无效对象或模式')
        if not isinstance(args.get('idempotency_key'),str) or not 8<=len(args['idempotency_key'])<=80:raise ValueError('无效发送编号')
        key=hashlib.sha256(f'{sid}:{eid}:bubbles-v1'.encode()).hexdigest()
        signature=hashlib.sha256(json.dumps([bubbles,mode,policy],ensure_ascii=False).encode()).hexdigest()
        async with self.lock:
            row=self.rows.get(key)
            if row and row['signature']!=signature:raise ValueError('同一回应不能换内容、对象、模式或编号补发')
            if row and row.get('state') in ('SUCCEEDED','CANCELLED','FAILED'):return self.summary(row)
            trigger=quotes.pending.get((sid,eid)) if not row else row['trigger']
            if not trigger or trigger.get('is_self'):raise ValueError('先读取实际新消息再绑定回应')
            context_result=await upstream.call_tool('get_chat_session',{'session_id':sid})
            if context_result.isError:raise ValueError('无法核实会话当前状态，未继续发送')
            context=tool_data(context_result)
            if expression_history:expression_history.observe(context)
            if not row:
                hint=addresses.hint(sid,trigger,quotes.pending)
                fresh=context.get('context',{}).get('messages',[])
                if any(not m.get('is_self') and m.get('sender_id')!=trigger.get('sender_id') and type(m.get('id'))==int and m['id']>eid for m in fresh):
                    hint.update(mention_required=True,mention_event_id=eid)
                if mode=='proactive' or policy=='omit' and not hint.get('mention_required'):
                    hint['mention_event_id']=None
                parts=[]
                for i,text in enumerate(bubbles):
                    raw={'session_id':sid,'respond_to_event_id':eid,'idempotency_key':key+f'-{i+1}','text':text}
                    wire=quotes.prepare_send(raw)
                    part_hint=dict(hint)
                    if i:part_hint['mention_event_id']=None
                    rendered=addresses.prepare(raw,part_hint)
                    wire['text']=rendered['text']
                    if rendered.get('mention_event_id') is not None:wire['mention_event_id']=rendered['mention_event_id']
                    parts.append({'wire':wire,'state':'PENDING'})
                stored_trigger={k:trigger.get(k) for k in ('id','sender_id','conversation_id','is_self')}
                row={'signature':signature,'at':time.time(),'state':'PENDING','trigger':stored_trigger,'parts':parts}
                self.rows[key]=row;self.save()
            if self.interrupted(context,trigger):row['state']='CANCELLED';self.save();return self.summary(row)
            participation.admit({'session_id':sid,'respond_to_event_id':eid,'idempotency_key':key},mode)
            for i,part in enumerate(row['parts']):
                if part['state']=='SUCCEEDED':continue
                if part['state'] in ('SENDING','UNKNOWN'):
                    operation=next((op for op in context.get('recent_operations',[]) if op.get('id')==part.get('operation_id')),None)
                    if operation and operation.get('state')=='SUCCEEDED':
                        part['state']='SUCCEEDED';self.save();addresses.commit_group([p['wire'] for p in row['parts'] if p['state']=='SUCCEEDED'],key)
                        if expression_history:expression_history.commit(sid,key,[p['wire']['text'] for p in row['parts'] if p['state']=='SUCCEEDED'])
                        continue
                    row['state']='UNKNOWN';self.save();return self.summary(row)
                if i:
                    current=await upstream.call_tool('get_chat_session',{'session_id':sid})
                    if current.isError:row['state']='PENDING';self.save();return self.summary(row)
                    context=tool_data(current)
                    if self.interrupted(context,trigger):row['state']='CANCELLED';self.save();return self.summary(row)
                part['state']='SENDING';self.save()
                try:result=await upstream.call_tool('send_chat_message',part['wire'])
                except Exception:
                    part['state']='UNKNOWN';row['state']='UNKNOWN';self.save();return self.summary(row)
                receipt=tool_data(result);state=receipt.get('state')
                part['operation_id']=receipt.get('id')
                part['state']=state if state in ('SUCCEEDED','FAILED','UNKNOWN') else 'UNKNOWN'
                self.save()
                if part['state']!='SUCCEEDED':row['state']=part['state'];self.save();return self.summary(row)
                addresses.commit_group([p['wire'] for p in row['parts'] if p['state']=='SUCCEEDED'],key)
                if expression_history:expression_history.commit(sid,key,[p['wire']['text'] for p in row['parts'] if p['state']=='SUCCEEDED'])
            row['state']='SUCCEEDED';self.save();return self.summary(row)
