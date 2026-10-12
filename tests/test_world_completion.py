"""Public summary provenance, event causality and complete replies, offline."""
import hashlib
import importlib.util
import json
from pathlib import Path
import sqlite3
import unittest
from chat_context import GROUP
from chat_completion import require_complete_text
from chat_world import TerraKnowledge, chat_query

ROOT=Path(__file__).resolve().parent.parent

class WorldTests(unittest.TestCase):
    def test_full_index_retains_actual_verification_states(self):
        with sqlite3.connect(ROOT/'knowledge/terra-journey/index.sqlite3') as db:
            rows=db.execute('SELECT text,verification,scope FROM pages').fetchall()
        self.assertEqual(len(rows),454)
        self.assertEqual(sum(v=='automatic_ocr_crosschecked' for _,v,_ in rows),426)
        self.assertEqual(sum(v=='user_transcribed' for _,v,_ in rows),7)
        self.assertFalse(any(v=='curated_summary' for _,v,_ in rows))

    def test_all_event_facts_have_actual_bounded_evidence(self):
        catalog=json.loads((ROOT/'knowledge/terra-journey/story-events.json').read_text('utf-8'))
        with sqlite3.connect(ROOT/'knowledge/terra-journey/index.sqlite3') as db:
            for card in catalog['events']:
                sources={}
                for source in card['sources']:
                    table='handwritten_regions' if source['scope']=='handwritten_annotation_only' else 'pages'
                    text=db.execute(f'SELECT text FROM {table} WHERE page=?',(source['scan_page'],)).fetchone()[0]
                    self.assertEqual(hashlib.sha256(text.encode()).hexdigest(),source['text_sha256'])
                    self.assertNotEqual(source['scope'],'curated_summary_only')
                    sources[source['scan_page']]=text
                self.assertEqual(set(card['sequence']),{f['id'] for f in card['facts']})
                for fact in card['facts']:self.assertIn(fact['support_quote'],sources[fact['scan_page']])

    def test_documented_story_and_unknown_subject(self):
        reader=TerraKnowledge()
        for query in ['讲个泰拉小故事','讲个乌萨斯圣愚相关的泰拉故事','讲个萨科塔的故事']:
            result=reader.retrieve(query,1600)
            self.assertEqual(result['status'],'ok')
            self.assertEqual(result['mode'],'documented_story')
            self.assertTrue(result['event_card']['facts'])
            self.assertTrue(all(p['verification']!='curated_summary' for p in result['pages']))
        self.assertEqual(reader.retrieve('auth.json; DROP TABLE pages; $(whoami)')['status'],'not_found')

    def test_authorization_and_budget(self):
        reader=TerraKnowledge()
        self.assertEqual(reader.lookup('s','圣愚')['status'],'rejected')
        reader.observe({'session':{'id':'s','conversation_id':'other','persona_preset':'kaltsit_arknights_standard'}})
        self.assertFalse(reader.allowed('s'))
        reader.observe({'session':{'id':'s','conversation_id':GROUP,'persona_preset':'kaltsit_arknights_standard'}})
        self.assertEqual(reader.lookup('s','圣愚')['status'],'ok')
        for budget in (True,4001):self.assertEqual(reader.retrieve('圣愚',budget)['status'],'rejected')

    def test_followup_does_not_take_another_speakers_topic(self):
        current={'id':5,'sender_id':'a','content':'那它能治好吗'}
        self.assertIn('矿石病',chat_query(current,[{'id':4,'sender_id':'a','content':'矿石病是什么'}]))
        self.assertIsNone(chat_query(current,[{'id':4,'sender_id':'b','content':'矿石病是什么'}]))
        self.assertIsNone(chat_query(current,[{'id':6,'sender_id':'a','content':'矿石病是什么'}]))

    def test_window_uses_same_world_sources(self):
        spec=importlib.util.spec_from_file_location('public_window',ROOT/'dialogue-test-window/server.py')
        server=importlib.util.module_from_spec(spec);spec.loader.exec_module(server)
        prompt=server.build_prompt({'message':'讲一个泰拉小故事'})
        self.assertIn('terra_world_frame',prompt);self.assertIn('world_knowledge',prompt)

class CompletionTests(unittest.TestCase):
    def test_announcing_a_retry_is_not_a_reply(self):
        for text in ['我重新发一句','博士，我重新发一句。','那我换个说法']:
            with self.assertRaises(ValueError):require_complete_text(text)
        for text in ['我重新发一句：博士，阵容发来','博士，我听着','要我重新发吗？']:
            require_complete_text(text)
