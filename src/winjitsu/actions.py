from .config import _CFG
from .screen import get_screens, get_screen_for_window
from .window import get_window_position, get_wm_class, move_window
from .cache import load_state, save_state, clear_cache, _update_state


VALID_ACTIONS = ["N", "S", "E", "W", "NE", "NW", "SE", "SW", "C", "F", "U", "TF", "TD", "CC"]


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


def toggle_display():
    win = get_window_position()
    primary, others = get_screens()
    if not primary or not others:
        return

    all_screens = [primary] + others
    win_cx = win["X"] + win["WIDTH"] / 2
    win_cy = win["Y"] + win["HEIGHT"] / 2

    def _dist(s):
        return (win_cx - (s["x"] + s["width"] / 2)) ** 2 + (win_cy - (s["y"] + s["height"] / 2)) ** 2

    current = next(
        (s for s in all_screens
         if s["x"] <= win_cx < s["x"] + s["width"] and s["y"] <= win_cy < s["y"] + s["height"]),
        min(all_screens, key=_dist),
    )
    target = all_screens[(all_screens.index(current) + 1) % len(all_screens)]

    tx = target["x"] + (win["X"] - current["x"])
    ty = target["y"] + (win["Y"] - current["y"])
    wm = get_wm_class(win["WINDOW"])
    target_home = {"WINDOW": win["WINDOW"], "X": tx, "Y": ty,
                   "WIDTH": win["WIDTH"], "HEIGHT": win["HEIGHT"],
                   "SCREEN": all_screens.index(target)}
    save_state(win["WINDOW"], target_home, tx, ty, win["WIDTH"], win["HEIGHT"], wm)
    move_window(win["WIDTH"], win["HEIGHT"], win["WINDOW"],
                win["WIDTH"], win["HEIGHT"], win["X"], win["Y"], tx, ty)


def dispatch(action):
    if action in ["N", "S", "E", "W", "NE", "NW", "SE", "SW", "C"]:
        direction(action)
    elif action == "F":  fullscreen()
    elif action == "U":  restore()
    elif action == "TF": toggle_fullscreen()
    elif action == "TD": toggle_display()
    elif action == "CC": clear_cache()
    else: raise ValueError(f"Unknown action: {action!r}")
