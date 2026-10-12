"""Cross-process model concurrency limit. Locks release on process exit."""
from contextlib import contextmanager
import os
import time
from bot_config import ROOT, load


@contextmanager
def model_slot(stop):
    directory=ROOT/'runtime';directory.mkdir(exist_ok=True)
    held=None
    while held is None and not stop.exists():
        for number in range(load()['max_parallel_groups']):
            handle=(directory/f'model-slot-{number}.lock').open('a+b')
            handle.seek(0)
            try:
                if os.name=='nt':
                    import msvcrt
                    msvcrt.locking(handle.fileno(),msvcrt.LK_NBLCK,1)
                else:
                    import fcntl
                    fcntl.flock(handle.fileno(),fcntl.LOCK_EX|fcntl.LOCK_NB)
                if os.fstat(handle.fileno()).st_size==0:handle.write(b'0');handle.flush()
                held=handle;break
            except OSError:handle.close()
        if held is None:time.sleep(.2)
    try:yield held is not None and not stop.exists()
    finally:
        if held:
            held.seek(0)
            if os.name=='nt':msvcrt.locking(held.fileno(),msvcrt.LK_UNLCK,1)
            else:fcntl.flock(held.fileno(),fcntl.LOCK_UN)
            held.close()
