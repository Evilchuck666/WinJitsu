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


def get_screen_for_window(window):
    primary, others = get_screens()
    if not primary:
        default_screen = _get_display().screen()
        return default_screen.width_in_pixels, default_screen.height_in_pixels, 0, 0

    all_screens     = [primary] + others
    window_center_x = window["X"] + window["WIDTH"] / 2
    window_center_y = window["Y"] + window["HEIGHT"] / 2

    def _dist(screen_candidate):
        screen_center_x = screen_candidate["x"] + screen_candidate["width"] / 2
        screen_center_y = screen_candidate["y"] + screen_candidate["height"] / 2
        x_distance = window_center_x - screen_center_x
        y_distance = window_center_y - screen_center_y
        return x_distance ** 2 + y_distance ** 2

    screen = next(
        (screen_candidate for screen_candidate in all_screens
         if screen_candidate["x"] <= window_center_x < screen_candidate["x"] + screen_candidate["width"]
         and screen_candidate["y"] <= window_center_y < screen_candidate["y"] + screen_candidate["height"]),
        min(all_screens, key=_dist),
    )
    return screen["width"], screen["height"], screen["x"], screen["y"]
