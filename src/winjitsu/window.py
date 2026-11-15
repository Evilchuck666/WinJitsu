import subprocess
import time
from Xlib     import X, Xatom
from Xlib     import error as xerror
from Xlib     import protocol
from .config  import cfg
from .screen  import _get_display


# Geometries are (x, y, width, height) of the window's outer frame, decorations
# included. xdotool reports the client area but, following ICCCM, window
# managers place the frame at the position a ConfigureWindow request asks for
# while the size is the client area's, so mixing the two makes decorated
# windows drift and never match what WinJitsu saved.
#
# xdotool reads the active window, its geometry and class; the animation talks
# to the X server directly, one ConfigureWindow request per frame.

# Pixels two geometries may differ by and still count as the same position.
GEOMETRY_TOLERANCE = 2

_SETTLE_ATTEMPTS = 10
_SETTLE_INTERVAL = 0.02

# Seconds per animation step: cfg.steps steps last about steps × FRAME_INTERVAL
# whatever the speed of the machine (25 steps ≈ 0.17 s).
FRAME_INTERVAL = 1 / 144

# Window managers ignore moves and resizes of windows in these states.
_BLOCKING_STATES = ("_NET_WM_STATE_MAXIMIZED_VERT", "_NET_WM_STATE_MAXIMIZED_HORZ", "_NET_WM_STATE_FULLSCREEN")


def geometry_of(window):
    return window["X"], window["Y"], window["WIDTH"], window["HEIGHT"]


def geometry_matches(first, second, tolerance=GEOMETRY_TOLERANCE):
    if first is None or second is None:
        return False

    return all(abs(a - b) <= tolerance for a, b in zip(first, second))


def _client_to_frame(client_geometry, extents):
    left, right, top, bottom = extents
    x, y, width, height = client_geometry
    return x - left, y - top, width + left + right, height + top + bottom


def get_frame_extents(window_id):
    """(left, right, top, bottom) decoration sizes from _NET_FRAME_EXTENTS, zeros when unknown."""
    display = _get_display()

    try:
        window        = display.create_resource_object("window", int(window_id))
        extents_reply = window.get_full_property(display.intern_atom("_NET_FRAME_EXTENTS"), Xatom.CARDINAL)
    except (xerror.XError, ValueError):
        return 0, 0, 0, 0

    if extents_reply is None or extents_reply.format != 32 or len(extents_reply.value) != 4:
        return 0, 0, 0, 0

    left, right, top, bottom = (int(value) for value in extents_reply.value)
    return left, right, top, bottom


def _xdotool(*args):
    try:
        return subprocess.check_output(["xdotool", *args], stderr=subprocess.DEVNULL).decode().strip()
    except FileNotFoundError:
        raise RuntimeError("xdotool is not installed or not in PATH.") from None


def get_window_geometry(window_id):
    try:
        geometry_output = _xdotool("getwindowgeometry", "--shell", str(window_id))
        window_geometry = {}

        for line in geometry_output.splitlines():
            if "=" not in line:
                continue

            key, value = line.split("=", 1)
            window_geometry[key] = int(value)
    except (subprocess.CalledProcessError, ValueError):
        raise RuntimeError(f"Could not read the geometry of window {window_id}; it may have closed.") from None

    frame = _client_to_frame(geometry_of(window_geometry), get_frame_extents(window_geometry["WINDOW"]))
    window_geometry["X"], window_geometry["Y"], window_geometry["WIDTH"], window_geometry["HEIGHT"] = frame
    return window_geometry


def get_window_position():
    try:
        window_id = _xdotool("getactivewindow")
    except subprocess.CalledProcessError:
        raise RuntimeError("No active window.") from None

    return get_window_geometry(window_id)


def get_wm_class(window_id):
    try:
        return _xdotool("getwindowclassname", str(window_id))
    except subprocess.CalledProcessError:
        return None


def _ignore_x_error(*_args):
    pass


def _configure(window_id, x, y, client_width, client_height):
    """Place the frame at (x, y) and size the client area, in a single request."""
    display = _get_display()
    window  = display.create_resource_object("window", int(window_id))

    # Errors (the window closed meanwhile) arrive later and are ignored here:
    # the geometry read after the animation reports them.
    window.configure(x=x, y=y, width=client_width, height=client_height, onerror=_ignore_x_error)
    display.flush()


def _clear_blocking_states(window_id):
    """Ask the window manager to drop the maximized and fullscreen states; True if any was set."""
    display    = _get_display()
    state_atom = display.intern_atom("_NET_WM_STATE")
    window     = display.create_resource_object("window", int(window_id))

    try:
        state_reply = window.get_full_property(state_atom, Xatom.ATOM)
    except xerror.XError:
        return False

    current_states = set(state_reply.value) if state_reply else set()
    blocking       = [display.intern_atom(name) for name in _BLOCKING_STATES]
    present        = [atom for atom in blocking if atom in current_states]
    if not present:
        return False

    # _NET_WM_STATE changes up to two states per message (action 0 = remove,
    # source 1 = normal application).
    root = display.screen().root
    for first, second in zip(present[::2], present[1::2] + [0]):
        event = protocol.event.ClientMessage(window=window, client_type=state_atom, data=(32, [0, first, second, 1, 0]))
        root.send_event(event, event_mask=X.SubstructureRedirectMask | X.SubstructureNotifyMask)
    display.sync()

    # Wait until the window manager has applied it, or moves would still be ignored.
    for _ in range(_SETTLE_ATTEMPTS):
        try:
            state_reply = window.get_full_property(state_atom, Xatom.ATOM)
        except xerror.XError:
            break
        if not state_reply or not set(state_reply.value) & set(present):
            break
        time.sleep(_SETTLE_INTERVAL)

    return True


def _settled_geometry(window_id):
    # The window manager applies the last move asynchronously: read until two
    # consecutive reads agree so the saved geometry is where the window ended up.
    previous = None

    for _ in range(_SETTLE_ATTEMPTS):
        try:
            current = geometry_of(get_window_geometry(window_id))
        except RuntimeError:
            return None

        if current == previous:
            break

        previous = current
        time.sleep(_SETTLE_INTERVAL)

    return previous


def move_window(window, target_x, target_y, target_width, target_height):
    """Animate the window's frame to the target geometry.

    Returns the frame geometry the window settled at, which can differ from the
    target (clamping, size increments, window manager constraints), or None if
    the window could not be moved.
    """
    def _ease(t):
        # smoothstep: eases in and out, producing natural-feeling animation
        return t * t * (3.0 - 2.0 * t)

    display_screen = _get_display().screen()
    display_width  = int(display_screen.width_in_pixels)
    display_height = int(display_screen.height_in_pixels)

    target_width  = min(target_width,  display_width)
    target_height = min(target_height, display_height)

    # Clamp to display bounds so the window never moves off-screen
    target_x = max(0, min(target_x, display_width  - target_width))
    target_y = max(0, min(target_y, display_height - target_height))

    current_x, current_y, current_w, current_h = geometry_of(window)

    # Unmaximizing makes the window manager put the window back at its old
    # size; the animation still starts from the geometry it had when maximized.
    # Decorations are read afterwards, some window managers trim them on
    # maximized windows.
    _clear_blocking_states(window["WINDOW"])
    left, right, top, bottom = get_frame_extents(window["WINDOW"])

    steps   = max(1, cfg.steps)
    started = time.monotonic()
    step    = 0

    while step < steps:
        if FRAME_INTERVAL > 0:
            # Running late (busy X server or window manager): jump to the step
            # that is due, so the animation keeps its duration.
            due_step = int((time.monotonic() - started) / FRAME_INTERVAL) + 1
            step     = min(steps, max(step + 1, due_step))
        else:
            step += 1

        ease_factor    = _ease(step / steps)
        interp_width   = current_w + (target_width  - current_w) * ease_factor
        interp_height  = current_h + (target_height - current_h) * ease_factor
        interp_x       = current_x + (target_x - current_x) * ease_factor
        interp_y       = current_y + (target_y - current_y) * ease_factor

        # The position is the frame's; the size is the client area's.
        client_width   = max(1, round(interp_width)  - left - right)
        client_height  = max(1, round(interp_height) - top  - bottom)
        _configure(window["WINDOW"], round(interp_x), round(interp_y), client_width, client_height)

        if step < steps and FRAME_INTERVAL > 0:
            time.sleep(max(0.0, started + step * FRAME_INTERVAL - time.monotonic()))

    return _settled_geometry(window["WINDOW"])
