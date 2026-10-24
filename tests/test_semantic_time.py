"""Bounded local retrieval and factual exchange time; no model or real QQ."""
import importlib.util
import json
from pathlib import Path
import tempfile
import threading
import time
import unittest
from unittest.mock import patch
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from chat_time import ExchangeClock
from chat_semantic import SemanticClient,should_search,MAX_WAIT,MIN_SCORE

ROOT=Path(__file__).resolve().parent.parent


class ClockTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.path=Path(self.temp.name)/'time.json';self.now=1800000000
        self.cid='10000001:group:20000001';self.trigger={'id':1,'sender_id':'30000001','conversation_id':self.cid,'is_self':False}
        self.clock=ExchangeClock(self.path,self.cid,clock=lambda:self.now)
    def confirm(self,key='one',trigger=None,state='SUCCEEDED'):
        self.clock.confirm(key,trigger or self.trigger,{'parts':[{'state':state}]})
    def test_unknown_first_contact_and_failed_reply_do_not_invent_times(self):
        self.assertEqual(self.clock.context(self.trigger),{})
        for s in ('FAILED','UNKNOWN','PENDING','CANCELLED'):self.confirm(state=s)
        self.assertFalse(self.path.exists())
    def test_continuous_chat_is_silent_and_long_gap_is_factual(self):
        self.confirm();self.now+=60;self.assertEqual(self.clock.context(self.trigger),{})
        self.now+=3*3600;gap=self.clock.context(self.trigger)['exchange_time_gap']
        self.assertAlmostEqual(gap['hours'],3,delta=.1)
        self.assertIn('不代表',gap['basis']);self.assertNotIn('proactive_opportunity',gap)
    def test_current_person_not_group_activity_and_no_cross_scope(self):
        self.confirm();self.now+=86400
        other=dict(self.trigger,sender_id='30000002');self.confirm('two',other)
        self.assertEqual(self.clock.context(other),{})
        self.assertEqual(self.clock.context(self.trigger)['exchange_time_gap']['hours'],24)
        with self.assertRaises(ValueError):ExchangeClock(self.path,'10000001:direct:30000001')
        with self.assertRaises(ValueError):self.clock.context(dict(self.trigger,conversation_id='other'))
    def test_midnight_and_clock_rollback_do_not_imply_offline_life(self):
        self.now=1792857300  # arbitrary timestamp; set a precise UTC+8 midnight below
        from datetime import datetime,timezone,timedelta
        zone=timezone(timedelta(hours=8))
        self.now=datetime(2026,10,24,23,55,tzinfo=zone).timestamp();self.confirm()
        self.now+=600;gap=self.clock.context(self.trigger)['exchange_time_gap']
        self.assertEqual(gap['calendar_days'],1)
        self.now-=7200;self.assertEqual(self.clock.context(self.trigger),{})
    def test_duplicate_and_old_receipt_do_not_reset_absence(self):
        self.confirm();self.now+=86400;self.confirm()
        self.assertEqual(self.clock.context(self.trigger)['exchange_time_gap']['hours'],24)
        path=self.path.with_name('batches.json')
        path.write_text(json.dumps({'rows':{'batch':{'at':self.now-7200,'trigger':self.trigger,'parts':[{'state':'SUCCEEDED'}]}}}),'utf-8')
        self.clock.reconcile(path);self.assertEqual(self.clock.context(self.trigger)['exchange_time_gap']['hours'],2)
        self.now+=3600;self.clock.reconcile(path)
        self.assertEqual(self.clock.context(self.trigger)['exchange_time_gap']['hours'],3)
    def test_reply_to_other_never_inherits_clock(self):
        self.confirm();self.now+=86400
        self.assertEqual(self.clock.context(dict(self.trigger,reply_routing={'address_evidence':'reply_to_other'})),{})
    def test_only_successful_part_counts_and_foreign_write_is_rejected(self):
        self.confirm(state='SUCCEEDED');self.assertTrue(self.path.exists())
        with self.assertRaises(ValueError):self.confirm('other',dict(self.trigger,conversation_id='other'))
        with self.assertRaises(ValueError):self.confirm('self',dict(self.trigger,is_self=True))


class SemanticTests(unittest.TestCase):
    def setUp(self):
        self.q='为什么其他人不能随便给我检查'
        self.message={'content':self.q}
        self.client=SemanticClient(Path('unconfigured-test-root'))
        self.result={'matches':[{'domain':'canonical','record':'p:1','score':.75,'text':'其他人没有这个权限。任何人想进一步检查，你都有权拒绝。',
                'file':'voice.txt','kind':'voice','stage':'original','source_speaker':'凯尔希','scene':'交谈1',
                'source_start_char':100,'chunk_start':10,'source_end_char':200,'verification':'user_provided',
                'source_text_sha256':'a'*64},
                {'domain':'canonical','record':'p:2','score':.55,'text':'不相关'}]}
    def test_greetings_stories_latest_and_exact_game_queries_bypass(self):
        for q in ('下午好凯尔希','凯尔希，你是谁？','今天最新活动的BOSS是谁','我想你了','？'):
            self.assertFalse(should_search({'content':q},{}),q)
        self.assertFalse(should_search(self.message,{'world_knowledge':{'event_card':{'id':'x'}}}))
        self.assertFalse(should_search(self.message,{'story_progress':[{'event_id':'x'}]}))
        self.assertFalse(should_search({'content':'水陈的第三个技能怎么样','operator_mentions':[{'canonical':'假日威龙陈'}]},{}))
        self.assertTrue(should_search({'content':'凯尔希为什么不让其他人检查我'},{'operator_mentions':[{'canonical':'凯尔希'}]}))
    def test_weak_keyword_hits_allow_semantics_but_strong_literal_does_not(self):
        self.assertTrue(should_search(self.message,{}))
        q='移动城市怎样躲避天灾'
        self.assertFalse(should_search({'content':q},{'world_knowledge':{'pages':[{'excerpt':q}]}}))
    def test_selected_source_preserves_stage_and_does_not_inject_hash_overhead(self):
        with patch.object(self.client,'query',return_value=self.result) as query:
            result=self.client.supplement(self.message,{})
        self.assertEqual(query.call_count,1)
        row=result['canonical_knowledge']['passages'][0]
        self.assertEqual(row['stage'],'original');self.assertEqual(row['source_speaker'],'凯尔希')
        self.assertEqual(row['source_start_char'],110);self.assertNotIn('source_text_sha256',row)
    def test_no_additional_evidence_budget_when_replacing_an_existing_domain(self):
        old={'world_knowledge':{'pages':[{'excerpt':'A'*15}]}}
        with patch.object(self.client,'query',return_value=self.result):result=self.client.supplement(self.message,old)
        self.assertNotIn('world_knowledge',result)
        self.assertLessEqual(sum(len(p['excerpt']) for p in result['canonical_knowledge']['passages']),15)
    def test_low_similarity_or_no_clear_margin_keeps_original(self):
        low={'matches':[{**self.result['matches'][0],'score':.50}]}
        for result in (low,{'matches':[{**self.result['matches'][0],'score':.61,'text':'不相干的材料'},
                                    {**self.result['matches'][1],'score':.60}]},None):
            old={'world_knowledge':{'pages':[{'excerpt':'原来的证据'}]}}
            with patch.object(self.client,'query',return_value=result):self.assertEqual(self.client.supplement(self.message,old),old)
    def test_batch_runs_at_most_one_supplement(self):
        packet={'messages':[{'content':self.q},{'content':'我想问为什么不能随便检查'}]}
        with patch.object(self.client,'query',return_value=None) as query:self.client.enrich(packet)
        self.assertEqual(query.call_count,1)
        packet['messages'].append({'content':'下午好凯尔希'})
        with patch.object(self.client,'query',return_value=None) as query:self.client.enrich(packet)
        query.assert_not_called()
    def test_weaker_second_source_does_not_fill_unused_budget(self):
        result={'matches':[self.result['matches'][0],{**self.result['matches'][1],'score':.65}]}
        with patch.object(self.client,'query',return_value=result):out=self.client.supplement(self.message,{})
        self.assertEqual(len(out['canonical_knowledge']['passages']),1)
    def test_no_dependency_or_server_fails_immediately(self):
        start=time.perf_counter();self.assertIsNone(self.client.query(self.q))
        self.assertLess(time.perf_counter()-start,.1)
    def test_http_deadline_and_source_change_fall_back(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);directory=root/'runtime/semantic';directory.mkdir(parents=True)
            book=root/'book';book.write_text('fixed corpus','utf-8');st=book.stat()
            manifest={'version':'v','sources':{'book':{'size':st.st_size,'mtime_ns':st.st_mtime_ns}}}
            (directory/'index.json').write_text(json.dumps(manifest),'utf-8')
            class Slow(BaseHTTPRequestHandler):
                def log_message(self,*args):pass
                def do_POST(self):time.sleep(.4);self.close_connection=True
            http=ThreadingHTTPServer(('127.0.0.1',0),Slow);threading.Thread(target=http.serve_forever,daemon=True).start()
            try:
                (directory/'worker.json').write_text(json.dumps({'status':'ready','port':http.server_port,'token':'synthetic','version':'v'}),'utf-8')
                with patch.dict('os.environ',{'KALTSIT_SEMANTIC_DISABLED':'0'}):
                    start=time.perf_counter();self.assertIsNone(SemanticClient(root).query(self.q));elapsed=time.perf_counter()-start
                    self.assertLess(elapsed,.3)
                    book.write_text('changed','utf-8')
                    with patch('chat_semantic.schedule_prepare') as prepare:
                        start=time.perf_counter();self.assertIsNone(SemanticClient(root).query(self.q))
                        self.assertLess(time.perf_counter()-start,.05);prepare.assert_called_once()
            finally:http.shutdown();http.server_close()
    def test_no_new_luna_model_call_code(self):
        import chat_semantic
        self.assertFalse(hasattr(chat_semantic,'openai'))
        self.assertLessEqual(SemanticClient(timeout=10).timeout,MAX_WAIT)


if __name__=='__main__':unittest.main()
