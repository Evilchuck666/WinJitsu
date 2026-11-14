import unittest

from winjitsu import screen


LEFT  = {"x": 0,    "y": 0, "width": 1920, "height": 1080}
RIGHT = {"x": 1920, "y": 0, "width": 2560, "height": 1440}


class SplitPrimaryTest(unittest.TestCase):
    def test_uses_the_primary_output(self):
        self.assertEqual(screen._split_primary([(10, LEFT), (20, RIGHT)], 20), (RIGHT, [LEFT]))

    def test_without_primary_output_uses_the_first_monitor(self):
        # RandR reports output 0 when no primary output is set.
        self.assertEqual(screen._split_primary([(10, LEFT), (20, RIGHT)], 0), (LEFT, [RIGHT]))

    def test_disabled_primary_output_uses_the_first_monitor(self):
        self.assertEqual(screen._split_primary([(10, LEFT), (20, RIGHT)], 30), (LEFT, [RIGHT]))

    def test_no_monitors(self):
        self.assertEqual(screen._split_primary([], 0), (None, []))


class FindScreenTest(unittest.TestCase):
    def _window(self, x, y, width, height):
        return {"X": x, "Y": y, "WIDTH": width, "HEIGHT": height}

    def test_monitor_containing_the_window_center(self):
        self.assertEqual(screen.find_screen_for_window(self._window(1500, 100, 1000, 500), (LEFT, [RIGHT])), RIGHT)
        self.assertEqual(screen.find_screen_for_window(self._window(1000, 100, 1000, 500), (LEFT, [RIGHT])), LEFT)

    def test_center_outside_every_monitor_uses_the_nearest(self):
        # Below the left monitor: the X screen is 1440 tall because of the right one.
        self.assertEqual(screen.find_screen_for_window(self._window(100, 1200, 200, 200), (LEFT, [RIGHT])), LEFT)
        self.assertEqual(screen.find_screen_for_window(self._window(5000, 500, 200, 200), (LEFT, [RIGHT])), RIGHT)


if __name__ == "__main__":
    unittest.main()
