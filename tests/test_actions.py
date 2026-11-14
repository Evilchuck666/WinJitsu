import unittest

from fakes    import FakeSessionTestCase, FakeWindowManager
from winjitsu import actions


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


if __name__ == "__main__":
    unittest.main()
