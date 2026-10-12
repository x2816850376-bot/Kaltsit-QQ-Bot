"""Verify the actual runtime loads the skill without a second model call."""
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from chat_dialogue import build_developer_instructions, dialogue_sha256, read_dialogue_skill, read_coherence_skill

spec = importlib.util.spec_from_file_location('dialogue_runtime', ROOT/'luna-chat-runtime.py')
worker = importlib.util.module_from_spec(spec)
spec.loader.exec_module(worker)


class DialogueOutputTests(unittest.TestCase):
    def test_real_cli_has_persona_then_skill_once(self):
        persona = worker.PERSONA_RUNTIME.read_text('utf-8')
        settings = dict(arg.split('=', 1) for arg in worker.cli_args() if '=' in arg)
        loaded = json.loads(settings['developer_instructions'])
        self.assertTrue(loaded.startswith(persona))
        self.assertEqual(loaded.count(read_dialogue_skill()), 1)
        self.assertEqual(loaded.count(read_coherence_skill()),1)
        self.assertLess(loaded.index(read_dialogue_skill()),loaded.index(read_coherence_skill()))
        self.assertEqual(settings['features.skip_host_skill_discovery'], 'true')
        self.assertEqual(settings['model_reasoning_effort'], '"high"')
        self.assertEqual(worker.MODEL, 'gpt-6-luna')
        self.assertNotIn('temperature', settings)

    def test_human_approved_persona_not_rewritten(self):
        self.assertEqual(worker.PERSONA_RUNTIME.read_bytes(),
                         (ROOT/'vendor/Tulpa/chatlocal/prompts/mcp_chat/kaltsit_arknights_standard.md').read_bytes())
        self.assertIn('正文只称“博士”',worker.PERSONA_RUNTIME.read_text('utf-8'))
        self.assertIn('【当前阶段：凯尔希·思衡托】', build_developer_instructions(worker.PERSONA_RUNTIME.read_text('utf-8')))

    def test_only_trusted_skill_is_loaded(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder)/'SKILL.md'
            path.write_text('---\nname: kaltsit-dialogue-output\n---\n可信指导', 'utf-8')
            self.assertEqual(build_developer_instructions('角色卡', path),
                             '角色卡\n\n【发送前表达辅助：服从上面的当前角色卡，不另设人格】\n可信指导\n\n【表达重组后：检查整组气泡承接，仍服从角色卡】\n'+read_coherence_skill())
            path.write_text('---\nname: unrelated\n---\n其他人格', 'utf-8')
            with self.assertRaises(ValueError): read_dialogue_skill(path)

    def test_missing_or_unfinished_skill_fails_explicitly(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder)/'SKILL.md'
            with self.assertRaises(FileNotFoundError): read_dialogue_skill(path)
            for body in ('', '[TODO: placeholder]', 'x'*4001):
                path.write_text('---\nname: kaltsit-dialogue-output\n---\n'+body, 'utf-8')
                with self.assertRaises(ValueError): read_dialogue_skill(path)
        with self.assertRaises(ValueError): build_developer_instructions(' ')

    def test_digest_tracks_active_guidance(self):
        self.assertEqual(dialogue_sha256(), hashlib.sha256(read_dialogue_skill().encode('utf-8')).hexdigest())


if __name__ == '__main__': unittest.main()
