from .config import _CFG
from .screen import get_screens, get_screen_for_window
from .window import get_window_position, get_wm_class, move_window
from .cache import load_state, save_state, clear_cache, _update_state


VALID_ACTIONS = ["N", "S", "E", "W", "NE", "NW", "SE", "SW", "C", "F", "U", "TF", "TD", "CC"]


def fullscreen(win=None, screen_w=None, screen_h=None, base_x=None, base_y=None):
    win = win or get_window_position()
    if screen_w is None:
        screen_w, screen_h, base_x, base_y = get_screen_for_window(win)
    tx, ty = base_x + _CFG.padding, base_y + _CFG.padding
    tw, th = screen_w - 2 * _CFG.padding, screen_h - 2 * _CFG.padding
    _update_state(win, tx, ty, tw, th)
    move_window(tw, th, win["WINDOW"], win["WIDTH"], win["HEIGHT"], win["X"], win["Y"], tx, ty)


def restore(win=None):
    win = win or get_window_position()
    saved = load_state(win["WINDOW"], get_wm_class(win["WINDOW"]))
    if saved:
        move_window(
            saved["WIDTH"], saved["HEIGHT"],
            win["WINDOW"],
            win["WIDTH"],  win["HEIGHT"],
            win["X"],      win["Y"],
            saved["X"],    saved["Y"],
        )


def toggle_fullscreen(win=None):
    win = win or get_window_position()
    screen_w, screen_h, base_x, base_y = get_screen_for_window(win)
    if win["WIDTH"] == screen_w - 2 * _CFG.padding and win["HEIGHT"] == screen_h - 2 * _CFG.padding:
        restore(win)
    else:
        fullscreen(win, screen_w, screen_h, base_x, base_y)


def direction(direction_code):
    win = get_window_position()
    screen_w, screen_h, base_x, base_y = get_screen_for_window(win)
    half_w = screen_w / 2
    half_h = screen_h / 2

    targets = {
        "N":  (screen_w, half_h,        base_x,          base_y),
        "S":  (screen_w, half_h,        base_x,          base_y + half_h),
        "E":  (half_w,   screen_h,      base_x + half_w, base_y),
        "W":  (half_w,   screen_h,      base_x,          base_y),
        "NE": (half_w,   half_h,        base_x + half_w, base_y),
        "NW": (half_w,   half_h,        base_x,          base_y),
        "SE": (half_w,   half_h,        base_x + half_w, base_y + half_h),
        "SW": (half_w,   half_h,        base_x,          base_y + half_h),
        "C":  (win["WIDTH"], win["HEIGHT"],
               (screen_w - win["WIDTH"])  / 2 + base_x,
               (screen_h - win["HEIGHT"]) / 2 + base_y),
    }
    tw, th, tx, ty = targets[direction_code]
    _update_state(win, tx, ty, tw, th)
    move_window(tw, th, win["WINDOW"], win["WIDTH"], win["HEIGHT"], win["X"], win["Y"], tx, ty)


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
