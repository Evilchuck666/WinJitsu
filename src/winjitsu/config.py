import os
import configparser
from dataclasses import dataclass
from pathlib     import Path


_CONFIG_PATH = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config")) / "winjitsu" / "config.ini"



@dataclass
class _Config:
    steps:    int
    padding:  int
    delay_ms: int
    path:     Path


def _load_config(path=None):
    ini_parser = configparser.ConfigParser()

    ini_parser.read_dict({
        "animation": {"steps": "25"},
        "display":   {"padding": "0"},
        "daemon":    {"delay_ms": "250"},
    })

    config_path = path or _CONFIG_PATH
    ini_parser.read(config_path)

    try:
        return _Config(
            steps=ini_parser.getint("animation", "steps"),
            padding=ini_parser.getint("display", "padding"),
            delay_ms=ini_parser.getint("daemon", "delay_ms"),
            path=config_path,
        )
    except (ValueError, configparser.Error) as e:
        import sys
        print(f"Warning: invalid config value ({e}), using defaults.", file=sys.stderr)
        return _Config(steps=25, padding=0, delay_ms=250, path=config_path)


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
# Higher = smoother but slower. Default: 25
steps = {active_config.steps}

[display]
# Gap in pixels around the window when using F (fullscreen).
# 0 = true fullscreen, 5 = small gap on all sides. Default: 0
padding = {active_config.padding}

[daemon]
# Delay in milliseconds. Rapid actions within this window are
# collapsed into one — only the last one fires. Default: 250
delay_ms = {active_config.delay_ms}
"""

    config_path.write_text(content)
    print(f"Config written to: {config_path}")


cfg = _load_config()
