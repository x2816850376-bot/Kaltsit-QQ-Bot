from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch
import model_slots

class SlotTests(unittest.TestCase):
    def test_second_worker_waits_and_stop_cancels_without_model(self):
        with tempfile.TemporaryDirectory() as temp,patch.object(model_slots,'ROOT',Path(temp)),patch.object(model_slots,'load',return_value={'max_parallel_groups':1}):
            stop=Path(temp)/'STOP';results=[];started=threading.Event()
            def second():
                started.set()
                with model_slots.model_slot(stop) as admitted:results.append(admitted)
            with model_slots.model_slot(stop) as admitted:
                self.assertTrue(admitted)
                thread=threading.Thread(target=second);thread.start();started.wait(1)
                self.assertFalse(results)
                stop.touch();thread.join(2);self.assertEqual(results,[False])
            stop.unlink()
            with model_slots.model_slot(stop) as admitted:self.assertTrue(admitted)
            self.assertEqual((Path(temp)/'runtime/model-slot-0.lock').stat().st_size,1)
