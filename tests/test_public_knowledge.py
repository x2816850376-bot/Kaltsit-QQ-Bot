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

    def test_topic_link_resolves_role_detail_without_forcing_plain_sugar(self):
        knowledge=OperatorKnowledge(ROOT/'knowledge/arknights/operators.json')
        mentions,cards=knowledge.context_cards({'content':'辣味糖果是哪个干员的细节？'},[])
        self.assertEqual(mentions[0]['canonical'],'霜星')
        self.assertEqual(mentions[0]['origin'],'topic_link')
        self.assertEqual(cards[0]['name'],'霜星')
        self.assertEqual(knowledge.context_cards({'content':'糖果'},[]),( [], [] ))

    def test_prts_topic_corpus_adds_source_bound_evidence_for_operator_questions(self):
        knowledge=OperatorKnowledge(ROOT/'knowledge/arknights/operators.json')
        mentions,cards=knowledge.context_cards({'content':'刻俄柏喜欢什么？'},[])
        self.assertEqual(mentions[0]['canonical'],'刻俄柏')
        self.assertTrue(cards[0].get('topic_evidence'))
        self.assertTrue(cards[0]['topic_evidence'][0]['source_url'].startswith('https://prts.wiki/w/'))

    def test_normalized_topic_concepts_cover_variants_and_keep_ambiguity(self):
        knowledge=OperatorKnowledge(ROOT/'knowledge/arknights/operators.json')
        mentions,cards=knowledge.context_cards({'content':'谁喜欢吃蜜饼？'},[])
        self.assertEqual(mentions[0]['canonical'],'刻俄柏')
        self.assertEqual(cards[0]['name'],'刻俄柏')
        mentions,cards=knowledge.context_cards({'content':'谁的信物是酸橙味的？'},[])
        names={x['name'] for x in cards}
        self.assertIn('安洁莉娜',names)
        self.assertIn('青枳',names)
        self.assertTrue(any(x.get('origin')=='topic_concept' for x in mentions))

    def test_chess_recommendation_prefers_wang_over_quoted_令_archive(self):
        knowledge=OperatorKnowledge(ROOT/'knowledge/arknights/operators.json')
        mentions,cards=knowledge.context_cards({'content':'推荐一个和我下围棋的人'},[])
        self.assertEqual(mentions[0]['canonical'],'望')
        self.assertEqual([x['name'] for x in cards],['望'])
        nickname=knowledge.context_cards({'content':'臭棋篓子是谁？'},[])[0][0]
        self.assertEqual(nickname['canonical'],'望')

    def test_relation_cards_keep_subject_and_relation_evidence(self):
        knowledge=OperatorKnowledge(ROOT/'knowledge/arknights/operators.json')
        _,cards=knowledge.context_cards({'content':'推荐一个和我下围棋的人'},[])
        self.assertEqual(cards[0]['name'],'望')
        self.assertEqual(cards[0]['relation_evidence'][0]['predicate'],'can_play')
        self.assertEqual(cards[0]['relation_evidence'][0]['role'],'subject_direct')
        self.assertIn('炎国国手',cards[0]['relation_evidence'][0]['text'])

    def test_action_detail_resolves_sanbi_stomping(self):
        knowledge=OperatorKnowledge(ROOT/'knowledge/arknights/operators.json')
        mentions,cards=knowledge.context_cards({'content':'擅长跺脚的干员是谁'},[])
        self.assertEqual(mentions[0]['canonical'],'珊比')
        self.assertEqual(cards[0]['name'],'珊比')

    def test_alter_forms_share_one_operator_identity_for_topic_relations(self):
        knowledge=OperatorKnowledge(ROOT/'knowledge/arknights/operators.json')
        self.assertEqual(knowledge.identity_canonical('引星棘刺'),'棘刺')
        self.assertEqual(knowledge.identity_canonical('阿米娅(医疗)'),'阿米娅')
        self.assertTrue(all(row.get('subject')!='引星棘刺' for row in knowledge.relations))

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
