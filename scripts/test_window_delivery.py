"""Meaningful delivery boundary tests; no model or QQ called."""
import importlib.util
import io
import json
from pathlib import Path
import tempfile
import threading
import time
import unittest

ROOT=Path(__file__).resolve().parent.parent
sp=importlib.util.spec_from_file_location('stream_delivery',ROOT/'dialogue-test-window/model_stream.py')
runner=importlib.util.module_from_spec(sp);sp.loader.exec_module(runner)

class Fake:
    def __init__(self,events,exit_gate=None):
        self.stdin=io.BytesIO();self.stdout=io.BytesIO(b''.join((json.dumps(e)+'\n').encode() for e in events))
        self.gate=exit_gate or threading.Event();self.stopped=False
    def poll(self):return 0 if self.stopped or self.gate.is_set() else None
    def wait(self,timeout=None):
        if not self.gate.wait(timeout):raise runner.subprocess.TimeoutExpired('fake',timeout)
        return 0
    def terminate(self):self.stopped=True;self.gate.set()
    kill=terminate

class Delivery(unittest.TestCase):
    def invoke(self,fake,temp):
        return runner.run_turn(['fake'],'synthetic',cwd=temp,env={},log_dir=temp,popen=lambda *a,**kw:fake)
    def test_completed_reply_delivered_before_cli_cleanup(self):
        gate=threading.Event()
        fake=Fake([{'type':'item.completed','item':{'type':'agent_message','text':'{"bubbles":["下午好，博士"]}'}},{'type':'turn.completed','usage':{}}],gate)
        with tempfile.TemporaryDirectory() as temp:
            start=time.monotonic();text,_,_=self.invoke(fake,temp)
            self.assertIn('博士',text);self.assertLess(time.monotonic()-start,.5)
            self.assertFalse(gate.is_set());gate.set();time.sleep(.05)
    def test_failure_after_draft_not_delivered(self):
        fake=Fake([{'type':'item.completed','item':{'type':'agent_message','text':'{"bubbles":["草稿"]}'}},{'type':'turn.failed'}])
        with tempfile.TemporaryDirectory() as temp:
            with self.assertRaises(RuntimeError):self.invoke(fake,temp)
            self.assertTrue(fake.stopped)
    def test_malformed_final_is_not_a_reply(self):
        fake=Fake([{'type':'item.completed','item':{'type':'agent_message','text':'我先看看'}},{'type':'turn.completed'}])
        with tempfile.TemporaryDirectory() as temp:
            with self.assertRaises(RuntimeError):self.invoke(fake,temp)

if __name__=='__main__':unittest.main()
