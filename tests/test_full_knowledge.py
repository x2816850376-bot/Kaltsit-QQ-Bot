import hashlib
import importlib.util
import json
from pathlib import Path
import sqlite3
import unittest

from chat_context import GROUP
from chat_corpus import CanonicalKnowledge, corpus_query
from chat_scope import CHAT_TOOLS
from chat_world import TerraKnowledge

ROOT=Path(__file__).resolve().parent.parent
CORPUS=ROOT/'knowledge/kaltsit-corpus'


class FullKnowledgeTests(unittest.TestCase):
    def test_all_original_files_are_complete_and_hash_verified(self):
        manifest=json.loads((CORPUS/'sources.json').read_text('utf-8'))
        self.assertEqual(len(manifest['sources']),15)
        self.assertFalse(manifest['group_memory_included'])
        for row in manifest['sources']:
            body=(CORPUS/'originals'/row['file']).read_bytes()
            self.assertEqual(hashlib.sha256(body).hexdigest(),row['sha256'])
            self.assertEqual(len(body.decode('utf-8-sig')),row['characters'])
            self.assertNotIn('source_path',row)

    def test_index_covers_every_character_of_each_original(self):
        with sqlite3.connect(CORPUS/'index.sqlite3') as db:
            sources=json.loads((CORPUS/'sources.json').read_text('utf-8'))['sources']
            for source in sources:
                text=(CORPUS/'originals'/source['file']).read_bytes().decode('utf-8-sig')
                rows=db.execute('SELECT text,start_char,end_char FROM passages WHERE file=? AND start_char IS NOT NULL ORDER BY start_char',(source['file'],)).fetchall()
                covered=0
                for piece,start,end in rows:
                    self.assertLessEqual(start,covered)
                    self.assertEqual(piece,text[start:end])
                    covered=max(covered,end)
                self.assertEqual(covered,len(text))

    def test_original_residual_and_esperanta_voices_are_separate(self):
        lines=json.loads((CORPUS/'voice-lines.json').read_text('utf-8'))['entries']
        self.assertEqual(len(lines),114)
        self.assertGreaterEqual(len({r['stage'] for r in lines}),3)
        self.assertTrue(all(r['text'] for r in lines))

    def test_bounded_lookup_and_injection_cannot_execute_or_read_files(self):
        reader=CanonicalKnowledge()
        result=reader.retrieve('任命助理',500)
        self.assertEqual(result['status'],'ok')
        self.assertLessEqual(sum(len(r['excerpt']) for r in result['passages']),500)
        self.assertIn('不是本群聊天',result['rules'])
        self.assertIn(reader.retrieve('auth.json; $(whoami); DROP TABLE passages')['status'],('not_found','ok'))
        with sqlite3.connect(CORPUS/'index.sqlite3') as db:
            self.assertEqual(db.execute('PRAGMA integrity_check').fetchone()[0],'ok')
            self.assertEqual(db.execute('SELECT count(*) FROM passages').fetchone()[0],235)
        self.assertEqual(reader.retrieve('任命助理',True)['status'],'rejected')
        self.assertEqual(reader.retrieve('x'*501)['status'],'rejected')

    def test_corpus_requires_current_group_and_persona(self):
        reader=CanonicalKnowledge()
        self.assertEqual(reader.lookup('s','任命助理')['status'],'rejected')
        reader.observe({'session':{'id':'s','conversation_id':'other','persona_preset':'kaltsit_arknights_standard'}})
        self.assertEqual(reader.lookup('s','任命助理')['status'],'rejected')
        reader.observe({'session':{'id':'s','conversation_id':GROUP,'persona_preset':'kaltsit_arknights_standard'}})
        self.assertEqual(reader.lookup('s','任命助理')['status'],'ok')
        self.assertIn('get_canonical_knowledge',CHAT_TOOLS)

    def test_greetings_do_not_dump_full_corpus(self):
        self.assertIsNone(corpus_query({'content':'在吗'}))
        self.assertIsNotNone(corpus_query({'content':'凯尔希如何看待艾利奥特'}))

    def test_world_handwriting_and_raw_ocr_have_separate_records(self):
        with sqlite3.connect(ROOT/'knowledge/terra-journey/index.sqlite3') as db:
            self.assertEqual(db.execute('SELECT count(*) FROM handwritten_regions').fetchone()[0],24)
            tables={r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            self.assertFalse(any(word in name for name in tables for word in ['message','memory','session','account']))
        result=TerraKnowledge().retrieve('圣愚',1500)
        self.assertEqual(result['status'],'ok')
        self.assertTrue(result['pages'])

    def test_text_window_retrieves_the_same_original_corpus(self):
        spec=importlib.util.spec_from_file_location('full_knowledge_window',ROOT/'dialogue-test-window/server.py')
        module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
        prompt=module.build_prompt({'nickname':'合成用户','message':'凯尔希，任命助理的台词是什么','history':[]})
        self.assertIn('canonical_knowledge',prompt)
        self.assertIn('用户提供的凯尔希原作文本全集',prompt)
