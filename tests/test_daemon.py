import threading
import time
import unittest
from unittest import mock

from Xlib import error as xerror

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
            mock.patch.object(daemon, "dispatch", self._slow_dispatch),
            mock.patch.object(daemon, "_last_request", float("-inf")),  # each test starts after a quiet period
        ]
        for patcher in patchers:
            patcher.start()
            self.addCleanup(patcher.stop)

    def _delay(self, milliseconds):
        patcher = mock.patch.object(config.cfg, "delay_ms", milliseconds)
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

    def _ran(self):
        return [run[0] for run in self.runs]

    def test_the_first_action_runs_at_once(self):
        self._delay(300)

        scheduled = time.monotonic()
        pending   = daemon._schedule_action("W")
        self._wait(pending)

        (_, started, _), = self.runs
        self.assertLess(started - scheduled, 0.1, "it should not wait for the debounce delay")

    def test_an_action_waits_for_the_previous_animation(self):
        self._delay(20)

        first = daemon._schedule_action("W")
        time.sleep(0.06)  # past the debounce delay, while W is still animating
        second = daemon._schedule_action("E")
        self._wait(first, second)

        self.assertEqual(self._ran(), ["W", "E"])
        (_, _, first_end), (_, second_start, _) = self.runs
        self.assertGreaterEqual(second_start, first_end)
        self.assertEqual((first.result, second.result), (["OK"], ["OK"]))

    def test_a_burst_runs_its_first_and_last_actions(self):
        self._delay(100)

        burst = [daemon._schedule_action(action) for action in ("N", "NE", "E")]
        self._wait(*burst)

        self.assertEqual(self._ran(), ["N", "E"])
        self.assertTrue(all(pending.result == ["OK"] for pending in burst))

    def test_key_repeat_runs_once(self):
        self._delay(100)

        burst = [daemon._schedule_action("TF") for _ in range(4)]
        self._wait(*burst)

        self.assertEqual(self._ran(), ["TF"])
        self.assertTrue(all(pending.result == ["OK"] for pending in burst))

    def test_no_delay_runs_every_action(self):
        self._delay(0)

        actions = [daemon._schedule_action(action) for action in ("N", "NE", "E")]
        self._wait(*actions)

        self.assertEqual(self._ran(), ["N", "NE", "E"])


class XReconnectTest(unittest.TestCase):
    def setUp(self):
        self.resets = []
        patcher = mock.patch.object(daemon, "reset_display", lambda: self.resets.append(True))
        patcher.start()
        self.addCleanup(patcher.stop)

    def _run(self, dispatch):
        pending = daemon._Pending("W")
        with mock.patch.object(daemon, "dispatch", dispatch), self.assertLogs("winjitsu", level="WARNING"):
            daemon._run_action(pending)
        return pending.result

    def test_retries_once_with_a_new_connection(self):
        calls = []

        def dispatch(action):
            calls.append(action)
            if len(calls) == 1:
                raise xerror.ConnectionClosedError("server")
            return None

        self.assertEqual(self._run(dispatch), ["OK"])
        self.assertEqual((len(calls), len(self.resets)), (2, 1))

    def test_reports_the_error_when_x_stays_unreachable(self):
        def dispatch(action):
            raise xerror.ConnectionClosedError("server")

        (result,) = self._run(dispatch)
        self.assertTrue(result.startswith("ERROR:"), result)
        self.assertEqual(len(self.resets), 2)


if __name__ == "__main__":
    unittest.main()
