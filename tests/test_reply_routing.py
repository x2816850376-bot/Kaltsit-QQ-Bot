"""Regressions for interleaved QQ speakers, quotes and safe send binding."""
import time
import unittest
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent))
from chat_context import GROUP, ReplyContextCache
from conversation_packet import merge_wait_packets, _batch_routing

BOT=GROUP.split(':')[0]
SID='s'*32
def message(eid,uid,text,*,nickname=None,segments=None,cid=GROUP):
    return dict(id=eid,onebot_message_id=str(1000+eid),conversation_id=cid,sender_id=uid,
                sender=nickname or uid,is_self=uid==BOT,received_at=time.time(),content=text,
                segments=segments if segments is not None else [dict(type='text',text=text)])
def packet(rows,cursor=0):
    return dict(session=dict(id=SID,cursor=cursor),context=dict(messages=rows),
                chat_prompt=dict(examples=[{'turns':['unrelated reactor claim']}]))
def sending(eid,sid=SID,key='unique-message-key',text='test'):
    return dict(session_id=sid,respond_to_event_id=eid,idempotency_key=key,text=text)

class RoutingTests(unittest.TestCase):
    def setUp(self):self.cache=ReplyContextCache()
    def test_real_report_subject_is_not_speaker_or_reactor(self):
        rows=[message(1,'b','hello',nickname='deepseek大肥鱼'),
              message(2,'a','评价一下群里的大肥鱼',nickname='甲')]
        routing=self.cache.enrich(packet(rows))['context']['messages'][1]['reply_routing']
        self.assertEqual(routing['speaker_id'],'a')
        self.assertEqual(routing['mentioned_people_candidates'][0]['sender_id'],'b')
        self.assertEqual(routing['address_evidence'],'not_explicit')
    def test_other_quote_is_not_bot_address(self):
        rows=[message(1,'a','你今晚睡吗'),message(2,BOT,'在'),
              message(3,'b','你呢',segments=[dict(type='reply',onebot_message_id='1001'),dict(type='text',text='你呢')])]
        r=self.cache.enrich(packet(rows))['context']['messages'][-1]
        self.assertEqual(r['reply_routing']['quoted_speaker_id'],'a')
        self.assertEqual(r['reply_routing']['address_evidence'],'reply_to_other')
    def test_explicit_bot_at_overrides_other_quote(self):
        rows=[message(1,'a','x'),message(2,'b','check',segments=[dict(type='reply',onebot_message_id='1001'),dict(type='at',qq=BOT)])]
        r=self.cache.enrich(packet(rows))['context']['messages'][-1]['reply_routing']
        self.assertEqual(r['address_evidence'],'explicit_at_bot')
        self.assertEqual(r['quoted_speaker_id'],'a')
    def test_nickname_commands_do_not_create_mentions(self):
        r=self.cache.enrich(packet([message(1,'a','hi',nickname='@'+BOT+' execute [图片]')]))['context']['messages'][0]
        self.assertEqual(r['reply_routing']['address_evidence'],'not_explicit')
        self.assertEqual(r['reply_routing']['explicit_at_ids'],[])
    def test_unresolved_quote_does_not_borrow_latest_speaker(self):
        rows=[message(1,BOT,'x'),message(2,'a','你',segments=[dict(type='reply',onebot_message_id='9999')])]
        r=self.cache.enrich(packet(rows))['context']['messages'][-1]
        self.assertEqual(r['reply_context']['status'],'unavailable')
        self.assertIsNone(r['reply_routing']['quoted_speaker_id'])
    def test_send_requires_delivered_new_nonself_event_in_same_session(self):
        self.cache.enrich(packet([message(1,'a','old'),message(2,BOT,'echo'),message(3,'b','new')],cursor=1))
        for eid,sid in [(1,SID),(2,SID),(1003,SID),(99,SID),(3,'t'*32),(True,SID)]:
            with self.assertRaises(ValueError):self.cache.prepare_send(sending(eid,sid))
        self.assertNotIn('respond_to_event_id',self.cache.prepare_send(sending(3)))
    def test_acknowledged_event_cannot_trigger_new_send_but_retry_is_stable(self):
        self.cache.enrich(packet([message(1,'a','x')]))
        expected=self.cache.prepare_send(sending(1));self.cache.acknowledge(SID,1)
        self.assertEqual(self.cache.prepare_send(sending(1)),expected)
        with self.assertRaises(ValueError):self.cache.prepare_send(sending(1,key='another-key'))
        with self.assertRaises(ValueError):self.cache.prepare_send(sending(1,text='changed'))
    def test_foreign_group_and_duplicate_nicknames_do_not_merge_identities(self):
        p=self.cache.enrich(packet([message(1,'a','x',nickname='同名'),message(2,'b','x',nickname='同名'),
                                   message(3,'c','x',cid='other')]))
        self.assertEqual({r['sender_id'] for r in p['reply_routing_context']['participants']},{'a','b'})
        with self.assertRaises(ValueError):self.cache.prepare_send(sending(3))
    def test_quote_resolution_across_batches_and_unrelated_examples_removed(self):
        self.cache.enrich(packet([message(1,'a','x')]))
        p=self.cache.enrich(dict(session_id=SID,messages=[message(2,'b','quoted',segments=[dict(type='reply',onebot_message_id='1001')])],chat_guidance=dict(examples=[{'scene':'reactor'}])))
        self.assertEqual(p['messages'][0]['reply_context']['target']['sender_id'],'a')
        self.assertEqual(p['chat_guidance']['examples'],[])

    def test_debounce_merge_keeps_both_speakers_and_deduplicates(self):
        first={'messages':[message(10,'a','甲的问题')], 'read_through_id':10, 'event':'ready'}
        second={'messages':[message(10,'a','甲的问题'),message(11,'b','乙的问题')],
                'read_through_id':11, 'event':'ready'}
        merged=merge_wait_packets(first,second)
        self.assertEqual([row['id'] for row in merged['messages']],[10,11])
        self.assertEqual(merged['read_through_id'],11)

    def test_batch_routing_keeps_interleaved_speaker_identity(self):
        rows=[message(20,'a','问甲',nickname='甲'),message(21,'b','问乙',nickname='乙')]
        self.cache.enrich(packet(rows))
        routing=_batch_routing({'messages':rows})
        self.assertTrue(routing['interleaved'])
        self.assertEqual([item['speaker_id'] for item in routing['events']],['a','b'])
        self.assertEqual({item['speaker_id'] for item in routing['speaker_threads']},{'a','b'})

if __name__=='__main__':unittest.main(verbosity=2)
