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


def _strut(left=0, right=0, top=0, bottom=0, left_y=(0, 0), right_y=(0, 0), top_x=(0, 0), bottom_x=(0, 0)):
    return (left, right, top, bottom, *left_y, *right_y, *top_x, *bottom_x)


class ApplyStrutsTest(unittest.TestCase):
    # LEFT is 1920x1080 and RIGHT 2560x1440 to its right: the X screen is 4480x1440.
    SIZE = (4480, 1440)

    def test_without_struts_the_monitor_is_unchanged(self):
        self.assertEqual(screen._apply_struts(LEFT, [], *self.SIZE), LEFT)

    def test_bottom_panel_on_the_shorter_monitor(self):
        # Struts count from the X screen edge: 1440 - 1080 + 32.
        panel = _strut(bottom=392, bottom_x=(0, 1919))

        self.assertEqual(screen._apply_struts(LEFT,  [panel], *self.SIZE), {"x": 0, "y": 0, "width": 1920, "height": 1048})
        self.assertEqual(screen._apply_struts(RIGHT, [panel], *self.SIZE), RIGHT)

    def test_top_and_left_panels(self):
        top_panel  = _strut(top=30, top_x=(1920, 4479))
        left_panel = _strut(left=48, left_y=(0, 1079))

        self.assertEqual(screen._apply_struts(RIGHT, [top_panel, left_panel], *self.SIZE),
                         {"x": 1920, "y": 30, "width": 2560, "height": 1410})
        self.assertEqual(screen._apply_struts(LEFT,  [top_panel, left_panel], *self.SIZE),
                         {"x": 48, "y": 0, "width": 1872, "height": 1080})

    def test_strip_covering_a_whole_monitor_is_ignored_for_it(self):
        # A panel on RIGHT's left edge can only be declared as a left strut that crosses LEFT entirely.
        panel = _strut(left=1968, left_y=(0, 1439))

        self.assertEqual(screen._apply_struts(LEFT,  [panel], *self.SIZE), LEFT)
        self.assertEqual(screen._apply_struts(RIGHT, [panel], *self.SIZE), {"x": 1968, "y": 0, "width": 2512, "height": 1440})


if __name__ == "__main__":
    unittest.main()
