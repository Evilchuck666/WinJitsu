from .config import _CFG
from .screen import get_screens, get_screen_for_window
from .window import get_window_position, get_wm_class, move_window
from .cache import load_state, save_state, clear_cache, _update_state


VALID_ACTIONS = ["N", "S", "E", "W", "NE", "NW", "SE", "SW", "C", "F", "U", "TF", "TD", "CC"]
DIRECTION_ACTIONS = {"N", "S", "E", "W", "NE", "NW", "SE", "SW", "C"}

_ACTION_HANDLERS = {
    "F":  fullscreen,
    "U":  restore,
    "TF": toggle_fullscreen,
    "TD": toggle_display,
    "CC": clear_cache,
}


# --- Grid snapping ---
def direction(direction_code):
    window = get_window_position()
    screen_width, screen_height, screen_origin_x, screen_origin_y = get_screen_for_window(window)
    half_width = screen_width / 2
    half_height = screen_height / 2

    centered_x = screen_origin_x + (screen_width - window["WIDTH"]) / 2
    centered_y = screen_origin_y + (screen_height - window["HEIGHT"]) / 2

    targets_by_direction = {
        "N":  {"width": screen_width, "height": half_height,  "x": screen_origin_x,              "y": screen_origin_y},
        "S":  {"width": screen_width, "height": half_height,  "x": screen_origin_x,              "y": screen_origin_y + half_height},
        "E":  {"width": half_width,   "height": screen_height,"x": screen_origin_x + half_width, "y": screen_origin_y},
        "W":  {"width": half_width,   "height": screen_height,"x": screen_origin_x,              "y": screen_origin_y},
        "NE": {"width": half_width,   "height": half_height,  "x": screen_origin_x + half_width, "y": screen_origin_y},
        "NW": {"width": half_width,   "height": half_height,  "x": screen_origin_x,              "y": screen_origin_y},
        "SE": {"width": half_width,   "height": half_height,  "x": screen_origin_x + half_width, "y": screen_origin_y + half_height},
        "SW": {"width": half_width,   "height": half_height,  "x": screen_origin_x,              "y": screen_origin_y + half_height},
        "C":  {"width": window["WIDTH"], "height": window["HEIGHT"], "x": centered_x, "y": centered_y},
    }

    target = targets_by_direction[direction_code]
    target_width, target_height = target["width"], target["height"]
    target_x, target_y = target["x"], target["y"]

    _update_state(window, target_x, target_y, target_width, target_height)
    move_window(
        target_width, target_height,
        window["WINDOW"],
        window["WIDTH"], window["HEIGHT"],
        window["X"], window["Y"],
        target_x, target_y,
    )


# --- Fullscreen ---
def fullscreen(window=None, screen_width=None, screen_height=None, screen_origin_x=None, screen_origin_y=None):
    window = window or get_window_position()
    if screen_width is None:
        screen_width, screen_height, screen_origin_x, screen_origin_y = get_screen_for_window(window)

    padding = _CFG.padding
    target_x = screen_origin_x + padding
    target_y = screen_origin_y + padding
    target_width = screen_width - 2 * padding
    target_height = screen_height - 2 * padding

    _update_state(window, target_x, target_y, target_width, target_height)
    move_window(
        target_width, target_height,
        window["WINDOW"],
        window["WIDTH"], window["HEIGHT"],
        window["X"], window["Y"],
        target_x, target_y,
    )


def restore(window=None):
    window = window or get_window_position()
    window_id = window["WINDOW"]
    saved_state = load_state(window_id, get_wm_class(window_id))
    if saved_state is None:
        return

    move_window(
        saved_state["WIDTH"], saved_state["HEIGHT"],
        window_id,
        window["WIDTH"], window["HEIGHT"],
        window["X"], window["Y"],
        saved_state["X"], saved_state["Y"],
    )


def toggle_fullscreen(window=None):
    window = window or get_window_position()
    screen_width, screen_height, screen_origin_x, screen_origin_y = get_screen_for_window(window)

    padding = _CFG.padding
    fullscreen_width = screen_width - 2 * padding
    fullscreen_height = screen_height - 2 * padding

    is_already_fullscreen = (
        window["WIDTH"] == fullscreen_width
        and window["HEIGHT"] == fullscreen_height
    )

    if is_already_fullscreen:
        restore(window)
    else:
        fullscreen(window, screen_width, screen_height, screen_origin_x, screen_origin_y)


# --- Display ---
def toggle_display():
    window = get_window_position()
    primary_screen, other_screens = get_screens()
    if not primary_screen or not other_screens:
        return

    all_screens = [primary_screen] + other_screens
    window_center_x = window["X"] + window["WIDTH"] / 2
    window_center_y = window["Y"] + window["HEIGHT"] / 2

    def _distance_to_screen_center(screen):
        screen_center_x = screen["x"] + screen["width"] / 2
        screen_center_y = screen["y"] + screen["height"] / 2
        return (window_center_x - screen_center_x) ** 2 + (window_center_y - screen_center_y) ** 2

    def _contains_window_center(screen):
        return (screen["x"] <= window_center_x < screen["x"] + screen["width"]
                and screen["y"] <= window_center_y < screen["y"] + screen["height"])

    current_screen = next(
        (screen for screen in all_screens if _contains_window_center(screen)),
        min(all_screens, key=_distance_to_screen_center),
    )
    current_screen_index = all_screens.index(current_screen)
    target_screen_index = (current_screen_index + 1) % len(all_screens)
    target_screen = all_screens[target_screen_index]

    target_x = target_screen["x"] + (window["X"] - current_screen["x"])
    target_y = target_screen["y"] + (window["Y"] - current_screen["y"])

    window_id = window["WINDOW"]
    wm_class = get_wm_class(window_id)
    target_home_state = {
        "WINDOW": window_id,
        "X": target_x, "Y": target_y,
        "WIDTH": window["WIDTH"], "HEIGHT": window["HEIGHT"],
        "SCREEN": target_screen_index,
    }
    save_state(window_id, target_home_state, target_x, target_y, window["WIDTH"], window["HEIGHT"], wm_class)
    move_window(
        window["WIDTH"], window["HEIGHT"],
        window_id,
        window["WIDTH"], window["HEIGHT"],
        window["X"], window["Y"],
        target_x, target_y,
    )


# --- Dispatcher ---
def dispatch(action_code):
    if action_code in DIRECTION_ACTIONS:
        direction(action_code)
    elif action_code in _ACTION_HANDLERS:
        _ACTION_HANDLERS[action_code]()
    else:
        raise ValueError(f"Unknown action: {action_code!r}")
