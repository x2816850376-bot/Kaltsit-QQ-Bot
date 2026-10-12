"""Native OneBot segments and exact delivered-event recipient binding, offline."""
from contextlib import contextmanager
import importlib.util
import json
from pathlib import Path
import sqlite3
import sys
import threading
from types import SimpleNamespace
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parent.parent
sys.path.insert(0,str(ROOT/'vendor/Tulpa'))
from chatlocal.message_sender import QQSender, SendError
from chatlocal.mcp_chat import MCPChat
from chat_address import DoctorAddress, PRESET


class NativeAtTests(unittest.TestCase):
    def test_sender_builds_native_at_and_keeps_cq_text_literal(self):
        sender=QQSender({'REPLY_ONEBOT_URL':'http://127.0.0.1:1','REPLY_ONEBOT_TOKEN':''})
        target={'conversation_id':'10000001:group:20000001','platform':'qq'}
        address={'account':'10000001','kind':'group','peer':'20000001','name':'群'}
        prepared=dict(address,quote_id=None,mention_user_id='12345')
        text='博士，这段[CQ:at,qq=all]只是文字'
        with patch.object(sender,'check_target',return_value=address),patch.object(sender,'call',return_value={'message_id':7}) as call:
            receipt=sender.send(target,text,prepared)
        segments=call.call_args.args[1]['message']
        self.assertEqual(segments,[{'type':'at','data':{'qq':'12345'}},{'type':'text','data':{'text':text}}])
        self.assertEqual(receipt['mention_user_id'],'12345')

    def test_invalid_all_or_private_mention_is_rejected(self):
        sender=QQSender({'REPLY_ONEBOT_URL':'http://127.0.0.1:1','REPLY_ONEBOT_TOKEN':''})
        for kind,uid in [('group','all'),('group','123,CQ'),('direct','12345')]:
            address={'account':'1','kind':kind,'peer':'2','name':'测试'}
            with patch.object(sender,'check_target',return_value=address),patch.object(sender,'call') as call:
                with self.assertRaises(SendError):sender.send({'conversation_id':'1:'+kind+':2'},'博士',dict(address,mention_user_id=uid))
                call.assert_not_called()

    def test_bound_recipient_and_qq_wire_have_visible_separator(self):
        role=DoctorAddress()
        role.observe({'session':{'id':'session','persona_preset':PRESET}})
        event={'id':5,'sender_id':'12345','sender':'晨星','is_self':False}
        hint=role.hint('session',event,{('session',5):event})
        sender=QQSender({'REPLY_ONEBOT_URL':'http://127.0.0.1:1','REPLY_ONEBOT_TOKEN':''})
        address={'account':'10000001','kind':'group','peer':'20000001','name':'群'}
        target={'conversation_id':'10000001:group:20000001','platform':'qq'}
        for i,body in enumerate(['在','先休息，博士','博士，我听着','\n下一行说话']):
            with self.subTest(body=body):
                rendered=role.prepare({'session_id':'session','respond_to_event_id':5,
                                       'idempotency_key':'space-'+str(i),'text':body},hint)
                with patch.object(sender,'check_target',return_value=address),patch.object(sender,'quote_id',return_value=19),patch.object(sender,'call',return_value={'message_id':7}) as call:
                    receipt=sender.send(target,rendered['text'],dict(address,quote_id=19,mention_user_id=hint['recipient']))
                wire=call.call_args.args[1]['message']
                self.assertEqual([s['type'] for s in wire],['reply','at','text'])
                self.assertEqual(wire[1]['data']['qq'],'12345')
                self.assertTrue(wire[2]['data']['text'][0].isspace())
                self.assertEqual(wire[2]['data']['text'],body if body[0].isspace() else ' '+body)
                self.assertEqual(receipt['content'],wire[2]['data']['text'])

    def fixture(self):
        db=sqlite3.connect(':memory:');db.row_factory=sqlite3.Row
        db.execute('CREATE TABLE chat_inbox(session_id TEXT,id INTEGER,payload TEXT)')
        event={'conversation_id':'10000001:group:20000001','sender_id':'12345','is_self':False,
               'reply_context':{'target':{'sender_id':'67890'}},'sender':'昵称含@全体成员'}
        db.execute('INSERT INTO chat_inbox VALUES(?,?,?)',('session',5,json.dumps(event)))
        @contextmanager
        def connect():yield db
        chat=object.__new__(MCPChat)
        row={'conversation_id':event['conversation_id'],'offered':5}
        chat.validate=lambda *a,**k:({'id':'grant'},row)
        chat.touch=lambda *a:None
        chat.access=SimpleNamespace(connect=connect)
        chat.receiver=SimpleNamespace(status=lambda:{'state':'connected','account':'10000001'})
        chat.live_target=lambda *a:None
        chat.receive=lambda *a:None
        actions=[]
        def execute(grant,kind,args,cancel,**kwargs):
            kwargs['guard']();actions.append(args)
            return {'state':'FAILED'}
        chat.actions=SimpleNamespace(execute=execute)
        return chat,db,actions

    def test_actual_sender_from_event_not_quote_or_display_name(self):
        chat,db,calls=self.fixture()
        chat.send({'id':'grant'},{'session_id':'session','text':'博士，在','idempotency_key':'native-key','mention_event_id':5},threading.Event())
        self.assertEqual(calls[0]['mention_user_id'],'12345')
        db.close()

    def test_unread_foreign_self_and_missing_events_are_rejected(self):
        for eid,event in [(6,None),(5,{'conversation_id':'other','sender_id':'12345'}),
                          (5,{'conversation_id':'10000001:group:20000001','sender_id':'10000001','is_self':True}),
                          (5,{'conversation_id':'10000001:group:20000001','sender_id':'all'})]:
            chat,db,calls=self.fixture()
            if event is not None:db.execute('UPDATE chat_inbox SET payload=?',(json.dumps(event),))
            with self.assertRaises(ValueError):chat.send({'id':'grant'},{'session_id':'session','text':'博士','idempotency_key':'native-key','mention_event_id':eid},threading.Event())
            self.assertEqual(calls,[]);db.close()
        chat,db,calls=self.fixture();db.execute('DELETE FROM chat_inbox')
        with self.assertRaises(ValueError):chat.send({'id':'grant'},{'session_id':'session','text':'博士','idempotency_key':'native-key','mention_event_id':5},threading.Event())
        self.assertEqual(calls,[]);db.close()


if __name__=='__main__':unittest.main()
