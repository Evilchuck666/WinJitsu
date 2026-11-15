# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

WinJitsu is an animated window snapping tool for Linux X11. A background daemon receives actions (`N`, `TF`, `TD`, …) from the `winjitsu` CLI over a Unix socket, works out the target geometry for the active window and glides it there with an eased (smoothstep) animation driven by `xdotool`. Monitors are detected through the RandR extension with `python-xlib`, and every action goes on a per-window undo history in SQLite, so `U` can take the window back step by step.

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
  → window.move_window (returns the settled geometry) → cache.push_entry (undo history: before, states, target, settled)
```

| Module       | Role                                                                                                                                  |
|--------------|---------------------------------------------------------------------------------------------------------------------------------------|
| `cli.py`     | argparse entry point. Pre-parses `--read-config` so it replaces the module-level config before anything uses it; `--steps`, `--padding`, `--delay-ms` (validated like the config file) then override it. Handles `--daemon`, `--reload-daemon` (signals only a PID `running_daemon_pid()` confirms), `--write-config`, `--see-config`, or sends the action to the daemon. Imports `daemon.py` only for `--daemon`/`--reload-daemon`, so sending an action never loads python-xlib. |
| `client.py`  | The light side: `VALID_ACTIONS`, runtime paths, `send_command()` and daemon detection. The daemon holds an exclusive `flock` on `winjitsu.lock` while it runs, so `running_daemon_pid()` trusts the PID file only while that lock is held, or, for daemons from before the lock, when `/proc/PID/cmdline` mentions winjitsu. |
| `daemon.py`  | Forks and detaches (`setsid`, stdio to `/dev/null`) and waits until the child listens before reporting; the child takes the lock (another daemon → exit status 3), writes the PID file, logs to `daemon.log` (and stderr in the foreground) and serves a `ThreadingUnixStreamServer` (socket mode `0600`). Debounce: the first action after a quiet `delay_ms` runs at once; actions within `delay_ms` of the previous one form a burst whose last action runs when it ends, unless it repeats the first (key repeat); superseded callers get `OK`. A single worker thread runs queued actions one at a time, in order, so animations never overlap and the X connection is used from one thread. A closed X connection is dropped (`screen.reset_display()`) and the action retried once. Clears the window cache on start. |
| `actions.py` | `dispatch()`. `_grid_targets()` gives halves, quarters and `F` (minus `padding`) of a monitor's usable area in whole pixels; `direction()` uses them, plus `C` (center, keeps size); `_is_at()` tells whether a window is at a target or still where the last action (top of its undo history) left it, which `toggle_fullscreen()` and `toggle_display()` use. `undo()` (`U`): if the window was moved or maximized by hand since the last action, it goes back to where that action left it; otherwise the action is popped and the window returns to its `before` geometry, with its window manager states restored (`window.restore_states()`). Leaving fullscreen with `TF` is an `undo()`. `toggle_display()` cycles to the next monitor: a window at a grid position takes the same position there, any other keeps size and offset, shrunk to fit. Every other move goes through `_move_and_push()`, which releases a maximized window first (its `before` is then the geometry the window manager gives back), moves it, skips moves that changed nothing, pushes the action and turns cache errors into a `WARN:` instead of failing the action. |
| `window.py`  | `xdotool` wrappers with clear errors: active window geometry (`getwindowgeometry --shell`, converted to the outer frame with `_NET_FRAME_EXTENTS`), WM class, and `move_window()`, which clamps to the X screen, runs one `xdotool windowsize … windowmove …` per step for all `cfg.steps` smoothstep-eased steps and returns the geometry the window settled at. Keep it that way: xdotool waits for the X server before exiting, which paces the animation by what the system keeps up with; a fixed clock that skipped steps (0.5.0) looked jerky, and python-xlib with per-step waits (`sync()`, the window manager's `ConfigureNotify`, a minimum step time) was compared on real windows and not preferred, despite using about 20× less CPU. Before moving it drops `_NET_WM_STATE_MAXIMIZED_*` and `_NET_WM_STATE_FULLSCREEN`, which make window managers ignore moves. `geometry_matches()` compares with a 2 px tolerance. |
| `screen.py`  | One shared `Xlib.display.Display` (lazily created under a lock, dropped by `reset_display()`). `get_screens()` returns `(primary, others)`: the usable area of each RandR monitor, minus the panel struts that overlap it (`_NET_WM_STRUT_PARTIAL` of `_NET_CLIENT_LIST` windows; `_NET_WORKAREA` is a single rectangle and useless with several monitors), using the first active monitor when no primary output is set; `find_screen_for_window()` picks the monitor containing the window center, or the nearest one. |
| `cache.py`   | The undo history in SQLite: table `history`, one row per action keyed by `(window_id, wm_class, seq)` with the `before` geometry and removed WM states, the `target` and the geometry the window settled at (`reached`); no depth limit. `push_entry()`, `top_entry()`, `pop_entry()`, `clear_cache()`. The schema version lives in `PRAGMA user_version` (`_SCHEMA_VERSION`): a different one drops the tables, which are emptied on every daemon start anyway. `_connect()` recreates the directory, database and table if they disappear while the daemon runs; reads that fail count as no history, and writes raise one of `CACHE_ERRORS`. |
| `config.py`  | `_Config` dataclass loaded from INI at import time into the module-level `cfg`. `OPTIONS` holds each option's section, default and range (`steps` 1–1000 = 25, `padding` 0–500 = 0, `delay_ms` 0–5000 = 250); `validate()` checks one value, and an invalid value in the file falls back to its own default with a warning. `_xdg_dir()` treats an empty XDG variable as unset. |

**Runtime files:**
- Config: `$XDG_CONFIG_HOME/winjitsu/config.ini` (default `~/.config/…`), sections `[animation] steps`, `[display] padding`, `[daemon] delay_ms`.
- Socket, PID and lock: `$XDG_RUNTIME_DIR/winjitsu/winjitsu.sock`, `winjitsu.pid` and `winjitsu.lock`.
- Undo history: `$XDG_CACHE_HOME/winjitsu/state.db` (default `~/.cache/…`).
- Daemon log: `$XDG_STATE_HOME/winjitsu/daemon.log` (default `~/.local/state/…`), rotated at 256 KiB.

**Gotchas:**
- Geometries are the window's outer frame. `xdotool getwindowgeometry` reports the client area, but window managers place the frame at the position given to `windowmove`, and `windowsize` sets the client area; `window.py` converts both ways.
- A dev daemon run next to the installed one needs its own `XDG_RUNTIME_DIR`, `XDG_CACHE_HOME` and `XDG_STATE_HOME` (the debug configuration in `.vscode/launch.json` sets them): with a newer cache schema it would drop the table the other daemon uses.
- Use `config_timestamp`, not `timestamp`, for RandR output/CRTC queries; the latter causes `BadMatch` on some drivers (commented in `screen.py`).
- The daemon reads `cfg` once at startup, so config or code changes need `winjitsu --reload-daemon`.
- Replies starting with `WARN:` or `ERROR:` are printed by the client. `send_command()` returns `True` on success, `False` when it failed with the reason printed (an `ERROR:` reply, no answer within `client._CLIENT_TIMEOUT`, other socket errors; exit 1) and `None` only when no daemon listens (missing socket or connection refused; exit 1 with the "daemon is not running" hint). The daemon answers within `delay_ms` + `ACTION_TIMEOUT`, before the client gives up.

## Actions Reference

`N S E W` — halves · `NE NW SE SW` — quarters · `C` — center, keeping size
`F` — fullscreen on the current monitor's usable area, minus `padding` (default 0)
`U` — undo the last action on the window (repeatable) · `TF` — toggle fullscreen (leaving it undoes)
`TD` — move to the next monitor · `CC` — clear the undo history

## Release

Versions live in `pyproject.toml` (`version`) and `arch/PKGBUILD` (`pkgver`) and must match.

**Bumping the version also means updating `README.md` and the project page (`site/index.html`), in the same commit.** Both link the files of a specific release (`releases/download/vX.Y.Z/winjitsu-X.Y.Z-py3-none-any.whl`, `winjitsu-X.Y.Z.tar.gz`): in `README.md` the "GitHub release" row of the Download table; in `site/index.html` the download list's `aria-label`, the wheel and source buttons with their `<small>` labels and `SHA256SUMS.txt`. Every `X.Y.Z` there must be the new version. The links work once the release exists, so run the release workflow right after pushing the bump (the push also redeploys the page). The release workflow refuses to publish if `README.md` or `site/index.html` don't link the wheel of the version being released. `.github/workflows/release.yaml` builds, smoke-tests and runs the unit tests on every run; on pushes and pull requests it only runs when the repository variable `WINJITSU_CI` is `true`. Running it manually with a version publishes the GitHub release, uploads to PyPI with Trusted Publishing (environment `pypi`) and copies `arch/PKGBUILD` to the `winjitsu` AUR package with `pkgrel=1` and a regenerated `.SRCINFO` (secret `AUR_SSH_PRIVATE_KEY`). `arch/PKGBUILD` is the source of truth for the AUR package:

```bash
gh workflow run release.yaml -R Evilchuck666/WinJitsu -f version=X.Y.Z --ref main
```
