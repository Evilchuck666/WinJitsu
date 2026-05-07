import threading

from Xlib import display as Xdisplay
from Xlib.ext import randr


_display: "Xdisplay.Display | None" = None
_display_lock = threading.Lock()


def _get_display() -> Xdisplay.Display:
    global _display
    if _display is None:
        with _display_lock:
            if _display is None:
                _display = Xdisplay.Display()
    return _display


def get_screens():
    display = _get_display()
    if not display.has_extension('RANDR'):
        raise RuntimeError("RandR extension not available.")
    root      = display.screen().root
    resources = root.xrandr_get_screen_resources()
    ts        = resources.config_timestamp  # config_timestamp, NOT timestamp — timestamp causes BadMatch on some drivers
    primary_id = root.xrandr_get_output_primary().output

    primary = None
    others  = []

    for output_id in resources.outputs:
        info = display.xrandr_get_output_info(output_id, ts)
        if info.connection != randr.Connected or not info.crtc:
            continue
        crtc = display.xrandr_get_crtc_info(info.crtc, ts)
        s = {"width": crtc.width, "height": crtc.height, "x": crtc.x, "y": crtc.y}
        if output_id == primary_id:
            primary = s
        else:
            others.append(s)

    return primary, others


def get_screen_for_window(win):
    primary, others = get_screens()
    if not primary:
        d = _get_display().screen()
        return d.width_in_pixels, d.height_in_pixels, 0, 0

    all_screens = [primary] + others
    win_cx = win["X"] + win["WIDTH"] / 2
    win_cy = win["Y"] + win["HEIGHT"] / 2

    def _dist(s):
        return (win_cx - (s["x"] + s["width"] / 2)) ** 2 + (win_cy - (s["y"] + s["height"] / 2)) ** 2

    screen = next(
        (s for s in all_screens
         if s["x"] <= win_cx < s["x"] + s["width"] and s["y"] <= win_cy < s["y"] + s["height"]),
        min(all_screens, key=_dist),
    )
    return screen["width"], screen["height"], screen["x"], screen["y"]
