import sqlite3
import tempfile
import unittest
from pathlib  import Path
from unittest import mock

from winjitsu import cache


MAXIMIZED = ["_NET_WM_STATE_MAXIMIZED_VERT", "_NET_WM_STATE_MAXIMIZED_HORZ"]


def _push(window_id, wm_class, step, states=()):
    # An action whose geometries all derive from `step`, to tell entries apart.
    cache.push_entry(window_id, wm_class, (step, 0, 300, 200), list(states), (step, 1, 960, 1080), (step, 2, 960, 1080))


class HistoryTest(unittest.TestCase):
    def setUp(self):
        temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(temp_dir.cleanup)
        self.db_path = Path(temp_dir.name) / "state.db"

        patcher = mock.patch.object(cache, "DB_PATH", self.db_path)
        patcher.start()
        self.addCleanup(patcher.stop)

        cache.init_db()

    def test_last_in_first_out(self):
        for step in (1, 2, 3):
            _push(7, "kitty", step)

        self.assertEqual(cache.top_entry(7, "kitty")["before"], (3, 0, 300, 200))
        self.assertEqual([cache.pop_entry(7, "kitty")["before"][0] for _ in range(3)], [3, 2, 1])
        self.assertIsNone(cache.pop_entry(7, "kitty"))
        self.assertIsNone(cache.top_entry(7, "kitty"))

    def test_an_entry_keeps_every_field(self):
        _push(7, "kitty", 5, states=MAXIMIZED)

        entry = cache.top_entry(7, "kitty")
        self.assertEqual(entry["before"],  (5, 0, 300, 200))
        self.assertEqual(entry["states"],  MAXIMIZED)
        self.assertEqual(entry["target"],  (5, 1, 960, 1080))
        self.assertEqual(entry["reached"], (5, 2, 960, 1080))

        _push(7, "kitty", 6)
        self.assertEqual(cache.top_entry(7, "kitty")["states"], [])

    def test_each_window_has_its_own_history(self):
        _push(7, "kitty", 1)
        _push(7, "firefox", 2)  # a reused window id with another class is another window
        _push(8, "kitty", 3)

        self.assertEqual(cache.pop_entry(7, "kitty")["before"][0], 1)
        self.assertEqual(cache.top_entry(7, "firefox")["before"][0], 2)
        self.assertEqual(cache.top_entry(8, "kitty")["before"][0], 3)
        self.assertIsNone(cache.top_entry(7, None))

    def test_clear_cache_empties_every_history(self):
        _push(7, "kitty", 1)
        _push(8, "kitty", 2)

        cache.clear_cache()
        self.assertIsNone(cache.top_entry(7, "kitty"))
        self.assertIsNone(cache.top_entry(8, "kitty"))

    def test_push_recreates_a_removed_database(self):
        self.db_path.unlink()
        self.db_path.parent.rmdir()

        _push(7, "kitty", 1)
        self.assertEqual(cache.top_entry(7, "kitty")["before"][0], 1)

    def test_a_broken_database_reads_as_empty_and_fails_writes(self):
        self.db_path.write_bytes(b"not a database " * 100)

        self.assertIsNone(cache.top_entry(7, "kitty"))
        with self.assertRaises(cache.CACHE_ERRORS):
            _push(7, "kitty", 1)
        with self.assertRaises(cache.CACHE_ERRORS):
            cache.pop_entry(7, "kitty")

    def test_tables_of_older_versions_are_replaced(self):
        self.db_path.unlink()
        with sqlite3.connect(self.db_path) as connection:
            connection.execute("CREATE TABLE windows (window_id TEXT, wm_class TEXT, x INTEGER, y INTEGER)")
            connection.execute("INSERT INTO windows VALUES ('7', 'kitty', 10, 20)")
            connection.execute("PRAGMA user_version = 2")

        cache.init_db()

        with sqlite3.connect(self.db_path) as connection:
            tables  = {row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
            version = connection.execute("PRAGMA user_version").fetchone()[0]
        self.assertEqual((tables, version), ({"history"}, cache._SCHEMA_VERSION))

        _push(7, "kitty", 1)
        self.assertEqual(cache.top_entry(7, "kitty")["before"][0], 1)


if __name__ == "__main__":
    unittest.main()
