# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

WinJitsu is an animated window snapping tool for Linux X11. A background daemon receives actions (`N`, `TF`, `TD`, …) from the `winjitsu` CLI over a Unix socket, works out the target geometry for the active window and glides it there with an eased (smoothstep) animation driven by `xdotool`. Monitors are detected through the RandR extension with `python-xlib`, and each window's "home position" is kept in SQLite so it can be restored.

## Commands

```bash
# Install locally for development
pip install -e .

# Start the daemon (required: actions are only sent to it), then run actions
winjitsu --daemon
winjitsu <ACTION>
winjitsu --reload-daemon      # restart after code or config changes

# Config
winjitsu --see-config
winjitsu --write-config

# Build wheel and sdist
python -m build
```

No test suite or linter is configured. CI only builds, runs `twine check` and smoke-tests the CLI without an X server (`--help`, `--see-config`, module imports).

**Dependencies:** `python-xlib` (Python, declared in `pyproject.toml`) and `xdotool` (system binary, called through `subprocess`). An X11 session with RandR is needed at runtime.

## Architecture

All code lives in `src/winjitsu/`. `__init__.py` reads `__version__` from the installed metadata and re-exports `cli.main`.

**Data flow:**
```
winjitsu ACTION → cli.main → daemon.send_command ──Unix socket──▶ _CommandHandler
  → _schedule_action (debounce) → _run_action → actions.dispatch
  → window.get_window_position + screen.get_screen_for_window
  → cache._update_state (save home + target) → window.move_window
```

| Module       | Role                                                                                                                                  |
|--------------|---------------------------------------------------------------------------------------------------------------------------------------|
| `cli.py`     | argparse entry point. Pre-parses `--read-config` so it replaces the module-level config before anything uses it; `--steps`, `--padding`, `--delay-ms` then override it. Handles `--daemon`, `--reload-daemon`, `--write-config`, `--see-config`, or sends the action to the daemon. |
| `daemon.py`  | Forks and detaches (`setsid`, stdio to `/dev/null`), writes the PID file and serves a `ThreadingUnixStreamServer` (socket mode `0600`). Each action restarts a `threading.Timer` of `delay_ms`; only the last action of a burst runs and superseded callers get `OK`. Clears the window cache on start. |
| `actions.py` | `VALID_ACTIONS` and `dispatch()`. `direction()` computes halves, quarters and `C` (center, keeps size) relative to the window's monitor; `fullscreen()` applies `padding`; `restore()` returns to the cached home; `toggle_fullscreen()` compares the current geometry with the fullscreen one; `toggle_display()` cycles to the next monitor keeping size and relative offset. |
| `window.py`  | `xdotool` wrappers: active window geometry (`getwindowgeometry --shell`), WM class, and `move_window()`, which clamps to the X screen and runs `cfg.steps` resize+move steps eased with smoothstep. |
| `screen.py`  | One shared `Xlib.display.Display` (lazily created under a lock). `get_screens()` returns `(primary, others)` from RandR CRTCs; `find_screen_for_window()` picks the monitor containing the window center, or the nearest one. |
| `cache.py`   | SQLite store keyed by `(window_id, wm_class)`: home geometry plus the last target WinJitsu moved the window to. `_resolve_home()` keeps the old home only while the window is still exactly at that last target; otherwise its current geometry becomes the new home. |
| `config.py`  | `_Config` dataclass loaded from INI at import time into the module-level `cfg` (defaults: `steps=25`, `padding=0`, `delay_ms=250`); invalid values fall back to defaults with a warning. |

**Runtime files:**
- Config: `$XDG_CONFIG_HOME/winjitsu/config.ini` (default `~/.config/…`), sections `[animation] steps`, `[display] padding`, `[daemon] delay_ms`.
- Socket and PID: `$XDG_RUNTIME_DIR/winjitsu/winjitsu.sock` and `winjitsu.pid`.
- Window state: `~/.cache/winjitsu/state.db`.

**Gotchas:**
- Use `config_timestamp`, not `timestamp`, for RandR output/CRTC queries; the latter causes `BadMatch` on some drivers (commented in `screen.py`).
- The daemon reads `cfg` once at startup, so config or code changes need `winjitsu --reload-daemon`.
- Replies starting with `WARN:` or `ERROR:` are printed by the client. `send_command()` returns `True` on success, `False` when the daemon replied `ERROR:` (exit 1) and `None` when the daemon cannot be reached (exit 1 with the "daemon is not running" hint).

## Actions Reference

`N S E W` — halves · `NE NW SE SW` — quarters · `C` — center, keeping size
`F` — fullscreen on the current monitor, minus `padding` (default 0)
`U` — restore the home position · `TF` — toggle fullscreen / home position
`TD` — move to the next monitor · `CC` — clear the window state cache

## Release

Versions live in `pyproject.toml` (`version`) and `arch/PKGBUILD` (`pkgver`) and must match. `.github/workflows/release.yml` builds and smoke-tests on every run; on pushes and pull requests it only runs when the repository variable `WINJITSU_CI` is `true`. Running it manually with a version publishes the GitHub release, uploads to PyPI with Trusted Publishing (environment `pypi`) and copies `arch/PKGBUILD` to the `winjitsu` AUR package with `pkgrel=1` and a regenerated `.SRCINFO` (secret `AUR_SSH_PRIVATE_KEY`). `arch/PKGBUILD` is the source of truth for the AUR package:

```bash
gh workflow run release.yml -R Evilchuck666/WinJitsu -f version=X.Y.Z --ref main
```
