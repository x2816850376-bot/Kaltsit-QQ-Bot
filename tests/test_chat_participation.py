"""Group joining, direct-reply preservation and cooldown/retry regressions."""
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parent))
from chat_context import GROUP, ReplyContextCache
from chat_participation import ChatParticipation

BOT = GROUP.split(':')[0]
SID = 'offline-participation'

def message(eid, text, uid='123', segments=None, cid=GROUP):
    return {'id': eid, 'onebot_message_id': str(1000+eid), 'conversation_id':cid,
            'sender_id':uid, 'sender': '测试者', 'is_self':uid==BOT, 'content':text,
            'segments':segments if segments is not None else [{'type':'text','text':text}]}

class ParticipationTests(unittest.TestCase):
    def setUp(self):
        self.now=1000
        self.p=ChatParticipation(clock=lambda:self.now)
        self.q=ReplyContextCache()

    def enrich(self, rows, cursor=0):
        data=self.q.enrich({'session':{'id':SID,'cursor':cursor},'messages':rows})
        return self.p.enrich(data,self.q.pending)

    def send(self, mode='proactive', key='one', eid=1):
        if mode=='proactive':
            with patch.object(self.p,'sample',return_value=0):self.enrich([message(eid,'肉鸽话题')])
        self.p.admit({'session_id':SID,'idempotency_key':key,'respond_to_event_id':eid},mode)

    def test_no_at_can_join_game_topic(self):
        with patch.object(self.p,'sample',return_value=.01):
            d=self.enrich([message(1,'这次肉鸽通关了，最后差点漏怪')])
        self.assertEqual(d['messages'][0]['reply_routing']['address_evidence'],'not_explicit')
        self.assertTrue(d['messages'][0]['reply_participation']['proactive_opportunity'])
        self.assertEqual(d['group_participation']['opportunity_event_ids'],[1])

    def test_interests_use_context_and_higher_rate(self):
        with patch.object(self.p,'sample',return_value=.01):
            d=self.enrich([message(1,'今天吃啥'),message(2,'肉鸽最后一层寄了'),message(3,'就差一点')])
        self.assertFalse(d['messages'][0]['reply_participation']['proactive_opportunity'])
        self.assertTrue(d['messages'][2]['reply_participation']['proactive_opportunity'])

    def test_other_person_quote_can_get_optional_comment_without_becoming_recipient(self):
        with patch.object(self.p,'sample',return_value=0):
            d=self.enrich([message(1,'肉鸽寄了','a'),message(2,'你怎么又漏怪','b',[
                {'type':'reply','onebot_message_id':'1001'},{'type':'text','text':'你怎么又漏怪'}])])
        r=d['messages'][1]
        self.assertEqual(r['reply_routing']['quoted_speaker_id'],'a')
        self.assertEqual(r['reply_participation']['priority'],'optional')
        self.assertTrue(r['reply_participation']['proactive_opportunity'])

    def test_direct_at_and_reply_are_not_lottery(self):
        self.send()
        d=self.enrich([message(1,'在吗',segments=[{'type':'at','qq':BOT},{'type':'text','text':'在吗'}]),
                       message(2,'我在',BOT),message(3,'那你看看',segments=[
                           {'type':'reply','onebot_message_id':'1002'},{'type':'text','text':'那你看看'}])])
        self.assertEqual(d['messages'][0]['reply_participation']['priority'],'direct')
        self.assertEqual(d['messages'][2]['reply_participation']['priority'],'direct')
        self.send('direct','two',3)

    def test_named_call_is_direct_but_third_person_and_nickname_are_not(self):
        self.assertTrue(self.p.direct(message(1,'凯尔希，你看看')))
        self.assertTrue(self.p.direct(message(2,'老猫，干嘛呢')))
        self.assertFalse(self.p.direct(message(3,'我抽到凯尔希了')))
        m=message(4,'你好');m['sender']='@'+BOT+' 凯尔希'
        self.assertFalse(self.p.direct(m))

    def test_no_self_old_foreign_blank_or_unresolved_quote_opportunities(self):
        with patch.object(self.p,'sample',return_value=0):
            d=self.enrich([message(1,'old'),message(2,'哈哈',BOT),message(3,'哈哈',cid='other'),
                           message(4,''),message(5,'你在说啥',segments=[{'type':'reply','onebot_message_id':'unknown'}])],cursor=1)
        for r in d['messages'][:3]:self.assertNotIn('reply_participation',r)
        self.assertFalse(d['messages'][3]['reply_participation']['proactive_opportunity'])
        self.assertFalse(d['messages'][4]['reply_participation']['proactive_opportunity'])

    def test_five_minute_cooldown_and_half_hour_cap(self):
        self.send(key='one')
        with self.assertRaises(ValueError):self.send(key='too-soon')
        self.now+=300;self.send(key='two')
        self.now+=300
        with self.assertRaises(ValueError):self.send(key='four')
        self.send('direct','called',2)
        self.now=2800;self.send(key='after-window')

    def test_retry_stable_does_not_charge_another_slot_or_change_mode(self):
        self.send();self.send()
        self.assertEqual(len(self.p.attempts),1)
        with self.assertRaises(ValueError):self.send('direct')
        with self.assertRaises(ValueError):self.send(eid=2)

    def test_cooldown_survives_worker_restart(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'state.json'
            self.p=ChatParticipation(path,clock=lambda:self.now);self.send()
            restored=ChatParticipation(path,clock=lambda:self.now)
            self.assertEqual(restored.cooldown(),300)
            self.assertNotIn('content',json.dumps(json.loads(path.read_text())))

    def test_repeat_packet_does_not_reroll(self):
        a=self.enrich([message(1,'抽卡')])
        b=self.enrich([message(1,'抽卡')])
        self.assertEqual(a['messages'][0]['reply_participation'],b['messages'][0]['reply_participation'])

    def test_unsampled_proactive_send_is_rejected_but_direct_continues(self):
        with patch.object(self.p,'sample',return_value=.5):self.enrich([message(1,'肉鸽话题')])
        arguments={'session_id':SID,'idempotency_key':'not-selected','respond_to_event_id':1}
        with self.assertRaises(ValueError):self.p.admit(arguments,'proactive')
        self.p.admit(dict(arguments,idempotency_key='real-followup'),'direct')
        self.assertEqual(self.p.attempts,[])

if __name__=='__main__':unittest.main(verbosity=2)
