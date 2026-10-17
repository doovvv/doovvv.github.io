"""One writer across preview and publish processes; OS releases it after a crash."""
from contextlib import contextmanager
import os
from pathlib import Path
import threading
import time

_held = threading.local()


@contextmanager
def workflow_lock(root, timeout=240):
    path = str(Path(root).resolve() / '.blog-build.lock')
    held = getattr(_held, 'paths', set())
    if path in held:
        yield
        return
    with open(path, 'a+b') as handle:
        if not handle.tell():
            handle.write(b'0')
            handle.flush()
        start = time.monotonic()
        while True:
            try:
                handle.seek(0)
                if os.name == 'nt':
                    import msvcrt
                    msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
                else:
                    import fcntl
                    fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except OSError:
                if time.monotonic() - start > timeout:
                    raise ValueError('另一个预览或发布任务仍在运行，请稍后重试。')
                time.sleep(0.05)
        _held.paths = held | {path}
        try:
            yield
        finally:
            _held.paths = held
            handle.seek(0)
            if os.name == 'nt':
                msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
