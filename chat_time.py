"""Actual confirmed exchange times; no offline-life inference or LLM calls."""
from copy import deepcopy
from datetime import datetime, timezone, timedelta
import json
from pathlib import Path
import time
import uuid
from chat_social import write_lock


class ExchangeClock:
    def __init__(self,path,cid,clock=time.time):
        self.path=Path(path);self.cid=cid;self.clock=clock;self.reload()

    def reload(self):
        self.data={'schema':1,'conversation_id':self.cid,'people':{},'commits':[]}
        if self.path.exists():
            row=json.loads(self.path.read_text('utf-8'))
            if row.get('schema')!=1 or row.get('conversation_id')!=self.cid:raise ValueError('Time scope mismatch')
            self.data=row
        now=self.clock()
        self.data['people']={p:t for p,t in self.data['people'].items() if isinstance(t,(int,float)) and 0<=now-t<180*86400}
        self.data['people']=dict(sorted(self.data['people'].items(),key=lambda p:p[1])[-128:])
        self.data['commits']=self.data['commits'][-256:]

    def context(self,message):
        self.reload()
        if message.get('conversation_id') not in (None,self.cid):raise ValueError('Foreign clock message')
        if (message.get('reply_routing') or {}).get('address_evidence') in ('explicit_at_other','reply_to_other','unresolved_reply','self_echo'):return {}
        prior=self.data['people'].get(message.get('sender_id'));now=self.clock()
        if prior is None or now<prior:return {}
        gap=now-prior
        zone=timezone(timedelta(hours=8),name='Asia/Shanghai');today=datetime.fromtimestamp(now,zone).date();previous=datetime.fromtimestamp(prior,zone).date()
        if gap<1800 and today==previous:return {}
        return {'exchange_time_gap':{'hours':round(gap/3600,1),'calendar_days':(today-previous).days,
                'basis':'距与当前对象上次确认交流；不代表对方离线或任何人的生活经历'}}

    def confirm(self,key,trigger,receipt,at=None):
        if not isinstance(trigger,dict) or trigger.get('conversation_id')!=self.cid or trigger.get('is_self') or not isinstance(trigger.get('sender_id'),str):raise ValueError('Invalid confirmed time speaker')
        if not any(p.get('state')=='SUCCEEDED' for p in receipt.get('parts',[])):return
        stamp=self.clock() if at is None else at
        if not isinstance(stamp,(int,float)) or not 0<=self.clock()-stamp<180*86400:return
        with write_lock(self.path):
            self.reload()
            if key in self.data['commits']:return
            person=trigger['sender_id'];self.data['people'][person]=max(stamp,self.data['people'].get(person,0))
            self.data['commits']=(self.data['commits']+[key])[-256:]
            self.path.parent.mkdir(parents=True,exist_ok=True)
            pending=self.path.with_name(self.path.name+'.'+uuid.uuid4().hex+'.pending')
            pending.write_text(json.dumps(self.data,ensure_ascii=False),'utf-8');pending.replace(self.path)

    def reconcile(self,batches):
        if not Path(batches).exists():return
        self.reload()
        for key,row in json.loads(Path(batches).read_text('utf-8')).get('rows',{}).items():
            if key in self.data['commits']:continue
            trigger=row.get('trigger')
            if not trigger or trigger.get('conversation_id')!=self.cid:continue
            parts=[{'state':p.get('state')} for p in row.get('parts',[])]
            self.confirm(key,trigger,{'parts':parts},at=row.get('at'))

    def enrich(self,packet):
        out=deepcopy(packet)
        for message in out.get('messages',[]):
            if not message.get('is_self') and message.get('conversation_id') in (None,self.cid):message.update(self.context(message))
        return out
