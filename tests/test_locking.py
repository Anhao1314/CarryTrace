"""Cross-process claim-store locking and bounded contention failure."""
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from chat_distiller import ClaimStore, ClaimStoreBusy

ROOT = Path(__file__).resolve().parents[1]

WORKER = """
import sys, uuid
from chat_distiller import ClaimStore

path, count = sys.argv[1], int(sys.argv[2])
store = ClaimStore(path, lock_timeout=30)
for _ in range(count):
    store.record(uuid.uuid4().hex)
"""

HOLDER = """
import sys, time
from chat_distiller.locking import FileLock

with FileLock(sys.argv[1] + ".lock", timeout=5):
    print("locked", flush=True)
    time.sleep(1.5)
"""


class ClaimStoreLockingTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / "claims.jsonl"

    def _run(self, code, *args):
        return subprocess.Popen(
            [sys.executable, "-c", code, str(self.path), *args],
            cwd=str(ROOT), text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)

    def test_concurrent_processes_do_not_lose_writes(self):
        processes = [self._run(WORKER, "5") for _ in range(4)]
        outputs = [process.communicate(timeout=90) for process in processes]
        for process, (stdout, stderr) in zip(processes, outputs):
            self.assertEqual(process.returncode, 0, stderr or stdout)
        rows = ClaimStore(self.path).claims(status="all")
        self.assertEqual(len(rows), 20)

    def test_lock_timeout_is_explicit_and_recoverable(self):
        holder = self._run(HOLDER)
        self.addCleanup(holder.kill)
        line = holder.stdout.readline().strip()
        self.assertEqual(line, "locked")
        with self.assertRaises(ClaimStoreBusy):
            ClaimStore(self.path, lock_timeout=0.2).record("blocked write")
        _, stderr = holder.communicate(timeout=30)
        self.assertEqual(holder.returncode, 0, stderr)
        ClaimStore(self.path, lock_timeout=5).record("after release")
        self.assertEqual(ClaimStore(self.path).claims()[0]["text"], "after release")


if __name__ == "__main__":
    unittest.main()
