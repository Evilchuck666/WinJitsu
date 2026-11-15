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

        self.assertEqual(wm.commands[-1], ["windowsize", "4242", "958", "1055", "windowmove", "4242", "0", "0"])
        self.assertEqual(reached, (0, 0, 960, 1080))

    def test_shows_every_step_eased_and_ends_on_the_target(self):
        wm = self.use(FakeWindowManager((1000, 500, 800, 600)))

        with mock.patch.object(window.cfg, "steps", 30):
            window.move_window(window.get_window_position(), 0, 0, 960, 1080)

        self.assertEqual(len(wm.commands), 30, "no step may be skipped")
        xs = [int(command[6]) for command in wm.commands]
        self.assertEqual(xs, sorted(xs, reverse=True), "the window only moves towards the target")
        self.assertLess(xs[0] - xs[1], xs[14] - xs[15], "smoothstep: slow start")
        self.assertLess(xs[-2] - xs[-1], xs[14] - xs[15], "smoothstep: slow end")
        self.assertEqual(wm.commands[-1], ["windowsize", "4242", "960", "1080", "windowmove", "4242", "0", "0"])

    def test_clamps_to_the_x_screen(self):
        wm = self.use(FakeWindowManager((200, 150, 800, 600)))

        reached = window.move_window(window.get_window_position(), 1500, -50, 800, 600)

        self.assertEqual(reached, (1120, 0, 800, 600))
        self.assertEqual(wm.frame, reached)

    def test_returns_none_when_the_window_closes(self):
        wm = self.use(FakeWindowManager((200, 150, 800, 600)))
        current = window.get_window_position()
        original_run = wm.run

        def close_during_the_animation(args, **kwargs):
            result = original_run(args, **kwargs)
            wm.closed = True
            return result

        wm.run = close_during_the_animation
        self.assertIsNone(window.move_window(current, 0, 0, 960, 1080))
        self.assertEqual(len(wm.commands), 2, "it stops at the first failed step")

    def test_reports_a_missing_xdotool(self):
        wm = self.use(FakeWindowManager((200, 150, 800, 600)))
        current = window.get_window_position()

        def no_xdotool(args, **kwargs):
            raise FileNotFoundError("xdotool")

        wm.run = no_xdotool
        with self.assertRaisesRegex(RuntimeError, "xdotool is not installed"):
            window.move_window(current, 0, 0, 960, 1080)


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
