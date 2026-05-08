import sqlite3
from pathlib import Path
from uuid import uuid4

from .window import get_wm_class


DB_PATH = Path.home() / ".cache" / "winjitsu" / "state.db"

_CREATE_TABLE = """
CREATE TABLE IF NOT EXISTS windows (
    id         TEXT    PRIMARY KEY,
    window_id  TEXT    NOT NULL,
    x          INTEGER NOT NULL,
    y          INTEGER NOT NULL,
    width      INTEGER NOT NULL,
    height     INTEGER NOT NULL,
    screen     INTEGER NOT NULL DEFAULT 0,
    wm_class   TEXT    NOT NULL,
    last_x     INTEGER NOT NULL,
    last_y     INTEGER NOT NULL,
    last_w     INTEGER NOT NULL,
    last_h     INTEGER NOT NULL,
    UNIQUE(window_id, wm_class)
)
"""


def init_db():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute(_CREATE_TABLE)


def load_state(window_id, wm_class):
    if not DB_PATH.exists():
        return None
    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            "SELECT * FROM windows WHERE window_id = ? AND wm_class = ?",
            (window_id, wm_class),
        ).fetchone()
    if row is None:
        return None
    return {
        "WINDOW":   row["window_id"],
        "X":        row["x"],      "Y":      row["y"],
        "WIDTH":    row["width"],  "HEIGHT": row["height"],
        "SCREEN":   row["screen"],
        "WM_CLASS": row["wm_class"],
        "_last_X":  row["last_x"], "_last_Y": row["last_y"],
        "_last_W":  row["last_w"], "_last_H": row["last_h"],
    }


def save_state(window_id, home_state, target_x, target_y, target_width, target_height, wm_class):
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute(
            """
            INSERT INTO windows
                (id, window_id, x, y, width, height, screen, wm_class,
                 last_x, last_y, last_w, last_h)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(window_id, wm_class) DO UPDATE SET
                x=excluded.x,         y=excluded.y,
                width=excluded.width, height=excluded.height,
                screen=excluded.screen,
                last_x=excluded.last_x, last_y=excluded.last_y,
                last_w=excluded.last_w, last_h=excluded.last_h
            """,
            (
                str(uuid4()), window_id,
                home_state["X"], home_state["Y"],
                home_state["WIDTH"], home_state["HEIGHT"],
                home_state.get("SCREEN", 0),
                wm_class,
                target_x, target_y, target_width, target_height,
            ),
        )


def _resolve_home(window, cached_state):
    # If the window is still at the last position we animated it to, the original
    # home hasn't changed — reuse it. Otherwise, the window moved elsewhere and its
    # current position becomes the new home.
    if cached_state is None:
        return window
    last_target_geometry = (
        cached_state.get("_last_X"), cached_state.get("_last_Y"),
        cached_state.get("_last_W"), cached_state.get("_last_H")
    )
    if None in last_target_geometry:
        return window
    current_geometry = (window["X"], window["Y"], window["WIDTH"], window["HEIGHT"])
    if current_geometry == last_target_geometry:
        return {k: cached_state[k] for k in ("WINDOW", "X", "Y", "WIDTH", "HEIGHT", "SCREEN")}
    return window


def _update_state(window, target_x, target_y, target_width, target_height):
    wm_class = get_wm_class(window["WINDOW"])

    if wm_class is None:
        return
    
    cached_state = load_state(window["WINDOW"], wm_class)
    home_state = _resolve_home(window, cached_state)
    save_state(window["WINDOW"], home_state, target_x, target_y, target_width, target_height, wm_class)


def clear_cache():
    if not DB_PATH.exists():
        return
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute("DELETE FROM windows")
