# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

WinJitsu is a lightweight animated window management tool for Linux X11. It snaps windows to grid positions and monitors using smooth 25-step animations, driven by `xdotool` and `xrandr` shell commands.

## Commands

```bash
# Install locally for development
pip install -e .

# Run directly
winjitsu <action>

# Build wheel
python3 -m build
```

No test suite or linter is configured. The project has no Python dependencies (stdlib only).

**System requirements:** `xdotool` and `xrandr` must be installed.

## Architecture

All logic lives in `src/winjitsu/winjitsu.py` (~380 lines). `src/winjitsu/__init__.py` just re-exports `main`.

**Data flow:**
```
main(action) → handler → get_window_position() + get_screens() → move_window()
```

**Key functions:**

| Function                       | Role                                                                                           |
|--------------------------------|------------------------------------------------------------------------------------------------|
| `get_window_position()`        | Calls `xdotool getactivewindow` + `getwindowgeometry`; returns `{WINDOW, X, Y, WIDTH, HEIGHT}` |
| `get_screens()`                | Parses `xrandr` output; returns `{primary: {width, height}, others: [...]}`                    |
| `move_window(wid, x, y, w, h)` | Runs 25 interpolation steps via `xdotool windowmove/windowsize`                                |
| `direction(d)`                 | Handles N/S/E/W/NE/NW/SE/SW/C grid snapping                                                    |
| `fullscreen()` / `unscreen()`  | Full-monitor expand and restore from cache                                                     |
| `toggle_fullscreen()`          | Smart toggle using cached pre-fullscreen state                                                 |
| `toggle_display()`             | Moves window to alternate monitor, adjusting for its offset                                    |

**Cache:** Window state is saved to `~/.cache/winjitsu/<window_id>.pid` in `KEY=VALUE` format before fullscreen operations, enabling restore with `U` / `TF`.

## Actions Reference

`N S E W NE NW SE SW C` — grid snapping (half-screen quadrants/halves/center)  
`F` — fullscreen (near-maximized with 5px padding)  
`U` — restore from cache  
`TF` — toggle fullscreen  
`TD` — move to other monitor  
`CC` — clear cache