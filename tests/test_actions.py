import shutil
import unittest
from unittest import mock

from fakes    import FakeSessionTestCase, FakeWindowManager
from winjitsu import actions, cache, config


DECORATIONS = (1, 1, 24, 1)  # left, right, top, bottom


class SnapAndRestoreTest(FakeSessionTestCase):
    def test_restore_returns_to_home(self):
        wm = self.use(FakeWindowManager((200, 150, 800, 600)))

        actions.dispatch("W")
        self.assertEqual(wm.frame, (0, 0, 960, 1080))

        actions.dispatch("U")
        self.assertEqual(wm.frame, (200, 150, 800, 600))

    def test_decorated_window_fills_the_target_and_restores_without_drift(self):
        wm = self.use(FakeWindowManager((200, 150, 800, 600), extents=DECORATIONS))

        actions.dispatch("W")
        self.assertEqual(wm.frame, (0, 0, 960, 1080))

        for _ in range(3):
            actions.dispatch("E")
            actions.dispatch("U")
            self.assertEqual(wm.frame, (200, 150, 800, 600))

    def test_home_survives_a_chain_of_snaps_on_a_decorated_window(self):
        wm = self.use(FakeWindowManager((200, 150, 800, 600), extents=DECORATIONS))

        for action in ("W", "NE", "SE", "C", "S"):
            actions.dispatch(action)

        actions.dispatch("U")
        self.assertEqual(wm.frame, (200, 150, 800, 600))

    def test_home_survives_snaps_of_a_window_with_size_increments(self):
        wm = self.use(FakeWindowManager((200, 150, 803, 614), increments=(9, 17), base=(2, 2)))

        actions.dispatch("N")
        self.assertNotEqual(wm.frame, (0, 0, 1920, 540), "the fake should not reach the exact target")

        actions.dispatch("SW")
        actions.dispatch("U")
        self.assertEqual(wm.frame, (200, 150, 803, 614))

    def test_moving_by_hand_sets_a_new_home(self):
        wm = self.use(FakeWindowManager((200, 150, 800, 600)))

        actions.dispatch("W")
        wm.frame = (300, 300, 640, 480)  # the user moves the window by hand

        actions.dispatch("E")
        actions.dispatch("U")
        self.assertEqual(wm.frame, (300, 300, 640, 480))


class ClampedTargetTest(FakeSessionTestCase):
    # Two monitors side by side: the X screen is 3840 wide.
    SCREENS      = ({"x": 0, "y": 0, "width": 1920, "height": 1080}, [{"x": 1920, "y": 0, "width": 1920, "height": 1080}])
    DISPLAY_SIZE = (3840, 1080)

    def test_home_survives_a_center_that_had_to_be_clamped(self):
        # Wider than its monitor, so C asks for x=1880 and the clamp to the
        # X screen leaves it at 1840.
        wm = self.use(FakeWindowManager((1700, 100, 2000, 600)))

        actions.dispatch("C")
        self.assertEqual(wm.frame, (1840, 240, 2000, 600))

        actions.dispatch("N")
        actions.dispatch("U")
        self.assertEqual(wm.frame, (1700, 100, 2000, 600))

    def test_toggle_display_keeps_size_and_offset(self):
        wm = self.use(FakeWindowManager((100, 100, 800, 600)))

        actions.dispatch("TD")
        self.assertEqual(wm.frame, (2020, 100, 800, 600))

        actions.dispatch("TD")
        self.assertEqual(wm.frame, (100, 100, 800, 600))


class ToggleFullscreenTest(FakeSessionTestCase):
    def test_round_trip(self):
        wm = self.use(FakeWindowManager((200, 150, 800, 600)))

        actions.dispatch("TF")
        self.assertEqual(wm.frame, (0, 0, 1920, 1080))

        actions.dispatch("TF")
        self.assertEqual(wm.frame, (200, 150, 800, 600))

    def test_round_trip_for_a_decorated_terminal(self):
        wm = self.use(FakeWindowManager((200, 150, 805, 622), extents=DECORATIONS, increments=(9, 17), base=(2, 2)))

        actions.dispatch("TF")
        self.assertNotEqual(wm.frame, (0, 0, 1920, 1080), "the fake should not reach the exact target")

        actions.dispatch("TF")
        self.assertEqual(wm.frame, (200, 150, 805, 622))

    def test_toggles_back_to_fullscreen_after_restoring(self):
        wm = self.use(FakeWindowManager((200, 150, 800, 600)))

        for _ in range(2):
            actions.dispatch("TF")
            self.assertEqual(wm.frame, (0, 0, 1920, 1080))
            actions.dispatch("TF")
            self.assertEqual(wm.frame, (200, 150, 800, 600))

    def test_warns_when_a_fullscreen_window_has_no_home(self):
        wm = self.use(FakeWindowManager((0, 0, 1920, 1080)))

        self.assertEqual(actions.dispatch("TF"), "WARN: no cached state for this window")
        self.assertEqual(wm.frame, (0, 0, 1920, 1080))


class GridTargetsTest(unittest.TestCase):
    def test_halves_cover_odd_sizes_exactly(self):
        with mock.patch.object(config.cfg, "padding", 0):
            targets = actions._grid_targets((1365, 767, 0, 0))

        self.assertEqual(targets["W"], (0,   0,   682,  767))
        self.assertEqual(targets["E"], (682, 0,   683,  767))
        self.assertEqual(targets["N"], (0,   0,   1365, 383))
        self.assertEqual(targets["S"], (0,   383, 1365, 384))

    def test_fullscreen_applies_the_padding(self):
        with mock.patch.object(config.cfg, "padding", 8):
            self.assertEqual(actions._grid_targets((1920, 1080, 1920, 0))["F"], (1928, 8, 1904, 1064))


class WorkAreaTest(FakeSessionTestCase):
    # A 32 px panel at the bottom: get_screens() reports the usable area.
    SCREENS = ({"x": 0, "y": 0, "width": 1920, "height": 1048}, [])

    def test_actions_stay_inside_the_work_area(self):
        wm = self.use(FakeWindowManager((200, 150, 800, 600)))

        actions.dispatch("C");  self.assertEqual(wm.frame, (560, 224, 800, 600))
        actions.dispatch("SW"); self.assertEqual(wm.frame, (0, 524, 960, 524))
        actions.dispatch("TF"); self.assertEqual(wm.frame, (0, 0, 1920, 1048))
        actions.dispatch("TF"); self.assertEqual(wm.frame, (200, 150, 800, 600))


class MixedMonitorsTest(FakeSessionTestCase):
    SCREENS      = ({"x": 0, "y": 0, "width": 1920, "height": 1080}, [{"x": 1920, "y": 0, "width": 2560, "height": 1440}])
    DISPLAY_SIZE = (4480, 1440)

    def test_fullscreen_stays_fullscreen_and_home_survives(self):
        wm = self.use(FakeWindowManager((2100, 200, 800, 600)))

        actions.dispatch("F");  self.assertEqual(wm.frame, (1920, 0, 2560, 1440))
        actions.dispatch("TD"); self.assertEqual(wm.frame, (0, 0, 1920, 1080))
        actions.dispatch("TD"); self.assertEqual(wm.frame, (1920, 0, 2560, 1440))
        actions.dispatch("U");  self.assertEqual(wm.frame, (2100, 200, 800, 600))

    def test_grid_position_is_kept_for_a_decorated_terminal(self):
        wm = self.use(FakeWindowManager((100, 100, 805, 622), extents=DECORATIONS, increments=(9, 17), base=(2, 2)))

        actions.dispatch("W")
        self.assertNotEqual(wm.frame, (0, 0, 960, 1080), "the fake should not reach the exact target")

        actions.dispatch("TD")  # W of the right monitor, (1920, 0, 1280, 1440), to the nearest cell
        self.assertEqual(wm.frame, (1920, 0, 1273, 1438))

        actions.dispatch("U")
        self.assertEqual(wm.frame, (100, 100, 805, 622))

    def test_free_window_keeps_size_and_offset_and_comes_back(self):
        wm = self.use(FakeWindowManager((100, 100, 800, 600)))

        actions.dispatch("TD"); self.assertEqual(wm.frame, (2020, 100, 800, 600))
        actions.dispatch("U");  self.assertEqual(wm.frame, (100, 100, 800, 600))

    def test_free_window_too_big_for_the_next_monitor_is_shrunk(self):
        wm = self.use(FakeWindowManager((2000, 100, 2400, 1300)))

        actions.dispatch("TD"); self.assertEqual(wm.frame, (0, 0, 1920, 1080))
        actions.dispatch("U");  self.assertEqual(wm.frame, (2000, 100, 2400, 1300))


class MaximizedWindowTest(FakeSessionTestCase):
    def test_a_maximized_window_can_be_snapped(self):
        wm = self.use(FakeWindowManager((0, 0, 1920, 1080), unmaximized_frame=(300, 200, 640, 400)))

        actions.dispatch("W")
        self.assertFalse(wm.maximized)
        self.assertEqual(wm.frame, (0, 0, 960, 1080))

        # Home is the geometry it had while maximized (not the maximized state).
        actions.dispatch("U")
        self.assertEqual(wm.frame, (0, 0, 1920, 1080))


class CacheFailureTest(FakeSessionTestCase):
    def test_state_database_removed_while_running(self):
        wm = self.use(FakeWindowManager((200, 150, 800, 600)))
        shutil.rmtree(cache.DB_PATH.parent)

        self.assertIsNone(actions.dispatch("W"))
        actions.dispatch("U")
        self.assertEqual(wm.frame, (200, 150, 800, 600))

    def test_broken_database_still_moves_and_warns(self):
        wm = self.use(FakeWindowManager((200, 150, 800, 600)))
        cache.DB_PATH.write_bytes(b"not a database " * 100)

        result = actions.dispatch("W")
        self.assertEqual(wm.frame, (0, 0, 960, 1080))
        self.assertTrue(result.startswith("WARN: moved, but the window state could not be saved"), result)

        self.assertEqual(actions.dispatch("U"), "WARN: no cached state for this window")


if __name__ == "__main__":
    unittest.main()
