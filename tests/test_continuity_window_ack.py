"""Browser acknowledgement, retry and origin isolation without model or QQ."""
import importlib.util
import json
from pathlib import Path
import tempfile
import threading
from types import SimpleNamespace
import unittest
from unittest.mock import patch, Mock
from urllib.request import build_opener, ProxyHandler, Request
from urllib.error import HTTPError
from http.server import ThreadingHTTPServer
from chat_continuity import ConversationContinuity
from chat_social import ConversationSocial

ROOT=Path(__file__).resolve().parent.parent


class WindowAckTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name);self.identity='a'*32;self.scope='test:'+self.identity
        spec=importlib.util.spec_from_file_location('ack_window',ROOT/'dialogue-test-window/server.py')
        self.server=importlib.util.module_from_spec(spec);spec.loader.exec_module(self.server)
        def store(scope):return ConversationContinuity(self.root/(scope[5:]+'.json'),scope,'role')
        self.make_store=store
        self.addCleanup(patch.stopall)
        patch.object(self.server,'continuity_store',side_effect=store).start()
        patch.object(self.server,'social_store',side_effect=lambda scope:ConversationSocial(self.root/(scope[5:]+'.social.json'),scope,'role')).start()
        self.http=ThreadingHTTPServer(('127.0.0.1',0),self.server.Handler)
        self.port=self.http.server_port;patch.object(self.server,'PORT',self.port).start()
        self.thread=threading.Thread(target=self.http.serve_forever,daemon=True);self.thread.start()
        self.addCleanup(self.http.server_close);self.addCleanup(self.http.shutdown)
        self.opener=build_opener(ProxyHandler({}))

    def post(self,path,body,origin=None):
        url=f'http://127.0.0.1:{self.port}'
        request=Request(url+path,json.dumps(body).encode(),{'Content-Type':'application/json','Origin':origin or url})
        try:
            with self.opener.open(request,timeout=5) as response:return response.status,json.load(response)
        except HTTPError as response:return response.code,json.load(response)

    def staged(self):
        store=self.make_store(self.scope)
        trigger={'id':1,'sender_id':'test:博士','conversation_id':self.scope,'content':'一会发给你','is_self':False}
        update={'followups':[{'topic':'阵容','awaiting':'阵容截图','status':'pending','user_quote':'一会发给你','bubble':0}]}
        store.stage('b'*32,trigger,update,['发来后我看看']);return store

    def test_only_display_acknowledgement_confirms_and_retries_are_idempotent(self):
        store=self.staged();self.assertFalse(store.data['followups'])
        body={'test_id':self.identity,'delivery_id':'b'*32}
        status,_=self.post('/chat/ack',body);self.assertEqual(status,200)
        self.assertEqual(len(self.make_store(self.scope).data['followups']),1)
        self.assertEqual(self.post('/chat/ack',body)[0],200)
        self.assertEqual(len(self.make_store(self.scope).data['followups']),1)

    def test_cross_origin_foreign_scope_and_unknown_ack_are_rejected(self):
        self.staged();body={'test_id':self.identity,'delivery_id':'b'*32}
        self.assertEqual(self.post('/chat/ack',body,'http://evil.invalid')[0],403)
        self.assertEqual(self.post('/chat/ack',{**body,'test_id':'c'*32})[0],400)
        self.assertEqual(self.post('/chat/ack',{**body,'delivery_id':'d'*32})[0],400)
        self.assertFalse(self.make_store(self.scope).data['followups'])

    def test_restart_clears_only_owned_continuity_not_other_window(self):
        self.staged();self.assertEqual(self.post('/social/reset',{'test_id':self.identity})[0],200)
        self.assertFalse(self.make_store(self.scope).data['deliveries'])
        self.assertEqual(self.post('/chat/ack',{'test_id':self.identity,'delivery_id':'b'*32})[0],400)

    def test_one_generation_stages_but_does_not_confirm_before_display(self):
        update={'followups':[{'topic':'阵容','awaiting':'阵容截图','status':'pending','user_quote':'一会发给你','bubble':0}]}
        runner=SimpleNamespace(run_turn=Mock(return_value=(json.dumps({'bubbles':['发来之后我看看'],'continuity_update':update}),[],.1)))
        original=self.server.load_module
        def modules(name,path):return runner if name=='test_model_stream' else original(name,path)
        worker=SimpleNamespace(cli_args=lambda:['fake','-'])
        with patch.object(self.server,'load_current_runtime',return_value=worker),patch.object(self.server,'load_module',side_effect=modules),patch.object(self.server,'current_metadata',return_value={}):
            result=self.server.generate({'nickname':'博士','message':'一会发给你','test_id':self.identity})
        self.assertEqual(runner.run_turn.call_count,1)
        self.assertEqual(len(result['delivery_id']),32)
        store=self.make_store(self.scope);self.assertFalse(store.data['followups']);self.assertEqual(len(store.data['deliveries']),1)
        self.assertEqual(self.post('/chat/ack',{'test_id':self.identity,'delivery_id':result['delivery_id']})[0],200)
        self.assertEqual(len(self.make_store(self.scope).data['followups']),1)

    def test_unsupported_memory_cannot_erase_or_retry_completed_reply(self):
        update={'followups':[{'topic':'阵容','awaiting':'截图','status':'pending','user_quote':'没有出现过的引文','bubble':0}]}
        runner=SimpleNamespace(run_turn=Mock(return_value=(json.dumps({'bubbles':['好，博士'],'continuity_update':update}),[],.1)))
        original=self.server.load_module
        def modules(name,path):return runner if name=='test_model_stream' else original(name,path)
        with patch.object(self.server,'load_current_runtime',return_value=SimpleNamespace(cli_args=lambda:['fake','-'])),patch.object(self.server,'load_module',side_effect=modules),patch.object(self.server,'current_metadata',return_value={}):
            result=self.server.generate({'nickname':'博士','message':'一会发给你','test_id':self.identity})
        self.assertEqual(result['reply'],'好，博士');self.assertIsNone(result['delivery_id'])
        self.assertEqual(runner.run_turn.call_count,1)
        self.assertFalse(self.make_store(self.scope).data['followups'])

    def test_ordinary_greeting_records_exchange_only_after_display(self):
        runner=SimpleNamespace(run_turn=Mock(return_value=(json.dumps({'bubbles':['下午好，博士']}),[],.1)))
        original=self.server.load_module
        def modules(name,path):return runner if name=='test_model_stream' else original(name,path)
        with patch.object(self.server,'load_current_runtime',return_value=SimpleNamespace(cli_args=lambda:['fake','-'])),patch.object(self.server,'load_module',side_effect=modules),patch.object(self.server,'current_metadata',return_value={}):
            result=self.server.generate({'nickname':'博士','message':'下午好凯尔希','test_id':self.identity})
        self.assertEqual(runner.run_turn.call_count,1)
        self.assertEqual(len(result['delivery_id']),32)
        self.assertFalse(self.server.exchange_clock(self.scope).data['people'])
        self.assertEqual(self.post('/chat/ack',{'test_id':self.identity,'delivery_id':result['delivery_id']})[0],200)
        self.assertIn('test:博士',self.server.exchange_clock(self.scope).data['people'])


if __name__=='__main__':unittest.main()
