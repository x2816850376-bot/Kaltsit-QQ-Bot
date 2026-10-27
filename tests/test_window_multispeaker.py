"""Preview-window regressions for simulated multi-speaker batches."""
import importlib.util
import pathlib
import sys
import unittest

ROOT=pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
spec=importlib.util.spec_from_file_location('dialogue_window_server',ROOT/'dialogue-test-window/server.py')
window=importlib.util.module_from_spec(spec);spec.loader.exec_module(window)

class WindowMultiSpeakerTests(unittest.TestCase):
    def test_batch_normalization_preserves_each_nickname_and_event(self):
        batch=window.normalize_test_batch({'messages':[
            {'event_id':'e甲','nickname':'甲','message':'早上好'},
            {'event_id':'e乙','nickname':'乙','message':'令和望谁更适合下棋'}]})
        self.assertEqual([row['event_id'] for row in batch],['e甲','e乙'])
        routing=window.build_batch_routing(batch,None)
        self.assertTrue(routing['interleaved'])
        self.assertEqual([row['speaker_name'] for row in routing['events']],['甲','乙'])
        self.assertEqual(routing['direct_target_event_ids'],['e甲','e乙'])

    def test_legacy_single_message_keeps_compatibility(self):
        batch=window.normalize_test_batch({'nickname':'晨星','message':'在吗'})
        self.assertEqual(len(batch),1)
        self.assertEqual(batch[0]['nickname'],'晨星')
        self.assertEqual(window.build_batch_routing(batch,None)['speaker_count'],1)

if __name__=='__main__':unittest.main(verbosity=2)
