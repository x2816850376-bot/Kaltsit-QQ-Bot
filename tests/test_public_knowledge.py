from pathlib import Path
import unittest
from chat_context import GROUP
from chat_knowledge import OperatorKnowledge
from chat_community import CommunityKnowledge
ROOT=Path(__file__).resolve().parent.parent

class PublicKnowledgeTests(unittest.TestCase):
    def test_verified_aliases_distinguish_operator_forms(self):
        knowledge=OperatorKnowledge(ROOT/'knowledge/arknights/operators.json')
        self.assertEqual(len(knowledge.operators),431)
        for alias,name in [('火陈','赤刃明霄陈'),('水陈','假日威龙陈')]:
            result=knowledge.mentions(alias,'抽卡干员')
            self.assertEqual(result[0]['canonical'],name)
            self.assertTrue(result[0]['source_url'].startswith('https://prts.wiki/w/'))

    def test_common_aliases_do_not_relabel_real_people(self):
        knowledge=OperatorKnowledge(ROOT/'knowledge/arknights/operators.json')
        self.assertEqual(knowledge.mentions('我叔叔家里养了小羊'),[])

    def test_detailed_kaltsit_and_brief_roster_are_session_scoped(self):
        knowledge=OperatorKnowledge(ROOT/'knowledge/arknights/operators.json')
        self.assertEqual(knowledge.lookup('s','水陈')['status'],'rejected')
        knowledge.observe({'session':{'id':'s','conversation_id':GROUP,'persona_preset':'kaltsit_arknights_standard'}})
        result=knowledge.lookup('s','凯尔希',max_chars=500)
        self.assertEqual(result['status'],'ok');self.assertEqual(result['level'],'detailed')
        self.assertTrue(result['detail']);self.assertTrue(result['has_more'])
        other=knowledge.lookup('s','假日威龙陈')
        self.assertEqual(other['level'],'brief');self.assertEqual(other['detail'],'')

    def test_primary_and_supplement_cards_have_live_references(self):
        knowledge=CommunityKnowledge(ROOT/'knowledge/bilibili-arknights')
        self.assertTrue(knowledge.cards);self.assertTrue(knowledge.supplement.cards)
        for provider in (knowledge,knowledge.supplement):
            for card in provider.cards:
                result=provider.render(card)
                self.assertTrue(result['sources']);self.assertLessEqual(len(result['sample']['root']),140)
                self.assertNotIn('uname',result['sample'])
