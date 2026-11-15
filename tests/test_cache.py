import sqlite3
import tempfile
import unittest
from pathlib  import Path
from unittest import mock

from winjitsu import cache


HOME   = {"WINDOW": "7", "X": 10, "Y": 20, "WIDTH": 300, "HEIGHT": 200, "SCREEN": 0}
TARGET = (0, 0, 960, 1080)


def _cached(reached):
    return {**HOME, "WM_CLASS": "kitty", "_target": TARGET, "_reached": reached}


def _window(x, y, width, height):
    return {"WINDOW": 7, "X": x, "Y": y, "WIDTH": width, "HEIGHT": height, "SCREEN": 0}


class ResolveHomeTest(unittest.TestCase):
    def test_without_cache_the_window_is_the_home(self):
        window = _window(1, 2, 3, 4)
        self.assertIs(cache._resolve_home(window, None), window)

    def test_still_where_it_settled_keeps_the_home(self):
        home = cache._resolve_home(_window(0, 24, 960, 1056), _cached((0, 24, 960, 1056)))
        self.assertEqual((home["X"], home["Y"], home["WIDTH"], home["HEIGHT"]), (10, 20, 300, 200))

    def test_small_differences_still_count_as_the_same_place(self):
        home = cache._resolve_home(_window(1, 26, 959, 1056), _cached((0, 24, 960, 1056)))
        self.assertEqual(home["X"], 10)

    def test_moved_away_makes_the_current_geometry_the_home(self):
        window = _window(500, 400, 960, 1056)
        self.assertIs(cache._resolve_home(window, _cached((0, 24, 960, 1056))), window)

    def test_without_a_settled_geometry_compares_with_the_target(self):
        self.assertEqual(cache._resolve_home(_window(*TARGET), _cached(None))["X"], 10)


class DatabaseTest(unittest.TestCase):
    def setUp(self):
        temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(temp_dir.cleanup)
        self.db_path = Path(temp_dir.name) / "state.db"

        patcher = mock.patch.object(cache, "DB_PATH", self.db_path)
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_save_and_load_round_trip(self):
        cache.init_db()
        cache.save_state(7, HOME, TARGET, (0, 24, 960, 1056), "kitty")

        state = cache.load_state(7, "kitty")
        self.assertEqual((state["X"], state["Y"], state["WIDTH"], state["HEIGHT"]), (10, 20, 300, 200))
        self.assertEqual(state["_target"],  TARGET)
        self.assertEqual(state["_reached"], (0, 24, 960, 1056))
        self.assertIsNone(cache.load_state(7, "firefox"))

    def test_save_recreates_a_removed_database(self):
        cache.init_db()
        self.db_path.unlink()
        self.db_path.parent.rmdir()

        cache.save_state(7, HOME, TARGET, (0, 24, 960, 1056), "kitty")
        self.assertEqual(cache.load_state(7, "kitty")["_reached"], (0, 24, 960, 1056))

    def test_load_treats_a_broken_database_as_empty(self):
        self.db_path.write_bytes(b"not a database " * 100)
        self.assertIsNone(cache.load_state(7, "kitty"))

    def test_a_table_from_an_older_version_is_replaced(self):
        with sqlite3.connect(self.db_path) as connection:
            connection.execute(
                "CREATE TABLE windows (id TEXT PRIMARY KEY, window_id TEXT NOT NULL, x INTEGER NOT NULL,"
                " y INTEGER NOT NULL, width INTEGER NOT NULL, height INTEGER NOT NULL,"
                " screen INTEGER NOT NULL DEFAULT 0, wm_class TEXT NOT NULL, last_x INTEGER NOT NULL,"
                " last_y INTEGER NOT NULL, last_w INTEGER NOT NULL, last_h INTEGER NOT NULL,"
                " UNIQUE(window_id, wm_class))"
            )
            connection.execute("INSERT INTO windows VALUES ('id', '7', 10, 20, 300, 200, 0, 'kitty', 0, 0, 960, 1080)")

        cache.init_db()
        self.assertIsNone(cache.load_state(7, "kitty"))

        with sqlite3.connect(self.db_path) as connection:
            columns = {row[1] for row in connection.execute("PRAGMA table_info(windows)")}
        self.assertNotIn("id", columns)
        self.assertNotIn("screen", columns)

        cache.save_state(7, HOME, TARGET, (0, 24, 960, 1056), "kitty")
        self.assertEqual(cache.load_state(7, "kitty")["_reached"], (0, 24, 960, 1056))

if __name__ == "__main__":
    unittest.main()
