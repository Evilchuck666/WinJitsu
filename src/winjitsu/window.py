import subprocess

from .config import _CFG
from .screen import _get_display


def get_window_position():
    try:
        window_id       = subprocess.check_output(["xdotool", "getactivewindow"]).decode().strip()
        geometry_output = subprocess.check_output(["xdotool", "getwindowgeometry", "--shell", window_id]).decode()
        window_geometry = {}
        for line in geometry_output.splitlines():
            key, value = line.split("=", 1)
            window_geometry[key] = int(value)
        return window_geometry
    except subprocess.CalledProcessError:
        raise RuntimeError("Could not get window position. Is xdotool installed?")


def get_wm_class(window_id):
    try:
        return subprocess.check_output(
            ["xdotool", "getwindowclassname", str(window_id)]
        ).decode().strip()
    except subprocess.CalledProcessError:
        return None


def move_window(target_width, target_height, window_id, current_w, current_h, current_x, current_y, target_x, target_y):
    def _ease(t):
        # smoothstep: eases in and out, producing natural-feeling animation
        return t * t * (3.0 - 2.0 * t)

    display_screen = _get_display().screen()
    display_width, display_height = display_screen.width_in_pixels, display_screen.height_in_pixels
    target_width  = min(target_width,  display_width)
    target_height = min(target_height, display_height)
    # Clamp to display bounds so the window never moves off-screen
    target_x = max(0, min(target_x, display_width  - target_width))
    target_y = max(0, min(target_y, display_height - target_height))

    window_id_str = str(window_id)
    for step in range(1, _CFG.steps + 1):
        ease_factor    = _ease(step / _CFG.steps)
        interp_width   = current_w + (target_width  - current_w) * ease_factor
        interp_height  = current_h + (target_height - current_h) * ease_factor
        interp_x       = current_x + (target_x - current_x) * ease_factor
        interp_y       = current_y + (target_y - current_y) * ease_factor
        subprocess.run([
            "xdotool",
            "windowsize", window_id_str, str(round(interp_width)), str(round(interp_height)),
            "windowmove", window_id_str, str(round(interp_x)),     str(round(interp_y)),
        ])
