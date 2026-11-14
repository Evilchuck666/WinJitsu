import threading
import time
import unittest
from unittest import mock

from winjitsu import config, daemon


_worker_started = False


def _start_worker_once():
    global _worker_started
    if not _worker_started:
        threading.Thread(target=daemon._action_worker, daemon=True).start()
        _worker_started = True


class ActionQueueTest(unittest.TestCase):
    def setUp(self):
        _start_worker_once()

        self.runs = []  # (action, start, end)
        patchers = [
            mock.patch.object(config.cfg, "delay_ms", 20),
            mock.patch.object(daemon, "dispatch", self._slow_dispatch),
        ]
        for patcher in patchers:
            patcher.start()
            self.addCleanup(patcher.stop)

    def _slow_dispatch(self, action):
        start = time.monotonic()
        time.sleep(0.15)  # an animation in progress
        self.runs.append((action, start, time.monotonic()))
        return None

    def _wait(self, *pendings):
        for pending in pendings:
            self.assertTrue(pending.event.wait(timeout=5), f"{pending.action} never finished")

    def test_an_action_waits_for_the_previous_animation(self):
        first = daemon._schedule_action("W")
        time.sleep(0.06)  # past the debounce delay, while W is still animating
        second = daemon._schedule_action("E")
        self._wait(first, second)

        self.assertEqual([run[0] for run in self.runs], ["W", "E"])
        (_, _, first_end), (_, second_start, _) = self.runs
        self.assertGreaterEqual(second_start, first_end)
        self.assertEqual((first.result, second.result), (["OK"], ["OK"]))

    def test_only_the_last_action_of_a_burst_runs(self):
        burst = [daemon._schedule_action(action) for action in ("N", "NE", "E")]
        self._wait(*burst)

        self.assertEqual([run[0] for run in self.runs], ["E"])
        self.assertTrue(all(pending.result == ["OK"] for pending in burst))


if __name__ == "__main__":
    unittest.main()
