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
    if cached_state.get("WM_CLASS") != wm_class:
        return None
    return cached_state


def save_state(window_id, home, tx, ty, tw, th, wm_class):
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    with open(CACHE_DIR / f"{window_id}.json", "w") as f:
        json.dump({
            "WINDOW": home["WINDOW"],
            "X": home["X"], "Y": home["Y"],
            "WIDTH": home["WIDTH"], "HEIGHT": home["HEIGHT"],
            "SCREEN": home.get("SCREEN", 0),
            "WM_CLASS": wm_class,
            "_last_X": tx, "_last_Y": ty,
            "_last_W": tw, "_last_H": th,
        }, f)


def _resolve_home(win, existing):
    if existing is None:
        return win
    last = (existing.get("_last_X"), existing.get("_last_Y"),
            existing.get("_last_W"), existing.get("_last_H"))
    if None in last:
        return win
    if (win["X"] == last[0] and win["Y"] == last[1] and
            win["WIDTH"] == last[2] and win["HEIGHT"] == last[3]):
        return {k: existing[k] for k in ("WINDOW", "X", "Y", "WIDTH", "HEIGHT", "SCREEN")}
    return win


def _update_state(win, tx, ty, tw, th):
    wm = get_wm_class(win["WINDOW"])
    existing = load_state(win["WINDOW"], wm)
    home = _resolve_home(win, existing)
    save_state(win["WINDOW"], home, tx, ty, tw, th, wm)


def clear_cache():
    if CACHE_DIR.exists():
        shutil.rmtree(CACHE_DIR)
