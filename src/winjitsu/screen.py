import threading
from Xlib     import Xatom
from Xlib     import display as xdisplay
from Xlib     import error as xerror
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


def reset_display():
    """Forget the X connection, e.g. after the server closed it; the next use opens a new one."""
    global _display

    with _display_lock:
        if _display is not None:
            try:
                _display.close()
            except Exception:
                pass  # already broken
        _display = None


def get_screens():
    """(primary, others): the usable area of each active monitor, minus the space panels reserve."""
    display = _get_display()

    if not display.has_extension('RANDR'):
        raise RuntimeError("RandR extension not available.")

    root             = display.screen().root
    resources        = root.xrandr_get_screen_resources()
    config_timestamp = resources.config_timestamp  # config_timestamp, NOT timestamp — timestamp causes BadMatch on some drivers
    primary_id       = root.xrandr_get_output_primary().output

    monitors = []

    for output_id in resources.outputs:
        output_info = display.xrandr_get_output_info(output_id, config_timestamp)

        if output_info.connection != randr.Connected or not output_info.crtc:
            continue

        crtc_info       = display.xrandr_get_crtc_info(output_info.crtc, config_timestamp)

        screen_geometry = {
            "width":  crtc_info.width,
            "height": crtc_info.height,
            "x":      crtc_info.x,
            "y":      crtc_info.y
        }

        monitors.append((output_id, screen_geometry))

    screen = display.screen()
    struts = _read_struts(display, root, screen.width_in_pixels, screen.height_in_pixels)
    monitors = [
        (output_id, _apply_struts(geometry, struts, screen.width_in_pixels, screen.height_in_pixels))
        for output_id, geometry in monitors
    ]

    return _split_primary(monitors, primary_id)


def _read_struts(display, root, screen_width, screen_height):
    """_NET_WM_STRUT_PARTIAL of every managed window, the older _NET_WM_STRUT converted to it."""
    client_list = root.get_full_property(display.intern_atom("_NET_CLIENT_LIST"), Xatom.WINDOW)
    struts      = []

    for window_id in (client_list.value if client_list else []):
        window = display.create_resource_object("window", window_id)

        try:
            partial = window.get_full_property(display.intern_atom("_NET_WM_STRUT_PARTIAL"), Xatom.CARDINAL)
            simple  = None if partial else window.get_full_property(display.intern_atom("_NET_WM_STRUT"), Xatom.CARDINAL)
        except xerror.XError:
            continue  # closed in the meantime

        if partial is not None and len(partial.value) == 12:
            struts.append(tuple(int(value) for value in partial.value))
        elif simple is not None and len(simple.value) == 4:
            left, right, top, bottom = (int(value) for value in simple.value)
            last_x, last_y = screen_width - 1, screen_height - 1
            struts.append((left, right, top, bottom, 0, last_y, 0, last_y, 0, last_x, 0, last_x))

    return struts


def _apply_struts(monitor, struts, screen_width, screen_height):
    """The part of the monitor no strut reserves.

    Struts are measured from the edges of the whole X screen, so a reserved
    strip only shrinks the monitors it overlaps. A strip covering a monitor
    from edge to edge (a panel between two monitors, which EWMH can't express)
    is ignored rather than leaving the monitor without usable space.
    """
    monitor_x0, monitor_y0 = monitor["x"], monitor["y"]
    monitor_x1, monitor_y1 = monitor_x0 + monitor["width"], monitor_y0 + monitor["height"]
    left_edge, top_edge, right_edge, bottom_edge = monitor_x0, monitor_y0, monitor_x1, monitor_y1

    for (left, right, top, bottom,
         left_y0, left_y1, right_y0, right_y1, top_x0, top_x1, bottom_x0, bottom_x1) in struts:
        # Reserved strips as (side, x0, y0, x1, y1), end coordinates exclusive.
        strips = [
            ("left",   0,                    left_y0,               left,          left_y1 + 1),
            ("right",  screen_width - right, right_y0,              screen_width,  right_y1 + 1),
            ("top",    top_x0,               0,                     top_x1 + 1,    top),
            ("bottom", bottom_x0,            screen_height - bottom, bottom_x1 + 1, screen_height),
        ]

        for side, x0, y0, x1, y1 in strips:
            if x0 >= x1 or y0 >= y1:
                continue  # this side reserves nothing
            if x0 >= monitor_x1 or x1 <= monitor_x0 or y0 >= monitor_y1 or y1 <= monitor_y0:
                continue  # doesn't touch this monitor

            if side == "left" and x1 < monitor_x1:
                left_edge = max(left_edge, x1)
            elif side == "right" and x0 > monitor_x0:
                right_edge = min(right_edge, x0)
            elif side == "top" and y1 < monitor_y1:
                top_edge = max(top_edge, y1)
            elif side == "bottom" and y0 > monitor_y0:
                bottom_edge = min(bottom_edge, y0)

    return {
        "x":      left_edge,
        "y":      top_edge,
        "width":  max(1, right_edge  - left_edge),
        "height": max(1, bottom_edge - top_edge),
    }


def _split_primary(monitors, primary_id):
    """(primary, others) from (output_id, geometry) pairs of the active monitors."""
    primary = None
    others  = []

    for output_id, screen_geometry in monitors:
        if output_id == primary_id:
            primary = screen_geometry
        else:
            others.append(screen_geometry)

    # No primary output set (no `xrandr --primary`, reported as 0) or it is
    # disabled: use the first active monitor instead of treating the whole X
    # screen as a single monitor.
    if primary is None and others:
        primary = others.pop(0)

    return primary, others


def find_screen_for_window(window, screens=None) -> dict:
    """Return the screen dict that contains the window center."""
    if screens is None:
        primary, others = get_screens()
    else:
        primary, others = screens

    if not primary:
        screen = _get_display().screen()
        return {"x": 0, "y": 0, "width": screen.width_in_pixels, "height": screen.height_in_pixels}

    all_screens     = [primary] + others

    window_center_x = window["X"] + window["WIDTH"] / 2
    window_center_y = window["Y"] + window["HEIGHT"] / 2

    def _contains(scr):
        return (
                scr["x"] <= window_center_x < scr["x"] + scr["width"]
            and scr["y"] <= window_center_y < scr["y"] + scr["height"]
        )

    def _dist(scr):
        return (window_center_x - (scr["x"] + scr["width"]  / 2)) ** 2 \
             + (window_center_y - (scr["y"] + scr["height"] / 2)) ** 2

    # Use the screen whose bounds contain the window center. If the center falls
    # outside all screens (e.g., a window is mostly off-screen), fall back to the
    # nearest screen by distance from its center.
    return next((s for s in all_screens if _contains(s)), min(all_screens, key=_dist))


def get_screen_for_window(window):
    screen = find_screen_for_window(window)
    return screen["width"], screen["height"], screen["x"], screen["y"]
