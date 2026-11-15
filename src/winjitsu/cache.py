import sqlite3
from .config import _xdg_dir


DB_PATH = _xdg_dir("XDG_CACHE_HOME", ".cache") / "winjitsu" / "state.db"

# The undo history: one row per WinJitsu action on a window, seq orders them.
# before_*: the frame geometry the window had before the action (for a
# maximized window, the one it had before being maximized), and before_states
# the window manager states WinJitsu removed to move it. target_*: what was
# asked for. reached_*: where the window settled, which is what later reads of
# the window return.
_CREATE_TABLE = """
CREATE TABLE IF NOT EXISTS history (
    window_id      TEXT    NOT NULL,
    wm_class       TEXT    NOT NULL,
    seq            INTEGER NOT NULL,
    before_x       INTEGER NOT NULL,
    before_y       INTEGER NOT NULL,
    before_w       INTEGER NOT NULL,
    before_h       INTEGER NOT NULL,
    before_states  TEXT    NOT NULL DEFAULT '',
    target_x       INTEGER NOT NULL,
    target_y       INTEGER NOT NULL,
    target_w       INTEGER NOT NULL,
    target_h       INTEGER NOT NULL,
    reached_x      INTEGER NOT NULL,
    reached_y      INTEGER NOT NULL,
    reached_w      INTEGER NOT NULL,
    reached_h      INTEGER NOT NULL,
    PRIMARY KEY (window_id, wm_class, seq)
)
"""

# Stored in PRAGMA user_version; bump it whenever the table changes. The cache
# is emptied on every daemon start anyway, so outdated tables are dropped.
_SCHEMA_VERSION = 3

# What a broken or vanished cache raises. The cache is an extra: callers turn
# these into warnings instead of failing the action.
CACHE_ERRORS = (sqlite3.Error, OSError)


def _connect():
    # Creates the database, its directory and the table when they are missing,
    # e.g. ~/.cache was cleared while the daemon was running.
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(DB_PATH)
    connection.row_factory = sqlite3.Row

    if connection.execute("PRAGMA user_version").fetchone()[0] != _SCHEMA_VERSION:
        connection.execute("DROP TABLE IF EXISTS windows")  # the home positions of versions 1 and 2
        connection.execute("DROP TABLE IF EXISTS history")
        connection.execute(f"PRAGMA user_version = {_SCHEMA_VERSION}")

    connection.execute(_CREATE_TABLE)
    return connection


def init_db():
    with _connect() as connection:
        connection.commit()


def _whole(geometry):
    return tuple(int(round(value)) for value in geometry)


def _entry(row):
    return {
        "seq":     row["seq"],
        "before":  (row["before_x"],  row["before_y"],  row["before_w"],  row["before_h"]),
        "states":  [name for name in row["before_states"].split(",") if name],
        "target":  (row["target_x"],  row["target_y"],  row["target_w"],  row["target_h"]),
        "reached": (row["reached_x"], row["reached_y"], row["reached_w"], row["reached_h"]),
    }


_SELECT_TOP = "SELECT * FROM history WHERE window_id = ? AND wm_class = ? ORDER BY seq DESC LIMIT 1"


def push_entry(window_id, wm_class, before, states, target, reached):
    """Put an action on top of the window's history. Raises one of CACHE_ERRORS."""
    key = (str(window_id), wm_class)

    with _connect() as connection:
        connection.execute(
            """
            INSERT INTO history VALUES (
                ?, ?, (SELECT COALESCE(MAX(seq), 0) + 1 FROM history WHERE window_id = ? AND wm_class = ?),
                ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?
            )
            """,
            (*key, *key, *_whole(before), ",".join(states), *_whole(target), *_whole(reached)),
        )


def top_entry(window_id, wm_class):
    """The last action on the window, or None, also when the history can't be read."""
    if wm_class is None or not DB_PATH.exists():
        return None

    try:
        with _connect() as connection:
            row = connection.execute(_SELECT_TOP, (str(window_id), wm_class)).fetchone()
    except CACHE_ERRORS:
        return None  # treated like a window without history

    return _entry(row) if row is not None else None


def pop_entry(window_id, wm_class):
    """Take the last action off the window's history and return it (None if empty). Raises one of CACHE_ERRORS."""
    key = (str(window_id), wm_class)

    with _connect() as connection:
        row = connection.execute(_SELECT_TOP, key).fetchone()
        if row is None:
            return None

        connection.execute("DELETE FROM history WHERE window_id = ? AND wm_class = ? AND seq = ?", (*key, row["seq"]))

    return _entry(row)


def clear_cache():
    if not DB_PATH.exists():
        return

    with _connect() as connection:
        connection.execute("DELETE FROM history")
