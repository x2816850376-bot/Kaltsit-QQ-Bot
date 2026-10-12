"""Web opt-in, tool isolation and persona integration; no model or network."""
import importlib.util
import json
from pathlib import Path
import subprocess
import unittest

ROOT=Path(__file__).resolve().parent.parent

class WebFallbackTests(unittest.TestCase):
    def guard(self,event):
        code='const g=require(process.argv[1]);process.stdout.write(JSON.stringify(g.decision(JSON.parse(process.argv[2]))));'
        out=subprocess.run(['node','-e',code,str(ROOT/'tulpa-tools-only.cjs'),json.dumps(event)],capture_output=True,text=True,check=True,shell=False)
        return json.loads(out.stdout)

    def test_public_search_and_read_allowed(self):
        for args in [{'search_query':[{'q':'明日方舟 公测 官方公告'}]}, {'open':[{'ref_id':'https://prts.wiki/w/凯尔希'}]}, {'open':[{'ref_id':'turn0search0'}]}]:
            self.assertTrue(self.guard({'tool_name':'web.run','tool_input':args})['allow'])

    def test_local_private_and_credentials_rejected(self):
        for url in ['http://127.0.0.1:18777/mcp','http://localhost','http://192.168.1.1','http://[::1]','file:///C:/auth.json','https://user:password@example.com','https://computer.local/x']:
            self.assertFalse(self.guard({'tool_name':'web.run','tool_input':{'open':[{'ref_id':url}]}})['allow'])
        self.assertFalse(self.guard({'tool_name':'web.run','tool_input':{'search_query':[{'q':'OPENAI_API_KEY auth.json'}]}})['allow'])

    def test_tools_still_denied(self):
        for tool in ['exec_command','functions.exec','shell','apply_patch','browser','mcp__other__search','mcp__tulpa__read_file_chunks']:
            self.assertFalse(self.guard({'tool_name':tool,'tool_input':{}})['allow'])
        self.assertTrue(self.guard({'tool_name':'mcp__kaltsit_bot__get_operator_knowledge','tool_input':{}})['allow'])

    def test_malformed_tool_input_denied(self):
        for args in [None,'not json',[],{'open':[{'ref_id':'not_a_source'}]}]:
            self.assertFalse(self.guard({'tool_name':'web.run','tool_input':args})['allow'])

    def test_runtime_live_search_and_model_unchanged(self):
        spec=importlib.util.spec_from_file_location('web_worker',ROOT/'luna-chat-runtime.py');m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
        args=m.cli_args()
        self.assertIn('web_search="live"',args)
        self.assertEqual(m.MODEL,'gpt-6-luna');self.assertEqual(m.REASONING,'high');self.assertFalse(m.FAST_ENABLED)
        for name in ['shell_tool','unified_exec','browser_use','computer_use']:
            self.assertIn(f'features.{name}=false',args)
        self.assertIn('read-only',args)

    def test_persona_copies_and_policy_agree(self):
        files=['prompts/persona_runtime.txt','vendor/Tulpa/chatlocal/prompts/mcp_chat/kaltsit_arknights_standard.md']
        self.assertEqual(len({(ROOT/f).read_bytes() for f in files}),1)
        for name in files:
            text=(ROOT/name).read_text('utf-8')
            self.assertIn('【知识缺口与联网回答】',text)
            self.assertIn('不以“我搜索到了”',text)
            self.assertIn('不发送群号、QQ号',text)

    def test_search_reply_punctuation_and_source_preserved(self):
        from chat_style import normalize_outgoing_text
        source='https://ak.hypergryph.com/news/201904302'
        result=normalize_outgoing_text('博士，全平台公测是2019年5月1日。\n'+source)
        self.assertNotIn('。',result)
        self.assertTrue(result.endswith(source))

if __name__=='__main__':unittest.main()
