"""Source relevance and bounded excerpts, using a synthetic read-only index."""
from contextlib import closing
from pathlib import Path
import re
import sqlite3
import tempfile
import unittest

from chat_world import TerraKnowledge


def fixture_tokens(text):
    return ' '.join(run[i:i+2] for run in re.findall(r'[\u3400-\u9fff]+',text) for i in range(len(run)-1))


class WorldRelevanceTests(unittest.TestCase):
    def test_detail_beats_unrelated_country_annotation_and_survives_budget(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder)
            rows={
                197:'阿戈尔与伊比利亚的灾难传说。'*35,
                208:'阿戈尔市民的日常。'*110+'阿戈尔的科技发展涉及技术院与研究机构。'+'公民参与研究。'*80,
                209:'阿戈尔艺术与社会。'*110+'阿戈尔的科技研究有其社会制度背景。'+'公民参与讨论。'*80,
            }
            with closing(sqlite3.connect(root/'index.sqlite3')) as db:
                db.executescript('''
                    CREATE TABLE pages(page INTEGER PRIMARY KEY,file TEXT,text TEXT,chapter TEXT,verification TEXT,scope TEXT,speaker TEXT);
                    CREATE VIRTUAL TABLE search USING fts5(tokens);
                    CREATE TABLE handwritten_regions(page INTEGER PRIMARY KEY,text TEXT,verification TEXT,scope TEXT,speaker TEXT);
                    CREATE VIRTUAL TABLE handwriting_search USING fts5(tokens);
                ''')
                for page,text in rows.items():
                    db.execute('INSERT INTO pages VALUES(?,?,?,?,?,?,?)',(page,f'{page}.jpg',text,'fixture','automatic_ocr_unverified','page_body',None))
                    db.execute('INSERT INTO search(rowid,tokens) VALUES(?,?)',(page,fixture_tokens(text)))
                db.execute('INSERT INTO handwritten_regions VALUES(?,?,?,?,?)',(197,rows[197],'user_transcribed_handwriting','handwritten_annotation_only','凯尔希'))
                db.execute('INSERT INTO handwriting_search(rowid,tokens) VALUES(?,?)',(197,fixture_tokens(rows[197])))
                db.commit()
            for budget in (300,1200,1800):
                with self.subTest(budget=budget):
                    result=TerraKnowledge(root).retrieve('阿戈尔的科技是怎么发展的',budget)
                    self.assertEqual({p['scan_page'] for p in result['pages']},{208,209})
                    self.assertTrue(all('科技' in p['excerpt'] for p in result['pages']))
                    self.assertLessEqual(sum(len(p['excerpt']) for p in result['pages']),budget)

    def test_user_transcribed_history_remains_available(self):
        reader=TerraKnowledge()
        for query,expected in [('圣愚和皇帝的利刃是什么关系',{157,158}),('伊比利亚恐鱼和深海教会',{193,194})]:
            with self.subTest(query=query):
                result=reader.retrieve(query,1200)
                self.assertEqual({p['scan_page'] for p in result['pages']},expected)
                self.assertTrue(all(p['verification']=='user_transcribed' for p in result['pages']))


if __name__=='__main__':unittest.main()
