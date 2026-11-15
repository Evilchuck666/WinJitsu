import sqlite3
from .config import _xdg_dir
from .window import get_wm_class, geometry_of, geometry_matches


DB_PATH = _xdg_dir("XDG_CACHE_HOME", ".cache") / "winjitsu" / "state.db"

# x, y, width, height: the home geometry. last_*: the target WinJitsu asked
# for. reached_*: the frame geometry the window actually settled at, which is
# what later reads of the window return.
_CREATE_TABLE = """
CREATE TABLE IF NOT EXISTS windows (
    window_id  TEXT    NOT NULL,
    wm_class   TEXT    NOT NULL,
    x          INTEGER NOT NULL,
    y          INTEGER NOT NULL,
    width      INTEGER NOT NULL,
    height     INTEGER NOT NULL,
    last_x     INTEGER NOT NULL,
    last_y     INTEGER NOT NULL,
    last_w     INTEGER NOT NULL,
    last_h     INTEGER NOT NULL,
    reached_x  INTEGER,
    reached_y  INTEGER,
    reached_w  INTEGER,
    reached_h  INTEGER,
    PRIMARY KEY (window_id, wm_class)
)
"""

# Stored in PRAGMA user_version; bump it whenever the table changes. The cache
# is emptied on every daemon start anyway, so an outdated table is dropped.
_SCHEMA_VERSION = 2

# What a broken or vanished cache raises. The cache is an extra: callers turn
# these into warnings instead of failing the action.
CACHE_ERRORS = (sqlite3.Error, OSError)


def _connect():
    # Creates the database, its directory and the table when they are missing,
    # e.g. ~/.cache was cleared while the daemon was running.
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(DB_PATH)

    if connection.execute("PRAGMA user_version").fetchone()[0] != _SCHEMA_VERSION:
        connection.execute("DROP TABLE IF EXISTS windows")
        connection.execute(f"PRAGMA user_version = {_SCHEMA_VERSION}")

    connection.execute(_CREATE_TABLE)
    return connection


def init_db():
    with _connect() as connection:
        connection.commit()


def load_state(window_id, wm_class):
    if wm_class is None:
        return None

    window_id = str(window_id)

    if not DB_PATH.exists():
        return None

    try:
        with _connect() as connection:
            connection.row_factory = sqlite3.Row
            row = connection.execute(
                "SELECT * FROM windows WHERE window_id = ? AND wm_class = ?",
                (window_id, wm_class),
            ).fetchone()
    except CACHE_ERRORS:
        return None  # treated like a window WinJitsu doesn't know yet

    if row is None:
        return None

    reached = (row["reached_x"], row["reached_y"], row["reached_w"], row["reached_h"])

    return {
        "WINDOW":   row["window_id"],
        "X":        row["x"],
        "Y":        row["y"],
        "WIDTH":    row["width"],
        "HEIGHT":   row["height"],
        "_target":  (row["last_x"], row["last_y"], row["last_w"], row["last_h"]),
        "_reached": None if None in reached else reached,
    }


def save_state(window_id, home_state, target, reached, wm_class):
    if wm_class is None:
        return

    window_id = str(window_id)
    reached   = reached if reached is not None else (None, None, None, None)

    with _connect() as connection:
        connection.execute(
            """
            INSERT INTO windows
                (window_id, wm_class, x, y, width, height,
                 last_x, last_y, last_w, last_h,
                 reached_x, reached_y, reached_w, reached_h)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(window_id, wm_class) DO UPDATE SET
                x=excluded.x,         y=excluded.y,
                width=excluded.width, height=excluded.height,
                last_x=excluded.last_x, last_y=excluded.last_y,
                last_w=excluded.last_w, last_h=excluded.last_h,
                reached_x=excluded.reached_x, reached_y=excluded.reached_y,
                reached_w=excluded.reached_w, reached_h=excluded.reached_h
            """,
            (
                window_id,
                wm_class,
                home_state["X"],     home_state["Y"],
                home_state["WIDTH"], home_state["HEIGHT"],
                *target,
                *reached,
            )
        )


def _resolve_home(window, cached_state):
    # If the window is still where WinJitsu left it, the original home hasn't
    # changed — reuse it. Otherwise, the window moved elsewhere, and its
    # current position becomes the new home.
    if cached_state is None:
        return window

    left_at = cached_state["_reached"] or cached_state["_target"]

    if geometry_matches(geometry_of(window), left_at):
        return {k: cached_state[k] for k in ("WINDOW", "X", "Y", "WIDTH", "HEIGHT")}

    return window


def _update_state(window, target, reached):
    # window: geometry before the move. target: what was asked for. reached:
    # where the window settled, or None if it could not be moved.
    if reached is None:
        return

    target   = tuple(int(round(value)) for value in target)
    wm_class = get_wm_class(window["WINDOW"])

    if wm_class is None:
        return

    cached_state = load_state(window["WINDOW"], wm_class)
    home_state   = _resolve_home(window, cached_state)

    save_state(window["WINDOW"], home_state, target, reached, wm_class)


def clear_cache():
    if not DB_PATH.exists():
        return

    with _connect() as connection:
        connection.execute("DELETE FROM windows")
