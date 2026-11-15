"""A fake X11 session for the tests: xdotool and one window managed by an ICCCM window manager."""
import subprocess
import tempfile
import unittest
from contextlib import ExitStack
from pathlib    import Path
from types      import SimpleNamespace
from unittest   import mock

from winjitsu import actions, cache, config, screen, window


class FakeWindowManager:
    """Answers the xdotool calls WinJitsu makes for a single window.

    Like a real reparenting window manager, windowmove places the outer frame,
    windowsize sets the client area and getwindowgeometry reports the client
    area. Resize increments emulate terminals that only take whole cells. A
    maximized window ignores moves, like real window managers do, until
    WinJitsu drops the state; it then goes back to its unmaximized frame. Once
    closed, the window can't be moved or read any more.
    """

    WINDOW_ID = 4242

    def __init__(self, frame, extents=(0, 0, 0, 0), increments=(1, 1), base=(0, 0), wm_class="kitty",
                 unmaximized_frame=None):
        self.frame             = tuple(frame)
        self.extents           = extents
        self.increments        = increments
        self.base              = base
        self.wm_class          = wm_class
        self.moves             = 0
        self.maximized         = unmaximized_frame is not None
        self.unmaximized_frame = unmaximized_frame
        self.closed            = False
        self.commands          = []  # arguments of every windowsize/windowmove run, without "xdotool"

    def client(self):
        left, right, top, bottom = self.extents
        x, y, width, height = self.frame
        return x + left, y + top, width - left - right, height - top - bottom

    def _apply_increments(self, width, height):
        (increment_w, increment_h), (base_w, base_h) = self.increments, self.base
        return width - (width - base_w) % increment_w, height - (height - base_h) % increment_h

    def run(self, args, **kwargs):
        assert args[0] == "xdotool" and args[1] == "windowsize" and args[5] == "windowmove", args
        assert args[2] == args[6] == str(self.WINDOW_ID), args
        self.commands.append(list(args[1:]))

        if self.closed:
            return subprocess.CompletedProcess(args, 1)  # xdotool fails on a window that is gone
        if self.maximized:
            return subprocess.CompletedProcess(args, 0)  # ignored by the window manager, not an error

        client_width, client_height = self._apply_increments(int(args[3]), int(args[4]))
        left, right, top, bottom    = self.extents
        self.frame = (int(args[7]), int(args[8]), client_width + left + right, client_height + top + bottom)
        self.moves += 1
        return subprocess.CompletedProcess(args, 0)

    def clear_blocking_states(self, window_id):
        if not self.maximized:
            return False

        self.maximized = False
        self.frame     = tuple(self.unmaximized_frame)
        return True

    def check_output(self, args, **kwargs):
        command = args[1]

        if command == "getactivewindow":
            return f"{self.WINDOW_ID}\n".encode()

        if command == "getwindowgeometry":
            if self.closed:
                raise subprocess.CalledProcessError(1, args)
            x, y, width, height = self.client()
            return f"WINDOW={self.WINDOW_ID}\nX={x}\nY={y}\nWIDTH={width}\nHEIGHT={height}\nSCREEN=0\n".encode()

        if command == "getwindowclassname":
            return f"{self.wm_class}\n".encode()

        raise AssertionError(f"unexpected xdotool call: {args}")

    def patches(self, display_size):
        # Looked up on every call, so a test can replace methods afterwards.
        fake_subprocess = SimpleNamespace(
            run=lambda args, **kwargs: self.run(args, **kwargs),
            check_output=lambda args, **kwargs: self.check_output(args, **kwargs),
            CalledProcessError=subprocess.CalledProcessError,
            DEVNULL=subprocess.DEVNULL,
        )
        display_width, display_height = display_size
        fake_screen  = SimpleNamespace(width_in_pixels=display_width, height_in_pixels=display_height)
        fake_display = SimpleNamespace(screen=lambda: fake_screen)

        return [
            mock.patch.object(window, "subprocess",        fake_subprocess),
            mock.patch.object(window, "get_frame_extents", lambda window_id: self.extents),
            mock.patch.object(window, "_get_display",      lambda: fake_display),
            mock.patch.object(window, "_clear_blocking_states", lambda window_id: self.clear_blocking_states(window_id)),
        ]


class FakeSessionTestCase(unittest.TestCase):
    """Runs actions against a FakeWindowManager, fixed monitors and a temporary state database."""

    # (primary, others), in the format screen.get_screens() returns.
    SCREENS      = ({"x": 0, "y": 0, "width": 1920, "height": 1080}, [])
    DISPLAY_SIZE = (1920, 1080)

    def setUp(self):
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)

        temp_dir = self.stack.enter_context(tempfile.TemporaryDirectory())
        self.stack.enter_context(mock.patch.object(cache, "DB_PATH", Path(temp_dir) / "state.db"))
        self.stack.enter_context(mock.patch.object(config.cfg, "steps",   5))
        self.stack.enter_context(mock.patch.object(config.cfg, "padding", 0))
        self.stack.enter_context(mock.patch.object(window, "_SETTLE_INTERVAL", 0))

        primary, others = self.SCREENS

        def get_screen_for_window(win):
            found = screen.find_screen_for_window(win, (primary, others))
            return found["width"], found["height"], found["x"], found["y"]

        self.stack.enter_context(mock.patch.object(actions, "get_screens", lambda: (primary, list(others))))
        self.stack.enter_context(mock.patch.object(actions, "get_screen_for_window", get_screen_for_window))

        cache.init_db()

    def use(self, wm):
        for patch in wm.patches(self.DISPLAY_SIZE):
            self.stack.enter_context(patch)
        return wm
