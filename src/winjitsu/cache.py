import json
import shutil
from pathlib import Path

from .window import get_wm_class


CACHE_DIR = Path.home() / ".cache" / "winjitsu"


def load_state(window_id, wm_class):
    cache_file_path = CACHE_DIR / f"{window_id}.json"
    if not cache_file_path.exists():
        return None
    try:
        with open(cache_file_path) as f:
            cached_state = json.load(f)
    except (json.JSONDecodeError, ValueError):
        return None
    # X11 window IDs are recycled across sessions — reject cache if the app changed
    if cached_state.get("WM_CLASS") != wm_class:
        return None
    return cached_state


def save_state(window_id, home_state, target_x, target_y, target_width, target_height, wm_class):
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    with open(CACHE_DIR / f"{window_id}.json", "w") as f:
        json.dump({
            "WINDOW": home_state["WINDOW"],
            "X": home_state["X"], "Y": home_state["Y"],
            "WIDTH": home_state["WIDTH"], "HEIGHT": home_state["HEIGHT"],
            "SCREEN": home_state.get("SCREEN", 0),
            "WM_CLASS": wm_class,
            "_last_X": target_x, "_last_Y": target_y,
            "_last_W": target_width, "_last_H": target_height,
        }, f)


def _resolve_home(window, cached_state):
    # If the window is still at the last position we animated it to, the original
    # home hasn't changed — reuse it. Otherwise the window moved elsewhere and its
    # current position becomes the new home.
    if cached_state is None:
        return window
    last_target_geometry = (
        cached_state.get("_last_X"), cached_state.get("_last_Y"),
        cached_state.get("_last_W"), cached_state.get("_last_H")
    )
    if None in last_target_geometry:
        return window
    current_geometry = (window["X"], window["Y"],
                        window["WIDTH"], window["HEIGHT"])
    if current_geometry == last_target_geometry:
        return {k: cached_state[k] for k in ("WINDOW", "X", "Y", "WIDTH", "HEIGHT", "SCREEN")}
    return window


def _update_state(window, target_x, target_y, target_width, target_height):
    wm_class = get_wm_class(window["WINDOW"])
    cached_state = load_state(window["WINDOW"], wm_class)
    home_state = _resolve_home(window, cached_state)
    save_state(window["WINDOW"], home_state, target_x, target_y, target_width, target_height, wm_class)


def clear_cache():
    if CACHE_DIR.exists():
        shutil.rmtree(CACHE_DIR)
