import subprocess

from .config import _CFG
from .screen import _get_display


def get_window_position():
    try:
        wid = subprocess.check_output(["xdotool", "getactivewindow"]).decode().strip()
        out = subprocess.check_output(["xdotool", "getwindowgeometry", "--shell", wid]).decode()
        data = {}
        for line in out.splitlines():
            k, v = line.split("=", 1)
            data[k] = int(v)
        return data
    except subprocess.CalledProcessError:
        raise RuntimeError("Could not get window position. Is xdotool installed?")


def get_wm_class(window_id):
    try:
        return subprocess.check_output(
            ["xdotool", "getwindowclassname", str(window_id)]
        ).decode().strip()
    except subprocess.CalledProcessError:
        return None


def move_window(target_w, target_h, window_id, current_w, current_h, current_x, current_y, target_x, target_y):
    def _ease(t):
        return t * t * (3.0 - 2.0 * t)

    screen = _get_display().screen()
    dw, dh = screen.width_in_pixels, screen.height_in_pixels
    target_w = min(target_w, dw)
    target_h = min(target_h, dh)
    target_x = max(0, min(target_x, dw - target_w))
    target_y = max(0, min(target_y, dh - target_h))

    wid = str(window_id)
    for i in range(1, _CFG.steps + 1):
        t = _ease(i / _CFG.steps)
        w = current_w + (target_w - current_w) * t
        h = current_h + (target_h - current_h) * t
        x = current_x + (target_x - current_x) * t
        y = current_y + (target_y - current_y) * t
        subprocess.run([
            "xdotool",
            "windowsize", wid, str(round(w)), str(round(h)),
            "windowmove", wid, str(round(x)), str(round(y)),
        ])
