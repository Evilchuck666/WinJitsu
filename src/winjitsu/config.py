import os
import configparser
from dataclasses import dataclass
from pathlib import Path


_CONFIG_PATH = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config")) / "winjitsu" / "config.ini"

_CONFIG_TEMPLATE = """\
# WinJitsu configuration

[animation]
# Steps in the window movement animation.
# Higher = smoother but slower. Default: 25
# steps = 25

[display]
# Gap in pixels around the window when using F (fullscreen).
# 0 = true fullscreen, 5 = small gap on all sides. Default: 0
# padding = 0

[daemon]
# Debounce delay in milliseconds. Rapid actions within this window are
# collapsed into one — only the last one fires. Default: 250
# debounce_ms = 250
"""


@dataclass
class _Config:
    steps: int
    padding: int
    debounce_ms: int
    path: Path


def _load_config(path=None):
    cfg = configparser.ConfigParser()
    cfg.read_dict({
        "animation": {"steps": "25"},
        "display":   {"padding": "0"},
        "daemon":    {"debounce_ms": "250"},
    })
    p = path or _CONFIG_PATH
    cfg.read(p)
    return _Config(
        steps=cfg.getint("animation", "steps"),
        padding=cfg.getint("display", "padding"),
        debounce_ms=cfg.getint("daemon", "debounce_ms"),
        path=p,
    )


def _write_config(path):
    if path.exists():
        answer = input(f"Config already exists: {path}\nOverwrite? [y/N] ").strip().lower()
        if answer not in ("y", "yes"):
            print("Aborted.")
            return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(_CONFIG_TEMPLATE)
    print(f"Config written to: {path}")


_CFG = _load_config()
