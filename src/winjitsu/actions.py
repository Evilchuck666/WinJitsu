from .config import cfg
from .screen import get_screens, get_screen_for_window, find_screen_for_window
from .window import get_window_position, get_wm_class, move_window, geometry_of, geometry_matches
from .cache  import load_state, save_state, clear_cache, _update_state


VALID_ACTIONS = ["N", "S", "E", "W", "NE", "NW", "SE", "SW", "C", "F", "U", "TF", "TD", "CC"]
DIRECTION_ACTIONS = {"N", "S", "E", "W", "NE", "NW", "SE", "SW", "C"}


def _move_and_remember(window, target):
    # Move first, then save where the window actually ended up, so later
    # comparisons are made against what xdotool will report.
    reached = move_window(window, *target)
    _update_state(window, target, reached)


# --- Grid snapping ---
def direction(direction_code):
    window = get_window_position()

    screen_width, screen_height, screen_origin_x, screen_origin_y = get_screen_for_window(window)

    half_width  = screen_width  / 2
    half_height = screen_height / 2

    centered_x = screen_origin_x + (screen_width  - window["WIDTH"])  / 2
    centered_y = screen_origin_y + (screen_height - window["HEIGHT"]) / 2

    targets_by_direction = {
        "N":  {"width": screen_width,    "height": half_height,      "x": screen_origin_x,              "y": screen_origin_y},
        "S":  {"width": screen_width,    "height": half_height,      "x": screen_origin_x,              "y": screen_origin_y + half_height},
        "E":  {"width": half_width,      "height": screen_height,    "x": screen_origin_x + half_width, "y": screen_origin_y},
        "W":  {"width": half_width,      "height": screen_height,    "x": screen_origin_x,              "y": screen_origin_y},
        "NE": {"width": half_width,      "height": half_height,      "x": screen_origin_x + half_width, "y": screen_origin_y},
        "NW": {"width": half_width,      "height": half_height,      "x": screen_origin_x,              "y": screen_origin_y},
        "SE": {"width": half_width,      "height": half_height,      "x": screen_origin_x + half_width, "y": screen_origin_y + half_height},
        "SW": {"width": half_width,      "height": half_height,      "x": screen_origin_x,              "y": screen_origin_y + half_height},
        "C":  {"width": window["WIDTH"], "height": window["HEIGHT"], "x": centered_x,                   "y": centered_y},
    }
    target = targets_by_direction[direction_code]

    _move_and_remember(window, (target["x"], target["y"], target["width"], target["height"]))


# --- Fullscreen ---
def _fullscreen_target(screen):
    screen_width, screen_height, screen_origin_x, screen_origin_y = screen
    padding = cfg.padding

    return (
        screen_origin_x + padding,
        screen_origin_y + padding,
        screen_width  - 2 * padding,
        screen_height - 2 * padding,
    )


def fullscreen(window=None, screen=None):
    window = window or get_window_position()
    screen = screen or get_screen_for_window(window)

    _move_and_remember(window, _fullscreen_target(screen))


def restore(window=None):
    window = window or get_window_position()

    saved_state = load_state(window["WINDOW"], get_wm_class(window["WINDOW"]))
    if saved_state is None:
        return "WARN: no cached state for this window"

    move_window(window, saved_state["X"], saved_state["Y"], saved_state["WIDTH"], saved_state["HEIGHT"])
    return None


def _is_fullscreen(window, fullscreen_target):
    current = geometry_of(window)

    # Fullscreened by WinJitsu and not moved since. The settled geometry can
    # differ from the target (size increments, WM constraints), so compare
    # with that one.
    cached_state = load_state(window["WINDOW"], get_wm_class(window["WINDOW"]))
    if (
            cached_state is not None
        and cached_state["_target"] == fullscreen_target
        and geometry_matches(current, cached_state["_reached"])
    ):
        return True

    return geometry_matches(current, fullscreen_target)


def toggle_fullscreen(window=None):
    window = window or get_window_position()
    screen = get_screen_for_window(window)

    if _is_fullscreen(window, _fullscreen_target(screen)):
        return restore(window)

    fullscreen(window, screen)
    return None


# --- Display ---
def toggle_display():
    window = get_window_position()

    primary_screen, other_screens = get_screens()
    if not primary_screen or not other_screens:
        return

    all_screens = [primary_screen] + other_screens

    current_screen       = find_screen_for_window(window, (primary_screen, other_screens))
    current_screen_index = all_screens.index(current_screen)

    target_screen_index = (current_screen_index + 1) % len(all_screens)
    target_screen       = all_screens[target_screen_index]

    # Preserve the window's relative offset on the new screen, clamped to its bounds
    target_x = target_screen["x"] + (window["X"] - current_screen["x"])
    target_x = max(target_screen["x"], min(target_x, target_screen["x"] + target_screen["width"]  - window["WIDTH"]))

    target_y = target_screen["y"] + (window["Y"] - current_screen["y"])
    target_y = max(target_screen["y"], min(target_y, target_screen["y"] + target_screen["height"] - window["HEIGHT"]))

    target  = (target_x, target_y, window["WIDTH"], window["HEIGHT"])
    reached = move_window(window, *target)
    if reached is None:
        return

    window_id = window["WINDOW"]

    target_home_state = {
        "WINDOW": window_id,
        "X": target_x, "Y": target_y,
        "WIDTH": window["WIDTH"], "HEIGHT": window["HEIGHT"],
        "SCREEN": target_screen_index,
    }

    save_state(window_id, target_home_state, target, reached, get_wm_class(window_id))


# --- Dispatcher ---
_ACTION_HANDLERS = {
    "F":  fullscreen,
    "U":  restore,
    "TF": toggle_fullscreen,
    "TD": toggle_display,
    "CC": clear_cache,
}

def dispatch(action_code):
    if action_code in DIRECTION_ACTIONS:
        direction(action_code)
        return None
    elif action_code in _ACTION_HANDLERS:
        return _ACTION_HANDLERS[action_code]()
    else:
        raise ValueError(f"Unknown action: {action_code!r}")
