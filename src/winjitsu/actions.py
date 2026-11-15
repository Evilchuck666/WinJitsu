from .config import cfg
from .screen import get_screens, get_screen_for_window, find_screen_for_window
from .window import (
    get_window_position, get_wm_class, move_window, geometry_of, geometry_matches,
    restore_states, _clear_blocking_states, _settled_geometry,
)
from .cache  import push_entry, top_entry, pop_entry, clear_cache, CACHE_ERRORS
from .client import VALID_ACTIONS  # noqa: F401  (re-exported, the list lives with the client)


DIRECTION_ACTIONS = {"N", "S", "E", "W", "NE", "NW", "SE", "SW", "C"}

# Screens are (width, height, origin_x, origin_y) tuples of a monitor's usable
# area; geometries and targets are (x, y, width, height) of the window frame.


def _move_and_push(window, target):
    # Every action goes on the window's undo history: where it was before
    # (with the window manager states it had), what was asked for and where
    # it actually ended up, which is what xdotool will report later. The
    # history is an extra: if it can't be saved, the window has still moved.
    window_id = window["WINDOW"]
    wm_class  = get_wm_class(window_id)

    # A maximized window has to be released before it can move. The geometry
    # the window manager gives back is the one to return to, maximized again,
    # on undo.
    states = _clear_blocking_states(window_id)
    before = geometry_of(window)
    if states:
        before = _settled_geometry(window_id) or before

    target  = tuple(int(round(value)) for value in target)
    reached = move_window(window, *target)

    if reached is None or wm_class is None:
        return None
    if not states and geometry_matches(before, reached):
        return None  # nothing changed: not worth an undo step

    try:
        push_entry(window_id, wm_class, before, states, target, reached)
    except CACHE_ERRORS as error:
        return f"WARN: moved, but the undo history could not be saved ({error})"

    return None


def _grid_targets(screen):
    """Halves, quarters and fullscreen (F, minus padding) of a screen, in whole pixels."""
    width, height, origin_x, origin_y = screen

    # The second half gets the odd pixel, so the two halves cover the screen exactly.
    left_w,  right_w  = width  // 2, width  - width  // 2
    top_h,   bottom_h = height // 2, height - height // 2
    right_x, bottom_y = origin_x + left_w, origin_y + top_h
    padding = cfg.padding

    return {
        "N":  (origin_x, origin_y, width,   top_h),
        "S":  (origin_x, bottom_y, width,   bottom_h),
        "W":  (origin_x, origin_y, left_w,  height),
        "E":  (right_x,  origin_y, right_w, height),
        "NW": (origin_x, origin_y, left_w,  top_h),
        "NE": (right_x,  origin_y, right_w, top_h),
        "SW": (origin_x, bottom_y, left_w,  bottom_h),
        "SE": (right_x,  bottom_y, right_w, bottom_h),
        "F":  (origin_x + padding, origin_y + padding, width - 2 * padding, height - 2 * padding),
    }


def _is_at(window, target, last_action):
    """Whether the window is at the target, or still where moving it there left it.

    The geometry a move settles at can differ from the target (size
    increments, window manager constraints), so the last action's counts too.
    """
    current = geometry_of(window)

    if (
            last_action is not None
        and last_action["target"] == tuple(target)
        and geometry_matches(current, last_action["reached"])
    ):
        return True

    return geometry_matches(current, target)


def _last_action(window):
    return top_entry(window["WINDOW"], get_wm_class(window["WINDOW"]))


# --- Grid snapping ---
def direction(direction_code):
    window = get_window_position()
    screen = get_screen_for_window(window)

    if direction_code == "C":
        width, height, origin_x, origin_y = screen
        target = (
            origin_x + (width  - window["WIDTH"])  // 2,
            origin_y + (height - window["HEIGHT"]) // 2,
            window["WIDTH"], window["HEIGHT"],
        )
    else:
        target = _grid_targets(screen)[direction_code]

    return _move_and_push(window, target)


# --- Fullscreen ---
def fullscreen(window=None, screen=None):
    window = window or get_window_position()
    screen = screen or get_screen_for_window(window)

    return _move_and_push(window, _grid_targets(screen)["F"])


def toggle_fullscreen(window=None):
    window = window or get_window_position()
    screen = get_screen_for_window(window)

    # Leaving fullscreen is undoing the move that entered it.
    if _is_at(window, _grid_targets(screen)["F"], _last_action(window)):
        return undo(window)

    return fullscreen(window, screen)


# --- Undo ---
def undo(window=None):
    window    = window or get_window_position()
    window_id = window["WINDOW"]
    wm_class  = get_wm_class(window_id)

    last_action = top_entry(window_id, wm_class)
    if last_action is None:
        return "WARN: nothing to undo for this window"

    # Moved or maximized by hand since the last action: undo that first, back
    # to where the action left the window. The next undo undoes the action.
    if not geometry_matches(geometry_of(window), last_action["reached"]):
        move_window(window, *last_action["reached"])
        return None

    try:
        pop_entry(window_id, wm_class)
    except CACHE_ERRORS as error:
        return f"WARN: the undo history could not be updated ({error})"

    move_window(window, *last_action["before"])
    restore_states(window_id, last_action["states"])
    return None


# --- Display ---
def _as_screen(screen_dict):
    return screen_dict["width"], screen_dict["height"], screen_dict["x"], screen_dict["y"]


def _target_on_next_screen(window, current_screen, next_screen):
    # A window at a grid position (halves, quarters, F) takes the same position
    # on the next screen, so it fits whatever that screen's size.
    last_action     = _last_action(window)
    current_targets = _grid_targets(current_screen)

    for code, target in current_targets.items():
        if _is_at(window, target, last_action):
            return _grid_targets(next_screen)[code]

    # Anywhere else: same offset from the screen's corner and same size,
    # shrunk if the next screen is smaller, kept inside it.
    current_w, current_h, current_x, current_y = current_screen
    next_w,    next_h,    next_x,    next_y    = next_screen

    width  = min(window["WIDTH"],  next_w)
    height = min(window["HEIGHT"], next_h)
    x = max(next_x, min(next_x + (window["X"] - current_x), next_x + next_w - width))
    y = max(next_y, min(next_y + (window["Y"] - current_y), next_y + next_h - height))

    return x, y, width, height


def toggle_display():
    window = get_window_position()

    primary_screen, other_screens = get_screens()
    if not primary_screen or not other_screens:
        return None

    all_screens = [primary_screen] + other_screens

    current_screen = find_screen_for_window(window, (primary_screen, other_screens))
    next_screen    = all_screens[(all_screens.index(current_screen) + 1) % len(all_screens)]

    target = _target_on_next_screen(window, _as_screen(current_screen), _as_screen(next_screen))
    return _move_and_push(window, target)


# --- Dispatcher ---
_ACTION_HANDLERS = {
    "F":  fullscreen,
    "U":  undo,
    "TF": toggle_fullscreen,
    "TD": toggle_display,
    "CC": clear_cache,
}

def dispatch(action_code):
    if action_code in DIRECTION_ACTIONS:
        return direction(action_code)
    elif action_code in _ACTION_HANDLERS:
        return _ACTION_HANDLERS[action_code]()
    else:
        raise ValueError(f"Unknown action: {action_code!r}")
