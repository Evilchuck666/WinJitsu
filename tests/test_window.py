import subprocess
import unittest
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
        calls = []
        original_run = wm.run
        wm.run = lambda args, **kwargs: calls.append(args) or original_run(args)

        reached = window.move_window(window.get_window_position(), 0, 0, 960, 1080)

        self.assertEqual(calls[-1][1:], ["windowsize", "4242", "958", "1055", "windowmove", "4242", "0", "0"])
        self.assertEqual(reached, (0, 0, 960, 1080))

    def test_clamps_to_the_x_screen(self):
        wm = self.use(FakeWindowManager((200, 150, 800, 600)))

        reached = window.move_window(window.get_window_position(), 1500, -50, 800, 600)

        self.assertEqual(reached, (1120, 0, 800, 600))
        self.assertEqual(wm.frame, reached)

    def test_returns_none_when_xdotool_fails(self):
        wm = self.use(FakeWindowManager((200, 150, 800, 600)))
        current = window.get_window_position()
        wm.run = lambda args, **kwargs: subprocess.CompletedProcess(args, 1)

        self.assertIsNone(window.move_window(current, 0, 0, 960, 1080))


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
