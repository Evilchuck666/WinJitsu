import argparse
import io
import tempfile
import unittest
from contextlib import redirect_stderr
from pathlib    import Path
from unittest   import mock

from winjitsu import cli, config


class ValidateTest(unittest.TestCase):
    def test_accepts_values_in_range(self):
        self.assertEqual(config.validate("steps", " 40 "), 40)
        self.assertEqual(config.validate("delay_ms", 0), 0)

    def test_rejects_out_of_range_values(self):
        for option, value in (("steps", 0), ("padding", -5), ("delay_ms", 10000)):
            with self.assertRaisesRegex(ValueError, f"^{option} must be between"):
                config.validate(option, value)

    def test_rejects_non_numbers(self):
        with self.assertRaisesRegex(ValueError, "must be a whole number"):
            config.validate("padding", "wide")

    def test_command_line_flags_use_the_same_ranges(self):
        with self.assertRaisesRegex(argparse.ArgumentTypeError, "steps must be between 1 and 1000"):
            cli._option_type("steps")("0")


class LoadConfigTest(unittest.TestCase):
    def _load(self, content):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "config.ini"
            if content is not None:
                path.write_text(content)

            stderr = io.StringIO()
            with redirect_stderr(stderr):
                loaded = config._load_config(path)

        return loaded, stderr.getvalue()

    def test_missing_file_gives_the_defaults(self):
        loaded, warnings = self._load(None)
        self.assertEqual((loaded.steps, loaded.padding, loaded.delay_ms), (25, 0, 250))
        self.assertEqual(warnings, "")

    def test_one_bad_value_only_resets_that_option(self):
        loaded, warnings = self._load("[animation]\nsteps = lots\n[display]\npadding = 8\n[daemon]\ndelay_ms = 99999\n")

        self.assertEqual((loaded.steps, loaded.padding, loaded.delay_ms), (25, 8, 250))
        self.assertIn("steps must be a whole number", warnings)
        self.assertIn("delay_ms must be between 0 and 5000", warnings)

    def test_unreadable_file_gives_the_defaults_with_a_warning(self):
        loaded, warnings = self._load("steps = 10\n")  # no section header

        self.assertEqual(loaded.steps, 25)
        self.assertIn("could not read", warnings)


class XdgDirTest(unittest.TestCase):
    def test_empty_variable_means_the_default(self):
        with mock.patch.dict("os.environ", {"XDG_CACHE_HOME": ""}):
            self.assertEqual(config._xdg_dir("XDG_CACHE_HOME", ".cache"), Path.home() / ".cache")

    def test_set_variable_is_used(self):
        with mock.patch.dict("os.environ", {"XDG_CACHE_HOME": "/srv/cache"}):
            self.assertEqual(config._xdg_dir("XDG_CACHE_HOME", ".cache"), Path("/srv/cache"))


if __name__ == "__main__":
    unittest.main()
