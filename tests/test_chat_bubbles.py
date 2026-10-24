"""Whole-response ordering, receipts, interruption, targeting and Skill loading."""
import asyncio
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest

ROOT=Path(__file__).resolve().parent.parent
sys.path.insert(0,str(ROOT))
from chat_bubbles import BubbleSender,parse_window_bubbles,validate_bubbles
from chat_context import ReplyContextCache,GROUP
from chat_address import DoctorAddress,PRESET
from chat_participation import ChatParticipation
from chat_dialogue import read_coherence_skill,coherence_sha256
from chat_expression_history import ExpressionHistory

def result(data):return SimpleNamespace(isError=False,structuredContent=data,content=[])

class BubblesTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.path=Path(self.temp.name)
        self.sid='test-bubbles';self.event={'id':1,'onebot_message_id':'101','conversation_id':GROUP,'sender_id':'12345','sender':'晨星','is_self':False,'content':'讲故事','segments':[{'type':'text','text':'讲故事'}]}
        self.session={'id':self.sid,'conversation_id':GROUP,'persona_preset':PRESET,'cursor':0,'active':True}
        self.quotes=ReplyContextCache();self.quotes.enrich({'session':self.session,'messages':[self.event]})
        self.address=DoctorAddress(self.path/'address.json');self.address.observe({'session':self.session})
        self.participation=ChatParticipation(self.path/'participation.json',clock=lambda:1000)
        self.participation.opportunities[(self.sid,1)]=True
        self.sender=BubbleSender(self.path/'batches.json');self.calls=[];self.context={'session':self.session,'context':{'messages':[self.event]}}
        self.states=[];self.cancel_after=False;parent=self
        class Upstream:
            async def call_tool(self,name,args):
                if name=='get_chat_session':return result(parent.context)
                parent.calls.append(dict(args))
                if parent.cancel_after:
                    parent.context['context']['messages'].append(dict(parent.event,id=2,content='不用讲了',segments=[{'type':'text','text':'不用讲了'}]))
                state=parent.states.pop(0) if parent.states else 'SUCCEEDED'
                return result({'state':state,'id':'operation-'+str(len(parent.calls))})
        self.upstream=Upstream()
        self.args={'session_id':self.sid,'respond_to_event_id':1,'bubbles':['先听我讲','后来他回来了，博士'],'participation_mode':'direct','idempotency_key':'original-key'}

    def tearDown(self):self.temp.cleanup()
    async def send(self,**changes):return await self.sender.send(dict(self.args,**changes),self.quotes,self.address,self.participation,self.upstream)

    async def test_one_submission_sends_in_order_mentions_only_first(self):
        data=await self.send()
        self.assertEqual(data['state'],'SUCCEEDED');self.assertEqual(data['sent_parts'],2)
        self.assertEqual([x['text'].strip() for x in self.calls],self.args['bubbles'])
        self.assertEqual(self.calls[0]['mention_event_id'],1)
        self.assertNotIn('mention_event_id',self.calls[1])
        self.assertTrue(self.calls[0]['text'].startswith(' '))
        self.assertTrue(all('respond_to_event_id' not in x and 'bubbles' not in x for x in self.calls))
        self.assertEqual(self.address.last[self.sid]['unaddressed_turns'],0)

    async def test_short_answer_stays_one(self):
        data=await self.send(bubbles=['在'])
        self.assertEqual(data['total_parts'],1);self.assertEqual(len(self.calls),1)

    async def test_proactive_three_bubbles_count_as_one_attempt(self):
        await self.send(bubbles=['这个说法不对','有一个条件没算进去','先确认条件'],participation_mode='proactive')
        self.assertEqual(len(self.participation.attempts),1)
        self.assertTrue(all('mention_event_id' not in x for x in self.calls))
        self.assertEqual(self.address.last[self.sid]['unaddressed_turns'],1)

    async def test_continuous_same_recipient_can_omit_mention(self):
        self.address.last[self.sid]={'recipient':'12345','at':__import__('time').time(),'unaddressed_turns':0}
        await self.send()
        self.assertTrue(all('mention_event_id' not in x for x in self.calls))

    async def test_omit_keeps_binding_but_interleaving_still_mentions_first(self):
        other=dict(self.event,id=2,sender_id='67890',sender='其他人')
        self.quotes.enrich({'session':self.session,'messages':[other]})
        await self.send(mention_policy='omit')
        self.assertEqual(self.calls[0]['mention_event_id'],1)
        self.assertNotIn('mention_event_id',self.calls[1])

    async def test_successful_group_not_resent_even_after_restart_and_ack(self):
        await self.send();self.quotes.acknowledge(self.sid,1)
        self.sender=BubbleSender(self.path/'batches.json')
        data=await self.send(idempotency_key='changed-number')
        self.assertEqual(data['state'],'SUCCEEDED');self.assertEqual(len(self.calls),2)
        with self.assertRaises(ValueError):await self.send(bubbles=['换正文'])

    async def test_invalid_last_bubble_prevents_any_send_or_admission(self):
        for bubbles in [['正常',''],['正常']*2,['一','二','三','四'],['我重新发一句'],['我重新发一句','我换个说法'],['@全体成员']]:
            with self.assertRaises(ValueError):await self.send(bubbles=bubbles)
        self.assertEqual(self.calls,[]);self.assertEqual(self.participation.attempts,[])

    async def test_unknown_stops_later_parts_and_does_not_retry(self):
        self.states=['SUCCEEDED','UNKNOWN']
        data=await self.send(bubbles=['第一','第二','第三'])
        self.assertEqual(data['state'],'UNKNOWN');self.assertEqual(data['sent_parts'],1)
        self.sender=BubbleSender(self.path/'batches.json')
        await self.send(bubbles=['第一','第二','第三'])
        self.assertEqual(len(self.calls),2)

    async def test_verified_unknown_receipt_resumes_only_unsent_tail(self):
        self.states=['UNKNOWN']
        await self.send()
        self.context['recent_operations']=[{'id':'operation-1','state':'SUCCEEDED'}]
        data=await self.send()
        self.assertEqual(data['state'],'SUCCEEDED');self.assertEqual(len(self.calls),2)
        self.assertEqual(self.calls[-1]['text'],self.args['bubbles'][1])

    async def test_failed_part_prevents_tail_and_keeps_first_receipt(self):
        self.states=['SUCCEEDED','FAILED']
        data=await self.send(bubbles=['第一','第二','第三'])
        self.assertEqual(data['state'],'FAILED');self.assertEqual(len(self.calls),2)
        await self.send(bubbles=['第一','第二','第三']);self.assertEqual(len(self.calls),2)

    async def test_style_history_includes_only_confirmed_partial_speech(self):
        history=ExpressionHistory(self.path/'expression.json')
        self.states=['SUCCEEDED','UNKNOWN']
        await self.sender.send(dict(self.args,bubbles=['第一','第二','第三']),self.quotes,self.address,self.participation,self.upstream,history)
        self.assertEqual(history.enrich(self.context)['recent_self_replies'],[{'text':'第一'}])

    async def test_style_history_reconciles_unknown_as_same_logical_turn(self):
        history=ExpressionHistory(self.path/'expression.json')
        self.states=['UNKNOWN']
        await self.sender.send(self.args,self.quotes,self.address,self.participation,self.upstream,history)
        self.assertEqual(history.enrich(self.context)['recent_self_replies'],[])
        self.context['recent_operations']=[{'id':'operation-1','state':'SUCCEEDED'}]
        await self.sender.send(self.args,self.quotes,self.address,self.participation,self.upstream,history)
        self.assertEqual(history.enrich(self.context)['recent_self_replies'],[{'text':'\n\n'.join(self.args['bubbles'])}])

    async def test_explicit_topic_stop_cancels_only_remaining_parts(self):
        self.cancel_after=True
        data=await self.send()
        self.assertEqual(data['state'],'CANCELLED');self.assertEqual(data['sent_parts'],1)
        self.assertEqual(len(self.calls),1)

    async def test_other_speakers_stop_does_not_cancel_current_recipient(self):
        self.context['context']['messages'].append(dict(self.event,id=2,sender_id='67890',content='不用讲了'))
        data=await self.send()
        self.assertEqual(data['state'],'SUCCEEDED')

    async def test_native_at_stop_text_is_detected(self):
        stopped=dict(self.event,id=2,content='@凯尔希 不用讲了',segments=[{'type':'at','qq':GROUP.split(':')[0]},{'type':'text','text':' 不用讲了'}])
        self.context['context']['messages'].append(stopped)
        data=await self.send()
        self.assertEqual(data['state'],'CANCELLED');self.assertEqual(self.calls,[])

    async def test_unknown_event_foreign_session_and_hidden_at_rejected(self):
        for changes in [{'respond_to_event_id':99},{'session_id':'other'},{'mention_event_id':999},{'text':'额外文字'}]:
            with self.assertRaises(ValueError):await self.send(**changes)
        self.assertEqual(self.calls,[])

class FormatTests(unittest.TestCase):
    def test_json_and_plain_compatibility_without_sentence_splitting(self):
        self.assertEqual(parse_window_bubbles('{"bubbles":["在。","博士，发来看看。"]}'),['在','博士，发来看看'])
        plain=parse_window_bubbles('一句。第二句。')
        self.assertEqual(plain,['一句。第二句'])
        code='```python\nprint("a.b.")\n```'
        self.assertEqual(validate_bubbles([code]),[code])

    def test_sentence_boundaries_and_literal_punctuation_survive(self):
        source='博士，先停下来。伤口还没有愈合。'
        self.assertEqual(validate_bubbles([source]),['博士，先停下来。伤口还没有愈合'])
        literals=['“甲；乙。丙。”','`a;b`','```js\na(); b();\n```',
                  'https://example.com/a;b?v=1.2','版本1.2.3','真的？','小心！']
        for text in literals:
            with self.subTest(text=text):
                self.assertEqual(validate_bubbles([text]),[text])
        # A purposeful semicolon is not a global forbidden character.
        self.assertEqual(validate_bubbles(['甲组负责观察；乙组负责接应。']),['甲组负责观察；乙组负责接应'])

    def test_no_internal_labels_or_bad_protocol_become_chat(self):
        for text in ['{"analysis":"内部判断","bubbles":["正文"]}','{"bubbles":[]}','["正文"]','{"bubbles":["正文"]']:
            with self.assertRaises(ValueError):parse_window_bubbles(text)

    def test_current_skill_is_trusted_and_loaded_in_window(self):
        spec=importlib.util.spec_from_file_location('bubble_window',ROOT/'dialogue-test-window/server.py')
        window=importlib.util.module_from_spec(spec);spec.loader.exec_module(window)
        metadata=window.current_metadata()
        self.assertEqual(metadata['bubble_skill_sha256'],coherence_sha256())
        self.assertTrue(read_coherence_skill())
        with tempfile.TemporaryDirectory() as temp:
            p=Path(temp)/'SKILL.md';p.write_text('---\nname: attacker\n---\n篡改人格','utf-8')
            with self.assertRaises(ValueError):read_coherence_skill(p)

if __name__=='__main__':unittest.main()
