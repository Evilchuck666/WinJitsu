import os
import sys
import configparser
from dataclasses import dataclass
from pathlib     import Path


def _xdg_dir(variable, default_under_home):
    # XDG base directories: an unset or empty variable means the default.
    return Path(os.environ.get(variable) or Path.home() / default_under_home)


_CONFIG_PATH = _xdg_dir("XDG_CONFIG_HOME", ".config") / "winjitsu" / "config.ini"

# option: (section, default, minimum, maximum)
OPTIONS = {
    "steps":    ("animation", 25,  1, 1000),
    "padding":  ("display",   0,   0, 500),
    "delay_ms": ("daemon",    250, 0, 5000),
}


@dataclass
class _Config:
    steps:    int
    padding:  int
    delay_ms: int
    path:     Path


def validate(option, value):
    """The value as a whole number inside the option's range, or ValueError saying why not."""
    _section, _default, minimum, maximum = OPTIONS[option]

    try:
        number = int(str(value).strip())
    except ValueError:
        raise ValueError(f"{option} must be a whole number, got {value!r}") from None

    if not minimum <= number <= maximum:
        raise ValueError(f"{option} must be between {minimum} and {maximum}, got {number}")

    return number


def _load_config(path=None):
    config_path = path or _CONFIG_PATH
    ini_parser  = configparser.ConfigParser()

    try:
        ini_parser.read(config_path)
    except configparser.Error as error:
        print(f"Warning: could not read {config_path} ({error}), using the defaults.", file=sys.stderr)
        ini_parser = configparser.ConfigParser()

    # Each option falls back to its default on its own, so one bad value
    # doesn't discard the others.
    values = {}
    for option, (section, default, _minimum, _maximum) in OPTIONS.items():
        raw_value = ini_parser.get(section, option, fallback=None)

        if raw_value is None:
            values[option] = default
            continue

        try:
            values[option] = validate(option, raw_value)
        except ValueError as error:
            print(f"Warning: {error} in {config_path}, using the default ({default}).", file=sys.stderr)
            values[option] = default

    return _Config(path=config_path, **values)


def _write_config(config_path, active_config):
    if config_path.exists():
        overwrite_response = input(f"Config already exists: {config_path}\nOverwrite? [y/N] ").strip().lower()

        if overwrite_response not in ("y", "yes"):
            print("Aborted.")
            return

    config_path.parent.mkdir(parents=True, exist_ok=True)

    content = f"""\
# WinJitsu configuration

[animation]
# Steps in the window movement animation.
# Higher = smoother but slower. 1-1000, default: 25
steps = {active_config.steps}

[display]
# Gap in pixels around the window when using F (fullscreen).
# 0 = true fullscreen, 5 = small gap on all sides. 0-500, default: 0
padding = {active_config.padding}

[daemon]
# Delay in milliseconds. The first action runs at once; the ones that follow
# within this delay are collapsed and only the last one fires. 0-5000, default: 250
delay_ms = {active_config.delay_ms}
"""

    config_path.write_text(content)
    print(f"Config written to: {config_path}")


cfg = _load_config()
