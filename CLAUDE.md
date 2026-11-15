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

`tests/fakes.py` stands in for `xdotool` (reads and `windowsize`/`windowmove`) and an ICCCM window manager (frame decorations, resize increments, maximized windows), so the action tests run whole scenarios such as `W`, `U`, `TF`. No linter is configured. CI builds, runs `twine check`, smoke-tests the CLI without an X server (`--help`, `--see-config`, module imports) and runs the unit tests against the installed wheel.

**Dependencies:** `python-xlib` (Python, declared in `pyproject.toml`) and `xdotool` (system binary, called through `subprocess`). An X11 session with RandR is needed at runtime.

## Architecture

All code lives in `src/winjitsu/`. `__init__.py` re-exports `cli.main` and reads `__version__` from the installed metadata on first use (importing `importlib.metadata` would double the client's start-up time).

**Data flow:**
```
winjitsu ACTION → cli.main → client.send_command ──Unix socket──▶ daemon._CommandHandler
  → _schedule_action (debounce) → action queue → _action_worker → actions.dispatch
  → window.get_window_position + screen.get_screen_for_window
  → window.move_window (returns the settled geometry) → cache._update_state (save home, target, settled)
```

| Module       | Role                                                                                                                                  |
|--------------|---------------------------------------------------------------------------------------------------------------------------------------|
| `cli.py`     | argparse entry point. Pre-parses `--read-config` so it replaces the module-level config before anything uses it; `--steps`, `--padding`, `--delay-ms` (validated like the config file) then override it. Handles `--daemon`, `--reload-daemon` (signals only a PID `running_daemon_pid()` confirms), `--write-config`, `--see-config`, or sends the action to the daemon. Imports `daemon.py` only for `--daemon`/`--reload-daemon`, so sending an action never loads python-xlib. |
| `client.py`  | The light side: `VALID_ACTIONS`, runtime paths, `send_command()` and daemon detection. The daemon holds an exclusive `flock` on `winjitsu.lock` while it runs, so `running_daemon_pid()` trusts the PID file only while that lock is held, or, for daemons from before the lock, when `/proc/PID/cmdline` mentions winjitsu. |
| `daemon.py`  | Forks and detaches (`setsid`, stdio to `/dev/null`) and waits until the child listens before reporting; the child takes the lock (another daemon → exit status 3), writes the PID file, logs to `daemon.log` (and stderr in the foreground) and serves a `ThreadingUnixStreamServer` (socket mode `0600`). Debounce: the first action after a quiet `delay_ms` runs at once; actions within `delay_ms` of the previous one form a burst whose last action runs when it ends, unless it repeats the first (key repeat); superseded callers get `OK`. A single worker thread runs queued actions one at a time, in order, so animations never overlap and the X connection is used from one thread. A closed X connection is dropped (`screen.reset_display()`) and the action retried once. Clears the window cache on start. |
| `actions.py` | `dispatch()`. `_grid_targets()` gives halves, quarters and `F` (minus `padding`) of a monitor's usable area in whole pixels; `direction()` uses them, plus `C` (center, keeps size); `restore()` returns to the cached home; `_is_at()` tells whether a window is at a target or still where a cached move to it left it, which `toggle_fullscreen()` and `toggle_display()` use. `toggle_display()` cycles to the next monitor: a window at a grid position takes the same position there, any other keeps size and offset, shrunk to fit. Every move except `U` goes through `_move_and_remember()`, so the home survives `TD`, and cache errors become a `WARN:` instead of failing the action. |
| `window.py`  | `xdotool` wrappers with clear errors: active window geometry (`getwindowgeometry --shell`, converted to the outer frame with `_NET_FRAME_EXTENTS`), WM class, and `move_window()`, which clamps to the X screen, runs one `xdotool windowsize … windowmove …` per step for all `cfg.steps` smoothstep-eased steps and returns the geometry the window settled at. Keep it that way: xdotool waits for the X server before exiting, which paces the animation by what the system keeps up with; a fixed clock that skipped steps (0.5.0) looked jerky, and python-xlib with per-step waits (`sync()`, the window manager's `ConfigureNotify`, a minimum step time) was compared on real windows and not preferred, despite using about 20× less CPU. Before moving it drops `_NET_WM_STATE_MAXIMIZED_*` and `_NET_WM_STATE_FULLSCREEN`, which make window managers ignore moves. `geometry_matches()` compares with a 2 px tolerance. |
| `screen.py`  | One shared `Xlib.display.Display` (lazily created under a lock, dropped by `reset_display()`). `get_screens()` returns `(primary, others)`: the usable area of each RandR monitor, minus the panel struts that overlap it (`_NET_WM_STRUT_PARTIAL` of `_NET_CLIENT_LIST` windows; `_NET_WORKAREA` is a single rectangle and useless with several monitors), using the first active monitor when no primary output is set; `find_screen_for_window()` picks the monitor containing the window center, or the nearest one. |
| `cache.py`   | SQLite store keyed by `(window_id, wm_class)`: home geometry, the last target WinJitsu asked for (`last_*`) and the geometry the window settled at (`reached_*`). The schema version lives in `PRAGMA user_version` (`_SCHEMA_VERSION`): a different one drops the table, which is emptied on every daemon start anyway. `_connect()` recreates the directory, database and table if they disappear while the daemon runs; reads that fail count as no cached state, and writes raise one of `CACHE_ERRORS`. `_resolve_home()` keeps the old home only while the window is still where it settled; otherwise its current geometry becomes the new home. |
| `config.py`  | `_Config` dataclass loaded from INI at import time into the module-level `cfg`. `OPTIONS` holds each option's section, default and range (`steps` 1–1000 = 25, `padding` 0–500 = 0, `delay_ms` 0–5000 = 250); `validate()` checks one value, and an invalid value in the file falls back to its own default with a warning. `_xdg_dir()` treats an empty XDG variable as unset. |

**Runtime files:**
- Config: `$XDG_CONFIG_HOME/winjitsu/config.ini` (default `~/.config/…`), sections `[animation] steps`, `[display] padding`, `[daemon] delay_ms`.
- Socket, PID and lock: `$XDG_RUNTIME_DIR/winjitsu/winjitsu.sock`, `winjitsu.pid` and `winjitsu.lock`.
- Window state: `$XDG_CACHE_HOME/winjitsu/state.db` (default `~/.cache/…`).
- Daemon log: `$XDG_STATE_HOME/winjitsu/daemon.log` (default `~/.local/state/…`), rotated at 256 KiB.

**Gotchas:**
- Geometries are the window's outer frame. `xdotool getwindowgeometry` reports the client area, but window managers place the frame at the position given to `windowmove`, and `windowsize` sets the client area; `window.py` converts both ways.
- A dev daemon run next to the installed one needs its own `XDG_RUNTIME_DIR`, `XDG_CACHE_HOME` and `XDG_STATE_HOME` (the workspace's debug configuration sets them): with a newer cache schema it would drop the table the other daemon uses.
- Use `config_timestamp`, not `timestamp`, for RandR output/CRTC queries; the latter causes `BadMatch` on some drivers (commented in `screen.py`).
- The daemon reads `cfg` once at startup, so config or code changes need `winjitsu --reload-daemon`.
- Replies starting with `WARN:` or `ERROR:` are printed by the client. `send_command()` returns `True` on success, `False` when it failed with the reason printed (an `ERROR:` reply, no answer within `client._CLIENT_TIMEOUT`, other socket errors; exit 1) and `None` only when no daemon listens (missing socket or connection refused; exit 1 with the "daemon is not running" hint). The daemon answers within `delay_ms` + `ACTION_TIMEOUT`, before the client gives up.

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
