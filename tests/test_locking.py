from pathlib import Path
import tempfile
import threading
import unittest

try:
    from tools.locking import workflow_lock
except ImportError:
    workflow_lock = None

ROOT = Path(__file__).resolve().parents[1]


class BuildLockTests(unittest.TestCase):
    def test_preview_and_publish_cannot_write_at_the_same_time(self):
        self.assertTrue(callable(workflow_lock), 'Preview and publish need a shared writer lock')
        (ROOT / '.qa').mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(dir=ROOT / '.qa') as directory:
            root = Path(directory).resolve()
            self.assertTrue(root.is_relative_to((ROOT / '.qa').resolve()))
            acquired = threading.Event()
            def second_writer():
                with workflow_lock(root):
                    acquired.set()
            with workflow_lock(root):
                with workflow_lock(root):  # publish can call the builder safely
                    worker = threading.Thread(target=second_writer)
                    worker.start()
                    self.assertFalse(acquired.wait(0.15))
            worker.join(timeout=3)
            self.assertTrue(acquired.is_set())


if __name__ == '__main__':
    unittest.main()
