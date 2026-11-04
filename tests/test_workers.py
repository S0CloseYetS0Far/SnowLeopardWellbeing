"""The pictures spread over several processes (real processes, Qt offscreen)."""

import os
import random
import time
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")  # inherited by the workers
os.environ.setdefault("QT_LOGGING_RULES", "qt.multimedia*=false")

from PySide6.QtWidgets import QApplication

from wellbeing import media
from wellbeing.workers import WorkerPool, default_count, split

app = QApplication.instance() or QApplication([])
SOURCES = media.discover().pictures


def wait_for(condition, seconds=30.0):
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        app.processEvents()
        if condition():
            return True
        time.sleep(0.02)
    return False


class SplitTest(unittest.TestCase):
    def test_every_picture_goes_to_exactly_one_worker(self):
        shares = split(SOURCES, 4, random.Random(1))
        self.assertEqual(len(shares), 4)
        dealt = [s for share in shares for s in share]
        self.assertCountEqual(dealt, SOURCES)
        self.assertLessEqual(max(map(len, shares)) - min(map(len, shares)), 1)

    def test_default_count_is_sensible(self):
        self.assertTrue(1 <= default_count() <= 4)


class PoolTest(unittest.TestCase):
    def setUp(self):
        self.pool = WorkerPool(SOURCES[:4], 2, rng=random.Random(3))

    def tearDown(self):
        self.pool.shutdown()

    def test_workers_open_every_picture_and_lock_the_video_until_shut_down(self):
        self.assertFalse(self.pool.all_closed(), "nothing has started yet")
        self.pool.start()
        self.assertFalse(self.pool.all_closed(), "workers are still starting")
        self.assertTrue(wait_for(lambda: self.pool.open_count == 4), f"open: {self.pool.open_count}")
        self.assertEqual(len({w.process.pid for w in self.pool.workers}), 2)
        self.assertFalse(self.pool.all_closed())

        self.assertTrue(wait_for(lambda: all(w.frames > 30 for w in self.pool.workers)), "workers animate")

        processes = [w.process for w in self.pool.workers]
        self.pool.shutdown()
        self.assertFalse(any(p.is_alive() for p in processes))

    def test_a_worker_that_dies_is_started_again(self):
        self.pool.start()
        self.assertTrue(wait_for(lambda: self.pool.open_count == 4))
        victim = self.pool.workers[0].process
        victim.kill()
        victim.join(5)

        self.assertTrue(wait_for(lambda: self.pool.restarts == 1))
        self.assertNotEqual(self.pool.workers[0].process.pid, victim.pid)
        self.assertTrue(wait_for(lambda: self.pool.open_count == 4), f"open: {self.pool.open_count}")


if __name__ == "__main__":
    unittest.main()
