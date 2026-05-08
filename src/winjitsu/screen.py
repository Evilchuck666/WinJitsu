import threading

from Xlib import display as xdisplay
from Xlib.ext import randr


_display: "xdisplay.Display | None" = None
_display_lock = threading.Lock()


def _get_display() -> xdisplay.Display:
    global _display
    if _display is None:
        with _display_lock:
            if _display is None:
                _display = xdisplay.Display()
    assert _display is not None
    return _display


def get_screens():
    display = _get_display()
    if not display.has_extension('RANDR'):
        raise RuntimeError("RandR extension not available.")
    root             = display.screen().root
    resources        = root.xrandr_get_screen_resources()
    config_timestamp = resources.config_timestamp  # config_timestamp, NOT timestamp — timestamp causes BadMatch on some drivers
    primary_id       = root.xrandr_get_output_primary().output

    primary = None
    others  = []

    for output_id in resources.outputs:
        output_info = display.xrandr_get_output_info(output_id, config_timestamp)
        if output_info.connection != randr.Connected or not output_info.crtc:
            continue
        crtc_info       = display.xrandr_get_crtc_info(output_info.crtc, config_timestamp)
        screen_geometry = {"width": crtc_info.width, "height": crtc_info.height,
                           "x": crtc_info.x, "y": crtc_info.y}
        if output_id == primary_id:
            primary = screen_geometry
        else:
            others.append(screen_geometry)

    return primary, others


def find_screen_for_window(window) -> dict:
    """Return the screen dict that contains the window center."""
    primary, others = get_screens()
    if not primary:
        s = _get_display().screen()
        return {"x": 0, "y": 0, "width": s.width_in_pixels, "height": s.height_in_pixels}

    all_screens     = [primary] + others
    window_center_x = window["X"] + window["WIDTH"] / 2
    window_center_y = window["Y"] + window["HEIGHT"] / 2

    def _contains(s):
        return (s["x"] <= window_center_x < s["x"] + s["width"]
                and s["y"] <= window_center_y < s["y"] + s["height"])

    def _dist(s):
        return (window_center_x - (s["x"] + s["width"]  / 2)) ** 2 \
             + (window_center_y - (s["y"] + s["height"] / 2)) ** 2

    # Use the screen whose bounds contain the window center. If the center falls
    # outside all screens (e.g., a window is mostly off-screen), fall back to the
    # nearest screen by distance from its center.
    return next((s for s in all_screens if _contains(s)), min(all_screens, key=_dist))


def get_screen_for_window(window):
    s = find_screen_for_window(window)
    return s["width"], s["height"], s["x"], s["y"]
