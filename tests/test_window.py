import subprocess
import unittest
from types    import SimpleNamespace
from unittest import mock

from fakes    import FakeSessionTestCase, FakeWindowManager
from winjitsu import window


class GeometryTest(unittest.TestCase):
    def test_client_to_frame_adds_the_decorations(self):
        self.assertEqual(window._client_to_frame((101, 124, 798, 575), (1, 1, 24, 1)), (100, 100, 800, 600))

    def test_matches_within_tolerance(self):
        self.assertTrue(window.geometry_matches((0, 0, 960, 1080), (2, 0, 960, 1078)))
        self.assertFalse(window.geometry_matches((0, 0, 960, 1080), (3, 0, 960, 1080)))

    def test_nothing_matches_a_missing_geometry(self):
        self.assertFalse(window.geometry_matches((0, 0, 960, 1080), None))


class MoveWindowTest(FakeSessionTestCase):
    def test_sizes_the_client_and_places_the_frame(self):
        wm = self.use(FakeWindowManager((200, 150, 800, 600), extents=(1, 1, 24, 1)))

        reached = window.move_window(window.get_window_position(), 0, 0, 960, 1080)

        self.assertEqual(wm.configures[-1], (0, 0, 958, 1055))
        self.assertEqual(reached, (0, 0, 960, 1080))

    def test_clamps_to_the_x_screen(self):
        wm = self.use(FakeWindowManager((200, 150, 800, 600)))

        reached = window.move_window(window.get_window_position(), 1500, -50, 800, 600)

        self.assertEqual(reached, (1120, 0, 800, 600))
        self.assertEqual(wm.frame, reached)

    def test_returns_none_when_the_window_closes(self):
        wm = self.use(FakeWindowManager((200, 150, 800, 600)))
        current = window.get_window_position()
        original_configure = wm.configure

        def close_during_the_animation(*args):
            original_configure(*args)
            wm.closed = True

        wm.configure = close_during_the_animation
        self.assertIsNone(window.move_window(current, 0, 0, 960, 1080))


class AnimationTimingTest(FakeSessionTestCase):
    STEPS    = 30
    INTERVAL = 0.01

    def setUp(self):
        super().setUp()
        self.now = 0.0
        fake_time = SimpleNamespace(monotonic=lambda: self.now, sleep=self._sleep)
        self.stack.enter_context(mock.patch.object(window, "time", fake_time))
        self.stack.enter_context(mock.patch.object(window, "FRAME_INTERVAL", self.INTERVAL))
        self.stack.enter_context(mock.patch.object(window.cfg, "steps", self.STEPS))
        self.wm = self.use(FakeWindowManager((200, 150, 800, 600)))

    def _sleep(self, seconds):
        self.now += max(0.0, seconds)

    def test_one_request_per_step_paced_by_the_clock(self):
        window.move_window(window.get_window_position(), 0, 0, 960, 1080)

        self.assertEqual(len(self.wm.configures), self.STEPS)
        self.assertAlmostEqual(self.now, (self.STEPS - 1) * self.INTERVAL, places=6)

    def test_drops_steps_when_running_late_and_ends_on_the_target(self):
        original_configure = self.wm.configure

        def slow_configure(*args):
            original_configure(*args)
            self.now += 3 * self.INTERVAL  # each request takes three steps' worth of time

        self.wm.configure = slow_configure
        reached = window.move_window(window.get_window_position(), 0, 0, 960, 1080)

        self.assertLess(len(self.wm.configures), self.STEPS // 2)
        self.assertEqual(self.wm.configures[-1], (0, 0, 960, 1080))
        self.assertEqual(reached, (0, 0, 960, 1080))
        # About STEPS × INTERVAL plus the last request's own time, instead of the
        # 30 × 3 × INTERVAL it would take without dropping steps.
        self.assertLess(self.now, (self.STEPS + 4) * self.INTERVAL)


class XdotoolErrorsTest(unittest.TestCase):
    def _xdotool(self, error):
        def check_output(args, **kwargs):
            raise error

        fake_subprocess = SimpleNamespace(
            check_output=check_output, CalledProcessError=subprocess.CalledProcessError, DEVNULL=subprocess.DEVNULL,
        )
        return mock.patch.object(window, "subprocess", fake_subprocess)

    def test_no_active_window(self):
        with self._xdotool(subprocess.CalledProcessError(1, ["xdotool"])):
            with self.assertRaisesRegex(RuntimeError, "^No active window"):
                window.get_window_position()

    def test_xdotool_missing(self):
        with self._xdotool(FileNotFoundError("xdotool")):
            with self.assertRaisesRegex(RuntimeError, "xdotool is not installed"):
                window.get_window_position()

    def test_window_gone(self):
        with self._xdotool(subprocess.CalledProcessError(1, ["xdotool"])):
            with self.assertRaisesRegex(RuntimeError, "it may have closed"):
                window.get_window_geometry(4242)
            self.assertIsNone(window.get_wm_class(4242))


class SettledGeometryTest(unittest.TestCase):
    def _reads(self, *geometries):
        reads = iter(geometries)
        return mock.patch.object(
            window, "get_window_geometry",
            lambda window_id: dict(zip(("X", "Y", "WIDTH", "HEIGHT"), next(reads))),
        )

    def test_waits_until_two_reads_agree(self):
        with self._reads((5, 5, 900, 1000), (0, 0, 960, 1080), (0, 0, 960, 1080)), \
             mock.patch.object(window, "_SETTLE_INTERVAL", 0):
            self.assertEqual(window._settled_geometry(1), (0, 0, 960, 1080))

    def test_gives_up_after_the_last_attempt(self):
        geometries = [(step, 0, 960, 1080) for step in range(window._SETTLE_ATTEMPTS)]
        with self._reads(*geometries), mock.patch.object(window, "_SETTLE_INTERVAL", 0):
            self.assertEqual(window._settled_geometry(1), geometries[-1])


if __name__ == "__main__":
    unittest.main()
