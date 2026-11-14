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

# Arch: replace the installed winjitsu package with a pacman "nightly" built
# from this checkout (uncommitted changes included), then reload the daemon
./install-nightly.sh            # --no-install only builds it into PKGs/

# Unit tests (stdlib unittest, no X server needed)
make test        # PYTHONPATH=src python -m unittest discover -s tests -v
```

`tests/fakes.py` stands in for `xdotool` and an ICCCM window manager (frame decorations, resize increments), so the action tests run whole scenarios such as `W`, `U`, `TF`. No linter is configured. CI builds, runs `twine check`, smoke-tests the CLI without an X server (`--help`, `--see-config`, module imports) and runs the unit tests against the installed wheel.

**Dependencies:** `python-xlib` (Python, declared in `pyproject.toml`) and `xdotool` (system binary, called through `subprocess`). An X11 session with RandR is needed at runtime.

## Architecture

All code lives in `src/winjitsu/`. `__init__.py` reads `__version__` from the installed metadata and re-exports `cli.main`.

**Data flow:**
```
winjitsu ACTION → cli.main → daemon.send_command ──Unix socket──▶ _CommandHandler
  → _schedule_action (debounce) → action queue → _action_worker → actions.dispatch
  → window.get_window_position + screen.get_screen_for_window
  → window.move_window (returns the settled geometry) → cache._update_state (save home, target, settled)
```

| Module       | Role                                                                                                                                  |
|--------------|---------------------------------------------------------------------------------------------------------------------------------------|
| `cli.py`     | argparse entry point. Pre-parses `--read-config` so it replaces the module-level config before anything uses it; `--steps`, `--padding`, `--delay-ms` then override it. Handles `--daemon`, `--reload-daemon`, `--write-config`, `--see-config`, or sends the action to the daemon. |
| `daemon.py`  | Forks and detaches (`setsid`, stdio to `/dev/null`), writes the PID file and serves a `ThreadingUnixStreamServer` (socket mode `0600`). Each action restarts a `threading.Timer` of `delay_ms`; only the last action of a burst is queued and superseded callers get `OK`. A single worker thread runs queued actions one at a time, in order, so animations never overlap and the X connection is used from one thread. Clears the window cache on start. |
| `actions.py` | `VALID_ACTIONS` and `dispatch()`. `_grid_targets()` gives halves, quarters and `F` (minus `padding`) of a monitor's usable area in whole pixels; `direction()` uses them, plus `C` (center, keeps size); `restore()` returns to the cached home; `_is_at()` tells whether a window is at a target or still where a cached move to it left it, which `toggle_fullscreen()` and `toggle_display()` use. `toggle_display()` cycles to the next monitor: a window at a grid position takes the same position there, any other keeps size and offset, shrunk to fit. Every move except `U` goes through `_move_and_remember()`, so the home survives `TD`, and cache errors become a `WARN:` instead of failing the action. |
| `window.py`  | `xdotool` wrappers: active window geometry (`getwindowgeometry --shell`, converted to the outer frame with `_NET_FRAME_EXTENTS`), WM class, and `move_window()`, which clamps to the X screen, runs `cfg.steps` resize+move steps eased with smoothstep and returns the geometry the window settled at. Before moving it drops `_NET_WM_STATE_MAXIMIZED_*` and `_NET_WM_STATE_FULLSCREEN`, which make window managers ignore moves. `geometry_matches()` compares with a 2 px tolerance. |
| `screen.py`  | One shared `Xlib.display.Display` (lazily created under a lock). `get_screens()` returns `(primary, others)`: the usable area of each RandR monitor, minus the panel struts that overlap it (`_NET_WM_STRUT_PARTIAL` of `_NET_CLIENT_LIST` windows; `_NET_WORKAREA` is a single rectangle and useless with several monitors), using the first active monitor when no primary output is set; `find_screen_for_window()` picks the monitor containing the window center, or the nearest one. |
| `cache.py`   | SQLite store keyed by `(window_id, wm_class)`: home geometry, the last target WinJitsu asked for (`last_*`) and the geometry the window settled at (`reached_*`, added to older databases). `_connect()` recreates the directory, database and table if they disappear while the daemon runs; reads that fail count as no cached state, and writes raise one of `CACHE_ERRORS`. `_resolve_home()` keeps the old home only while the window is still where it settled; otherwise its current geometry becomes the new home. |
| `config.py`  | `_Config` dataclass loaded from INI at import time into the module-level `cfg` (defaults: `steps=25`, `padding=0`, `delay_ms=250`); invalid values fall back to defaults with a warning. |

**Runtime files:**
- Config: `$XDG_CONFIG_HOME/winjitsu/config.ini` (default `~/.config/…`), sections `[animation] steps`, `[display] padding`, `[daemon] delay_ms`.
- Socket and PID: `$XDG_RUNTIME_DIR/winjitsu/winjitsu.sock` and `winjitsu.pid`.
- Window state: `~/.cache/winjitsu/state.db`.

**Gotchas:**
- Geometries are the window's outer frame. `xdotool getwindowgeometry` reports the client area, but window managers place the frame at the position given to `windowmove`, and `windowsize` sets the client area; `window.py` converts both ways.
- Use `config_timestamp`, not `timestamp`, for RandR output/CRTC queries; the latter causes `BadMatch` on some drivers (commented in `screen.py`).
- The daemon reads `cfg` once at startup, so config or code changes need `winjitsu --reload-daemon`.
- Replies starting with `WARN:` or `ERROR:` are printed by the client. `send_command()` returns `True` on success, `False` when the daemon replied `ERROR:` (exit 1) and `None` when the daemon cannot be reached (exit 1 with the "daemon is not running" hint).

## Actions Reference

`N S E W` — halves · `NE NW SE SW` — quarters · `C` — center, keeping size
`F` — fullscreen on the current monitor's usable area, minus `padding` (default 0)
`U` — restore the home position · `TF` — toggle fullscreen / home position
`TD` — move to the next monitor · `CC` — clear the window state cache

## Release

Versions live in `pyproject.toml` (`version`) and `arch/PKGBUILD` (`pkgver`) and must match. `.github/workflows/release.yaml` builds, smoke-tests and runs the unit tests on every run; on pushes and pull requests it only runs when the repository variable `WINJITSU_CI` is `true`. Running it manually with a version publishes the GitHub release, uploads to PyPI with Trusted Publishing (environment `pypi`) and copies `arch/PKGBUILD` to the `winjitsu` AUR package with `pkgrel=1` and a regenerated `.SRCINFO` (secret `AUR_SSH_PRIVATE_KEY`). `arch/PKGBUILD` is the source of truth for the AUR package:

```bash
gh workflow run release.yaml -R Evilchuck666/WinJitsu -f version=X.Y.Z --ref main
```
