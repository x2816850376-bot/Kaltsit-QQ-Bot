"""Local salutation regressions; no model, network or QQ sends."""
import json
from pathlib import Path
import sys
import tempfile
import time
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parent))
from chat_address import DoctorAddress, PRESET
from chat_context import ReplyContextCache, GROUP

SID='address-session'
def event(eid,uid,name='晨星',text='在吗'):
    return dict(id=eid,onebot_message_id=str(1000+eid),conversation_id=GROUP,
                sender_id=uid,sender=name,content=text,is_self=False,
                received_at=time.time(),segments=[dict(type='text',text=text)])
def args(eid=1,text='在，说吧',key='k1'):
    return dict(session_id=SID,respond_to_event_id=eid,idempotency_key=key,text=text)

class AddressTests(unittest.TestCase):
    def setUp(self):
        self.role=DoctorAddress()
        self.role.observe(dict(session=dict(id=SID,persona_preset=PRESET)))
        self.row=event(1,'a')
        self.pending={(SID,1):self.row}
    def render(self,arguments,row=None):
        return self.role.prepare(arguments,self.role.hint(SID,row or self.row,self.pending))
    def test_first_reply_is_not_forced_into_a_salutation(self):
        self.assertEqual(self.render(args())['text'],'在，说吧')
    def test_already_addressed_is_unchanged(self):
        self.assertEqual(self.render(args(text='博士，在'))['text'],'博士，在')
    def test_continuous_same_person_is_not_prefixed_each_time(self):
        self.role.commit(self.render(args()))
        self.assertEqual(self.render(args(2,'发来','k2'))['text'],'发来')
    def test_changed_recipient_does_not_force_address(self):
        self.role.commit(self.render(args()))
        row=event(2,'b','蓝莓')
        self.pending={(SID,2):row}
        self.assertEqual(self.render(args(2,'我听着','k2'),row)['text'],'我听着')
    def test_multiple_speakers_keep_doctor_not_nickname(self):
        self.pending[(SID,2)]=event(2,'b','蓝莓')
        self.row['reply_context']={'target':{'sender_id':'b','sender':'蓝莓'}}
        self.assertEqual(self.render(args())['text'],'在，说吧')
    def test_generic_doctor_not_replaced_by_nickname(self):
        self.pending[(SID,2)]=event(2,'b','蓝莓')
        self.assertEqual(self.render(args(text='博士，我听着'))['text'],'博士，我听着')
    def test_direct_reply_gets_native_event_binding_not_quoted_sender(self):
        self.row['sender_id']='12345'
        self.row['reply_context']={'target':{'sender_id':'67890','sender':'蓝莓'}}
        rendered=self.render(args(text='晨星博士，在'))
        self.assertEqual(rendered['text'],' 博士，在')
        self.assertEqual(rendered['mention_event_id'],1)
    def test_proactive_hint_does_not_mention(self):
        self.row['sender_id']='12345'
        hint=self.role.hint(SID,self.row,self.pending)
        hint.update(required=False,mention_event_id=None)
        rendered=self.role.prepare(args(text='这个不错'),hint)
        self.assertNotIn('mention_event_id',rendered)
        self.assertEqual(rendered['text'],'这个不错')
    def test_native_at_stays_stable_after_restart(self):
        self.row['sender_id']='12345'
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'state.json'
            self.role=DoctorAddress(path);self.role.observe(dict(session=dict(id=SID,persona_preset=PRESET)))
            first=self.render(args());self.role.commit(first)
            self.role=DoctorAddress(path);self.role.observe(dict(session=dict(id=SID,persona_preset=PRESET)))
            self.assertEqual(self.render(args()),first)
    def test_wrong_named_addressee_is_not_silently_retargeted(self):
        self.pending[(SID,2)]=event(2,'b','蓝莓')
        with self.assertRaises(ValueError):self.render(args(text='蓝莓博士，刚才那句我听到了'))
    def test_punctuation_and_next_reply_do_not_force_address(self):
        rendered=self.render(args(text='？'));self.role.commit(rendered)
        self.assertEqual(rendered['text'],'？')
        self.assertEqual(self.render(args(2,'发来','k2'))['text'],'发来')
    def test_retry_is_stable_across_process_restart(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'state.json'
            self.role=DoctorAddress(path)
            self.role.observe(dict(session=dict(id=SID,persona_preset=PRESET)))
            first=self.render(args());self.role.commit(first)
            self.role=DoctorAddress(path)
            self.role.observe(dict(session=dict(id=SID,persona_preset=PRESET)))
            self.assertEqual(self.render(args()),first)
            with self.assertRaises(ValueError):
                self.render(args(text='changed'))
    def test_other_persona_and_unread_event_are_not_modified_or_sent(self):
        self.role.observe(dict(session=dict(id=SID,persona_preset='other')))
        self.assertEqual(self.render(args())['text'],'在，说吧')
        cache=ReplyContextCache()
        with self.assertRaises(ValueError):
            cache.prepare_send(args())
    def test_hints_are_only_for_eligible_delivered_events(self):
        data=dict(session=dict(id=SID,persona_preset=PRESET),
                  context=dict(messages=[event(0,'old'),self.row]))
        enriched=self.role.enrich(data,self.pending)
        self.assertNotIn('role_address',enriched['context']['messages'][0])
        hint=enriched['context']['messages'][1]['role_address']
        self.assertEqual(hint['title'],'博士')
        self.assertFalse(hint['required'])
        self.assertTrue(hint['recommended'])

    def test_salutation_positions_and_omission_preserve_native_recipient(self):
        self.row['sender_id']='12345'
        for i,text in enumerate(['博士，先休息','先休息，博士，明天再说','先休息吧，博士','先休息吧']):
            with self.subTest(text=text):
                rendered=self.render(args(text=text,key='position-'+str(i)))
                self.assertEqual(rendered['text'],' '+text)
                self.assertEqual(rendered['mention_event_id'],1)

    def test_native_at_body_gets_space_without_changing_body_or_newline(self):
        self.row['sender_id']='12345'
        for i,text in enumerate(['在','先休息，博士','？',' 正文','\n```python\nprint(1)\n```']):
            with self.subTest(text=text):
                result=self.render(args(text=text,key='spacing-'+str(i)))
                self.assertEqual(result['text'],text if text[0].isspace() else ' '+text)
                self.assertEqual(result['mention_event_id'],1)

    def test_repeated_omissions_restore_hint_without_forcing_a_prefix(self):
        self.role.commit(self.render(args(text='我听着')))
        self.role.commit(self.render(args(2,text='发来看看',key='k2')))
        hint=self.role.hint(SID,self.row,self.pending)
        self.assertEqual(hint['consecutive_omissions'],2)
        self.assertTrue(hint['recommended'])
        self.assertFalse(hint['required'])
        result=self.render(args(3,text='先休息，博士，剩下的明早说',key='k3'))
        self.role.commit(result)
        self.assertEqual(self.role.last[SID]['unaddressed_turns'],0)
        self.assertEqual(result['text'],'先休息，博士，剩下的明早说')

    def test_replayed_receipt_does_not_double_count_omission(self):
        prepared=self.render(args())
        self.role.commit(prepared);self.role.commit(prepared)
        self.assertEqual(self.role.last[SID]['unaddressed_turns'],1)

    def test_old_prepared_reply_stays_exact_for_idempotent_retry(self):
        self.role.prepared[SID+'\0k1']=dict(original='在，说吧',text='博士，在，说吧',event_id=1,mention_event_id=1)
        rendered=self.render(args())
        self.assertEqual(rendered['text'],'博士，在，说吧')
        self.assertEqual(rendered['mention_event_id'],1)

    def test_foreign_group_cannot_gain_role_hint_by_event_id_collision(self):
        foreign=dict(self.row,conversation_id='other-group')
        data=dict(session=dict(id=SID,persona_preset=PRESET),context=dict(messages=[foreign]))
        self.assertNotIn('role_address',self.role.enrich(data,self.pending)['context']['messages'][0])
    def test_canonical_text_and_target_are_stable_after_ack(self):
        cache=ReplyContextCache()
        cache.enrich(dict(session=dict(id=SID,persona_preset=PRESET,cursor=0),context=dict(messages=[self.row])))
        raw=args();upstream=cache.prepare_send(raw);rendered=self.render(raw)
        upstream['text']=rendered['text'];self.role.commit(upstream)
        cache.acknowledge(SID,1)
        retry=cache.prepare_send(raw);retry['text']=self.render(raw)['text']
        self.assertEqual(retry,upstream)
        self.assertNotIn('respond_to_event_id',retry)

if __name__=='__main__':unittest.main(verbosity=2)
