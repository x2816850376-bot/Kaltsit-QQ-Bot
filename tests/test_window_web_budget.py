"""No network/model: test hook composition and aborting excessive native web."""
import importlib.util,io,json,os
from pathlib import Path
import shutil,subprocess,tempfile,threading,unittest

ROOT=Path(__file__).resolve().parent.parent
spec=importlib.util.spec_from_file_location('web_budget_stream',ROOT/'dialogue-test-window/model_stream.py')
stream=importlib.util.module_from_spec(spec);spec.loader.exec_module(stream)

class Fake:
    def __init__(self,events):
        self.stdin=io.BytesIO();self.stdout=io.BytesIO(b''.join((json.dumps(e)+'\n').encode() for e in events));self.done=threading.Event();self.stopped=False
    def poll(self):return 0 if self.done.is_set() else None
    def wait(self,timeout=None):
        if not self.done.wait(timeout):raise subprocess.TimeoutExpired('fake',timeout)
        return 0
    def terminate(self):self.stopped=True;self.done.set()
    kill=terminate

class WebBudgetTests(unittest.TestCase):
    def events(self,count,ids=True,complete_only=False):
        rows=[]
        for i in range(count):
            item={'type':'web_search',**({'id':str(i)} if ids else {})}
            if not complete_only:rows.append({'type':'item.started','item':item})
            rows.append({'type':'item.completed','item':item})
        rows += [{'type':'item.completed','item':{'type':'agent_message','text':'{"bubbles":["已核实的内容"]}'}},{'type':'turn.completed'}]
        return rows
    def run_fake(self,fake,folder,**options):
        return stream.run_turn(['fake'],'synthetic',cwd=folder,env={},log_dir=folder,popen=lambda *a,**kw:fake,**options)
    def test_four_queries_are_not_double_counted_and_complete(self):
        for ids,complete_only in ((True,False),(False,False),(True,True)):
            with tempfile.TemporaryDirectory() as folder:
                fake=Fake(self.events(4,ids,complete_only));fake.done.set()
                text,_,_=self.run_fake(fake,folder,web_budget=4)
                self.assertIn('已核实',text)
    def test_fifth_query_stops_turn_without_delivering_a_draft_or_retry(self):
        with tempfile.TemporaryDirectory() as folder:
            fake=Fake(self.events(5))
            with self.assertRaises(stream.WebBudgetExceeded):self.run_fake(fake,folder,web_budget=4)
            self.assertTrue(fake.stopped)
    def test_old_nonwindow_caller_has_no_new_implicit_limit(self):
        with tempfile.TemporaryDirectory() as folder:
            fake=Fake(self.events(5));fake.done.set()
            self.assertIn('已核实',self.run_fake(fake,folder)[0])
    def test_hook_denies_fifth_slot_and_preserves_private_url_guard(self):
        node=shutil.which('node')
        if not node:self.skipTest('Node unavailable')
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);window=root/'dialogue-test-window';window.mkdir()
            shutil.copyfile(ROOT/'tulpa-tools-only.cjs',root/'tulpa-tools-only.cjs')
            shutil.copyfile(ROOT/'dialogue-test-window/web-budget-hook.cjs',window/'web-budget-hook.cjs')
            directory=root/'runtime/test/web-budgets';directory.mkdir(parents=True)
            env=dict(os.environ,KALTSIT_GROUP='synthetic-budget',KALTSIT_TEST_WEB_BUDGET_FILE=str(directory/('a'*32)))
            def call(event):
                r=subprocess.run([node,str(window/'web-budget-hook.cjs')],input=json.dumps(event).encode(),stdout=subprocess.PIPE,stderr=subprocess.PIPE,env=env,timeout=8,shell=False)
                self.assertEqual(r.returncode,0)
                return json.loads(r.stdout)['hookSpecificOutput']['permissionDecision']
            public={'tool_name':'web.run','tool_input':{'search_query':[{'q':'明日方舟 PRTS'}]}}
            private={'tool_name':'web.run','tool_input':{'open':[{'ref_id':'http://127.0.0.1'}]}}
            self.assertEqual(call(private),'deny')
            self.assertEqual([call(public) for _ in range(5)],['allow']*4+['deny'])
            self.assertEqual(len(list(directory.glob('*.slot'))),4)
            self.assertEqual(call({'tool_name':'mcp__kaltsit_bot__send_chat_message','tool_input':{}}),'deny')

if __name__=='__main__':unittest.main()
