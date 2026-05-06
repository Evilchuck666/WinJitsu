#!/usr/bin/env python3
import os
import sys
import subprocess
import argparse
import re
import json
import shutil
import signal
import socket
import socketserver
import threading
import configparser
from pathlib import Path


# ── Cache ──────────────────────────────────────────────────────────────────
CACHE_DIR = Path.home() / ".cache" / "winjitsu"

# ── Runtime (socket / PID) ─────────────────────────────────────────────────
_XDG_DATA_HOME = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share"))
_RUNTIME_DIR   = _XDG_DATA_HOME / "winjitsu"
SOCKET_PATH    = _RUNTIME_DIR / "winjitsu.sock"
PID_PATH       = _RUNTIME_DIR / "winjitsu.pid"

# ── Config ─────────────────────────────────────────────────────────────────
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

# Fallback screen resolution used when xrandr cannot be read.
# fallback_width  = 1920
# fallback_height = 1080
"""

def _load_config(path=None):
    cfg = configparser.ConfigParser()
    cfg.read_dict({
        "animation": {"steps": "25"},
        "display":   {"padding": "0", "fallback_width": "1920", "fallback_height": "1080"},
    })
    cfg.read(path or _CONFIG_PATH)
    return cfg

def _write_config(path):
    if path.exists():
        answer = input(f"Config already exists: {path}\nOverwrite? [y/N] ").strip().lower()
        if answer not in ("y", "yes"):
            print("Aborted.")
            return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(_CONFIG_TEMPLATE)
    print(f"Config written to: {path}")

_active_config_path = _CONFIG_PATH
_CFG       = _load_config()
ANIM_STEPS = _CFG.getint("animation", "steps")
PADDING    = _CFG.getint("display",   "padding")
FALLBACK_W = _CFG.getint("display",   "fallback_width")
FALLBACK_H = _CFG.getint("display",   "fallback_height")


# ── X11 queries ────────────────────────────────────────────────────────────

def get_window_position():
    try:
        wid = subprocess.check_output(["xdotool", "getactivewindow"]).decode().strip()
        out = subprocess.check_output(["xdotool", "getwindowgeometry", "--shell", wid]).decode()
        data = {}
        for line in out.splitlines():
            k, v = line.split("=", 1)
            data[k] = int(v)
        return data
    except subprocess.CalledProcessError:
        raise RuntimeError("Could not get window position. Is xdotool installed?")


def get_screens():
    try:
        out = subprocess.check_output(["xrandr"]).decode()
    except subprocess.CalledProcessError:
        raise RuntimeError("Could not run xrandr. Is it installed?")

    primary = None
    others  = []

    for line in out.splitlines():
        if " connected" not in line:
            continue
        is_primary = " primary " in line
        # Parse WxH+X+Y directly from the "connected" line (active mode)
        match = re.search(r'(\d+)x(\d+)\+(\d+)\+(\d+)', line)
        if not match:
            continue  # connected but no active mode (monitor off)
        w, h, x, y = (int(match.group(i)) for i in range(1, 5))
        screen = {"width": w, "height": h, "x": x, "y": y}
        if is_primary:
            primary = screen
        else:
            others.append(screen)

    return primary, others


def get_wm_class(window_id):
    try:
        return subprocess.check_output(
            ["xdotool", "getwindowclassname", str(window_id)]
        ).decode().strip()
    except subprocess.CalledProcessError:
        return None


def get_screen_for_window(x_pos):
    primary, others = get_screens()
    if not primary:
        return FALLBACK_W, FALLBACK_H, 0

    for screen in [primary] + others:
        if screen["x"] <= x_pos < screen["x"] + screen["width"]:
            return screen["width"], screen["height"], screen["x"]

    return primary["width"], primary["height"], primary["x"]


# ── Cache I/O ──────────────────────────────────────────────────────────────

def save_cache(window_id, data, wm_class):
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    with open(CACHE_DIR / f"{window_id}.json", "w") as f:
        json.dump({**data, "WM_CLASS": wm_class}, f)


def load_cache(window_id, wm_class):
    cache_file = CACHE_DIR / f"{window_id}.json"
    if not cache_file.exists():
        return None
    try:
        with open(cache_file) as f:
            data = json.load(f)
    except (json.JSONDecodeError, ValueError):
        return None
    if data.get("WM_CLASS") != wm_class:
        return None
    return {k: v for k, v in data.items() if k != "WM_CLASS"}


def clear_cache():
    if CACHE_DIR.exists():
        shutil.rmtree(CACHE_DIR)


# ── Animation ──────────────────────────────────────────────────────────────

def move_window(target_w, target_h, window_id, current_w, current_h, current_x, current_y, target_x, target_y):
    w_step = (target_w - current_w) / ANIM_STEPS
    h_step = (target_h - current_h) / ANIM_STEPS
    x_step = (current_x - target_x) / ANIM_STEPS
    y_step = (current_y - target_y) / ANIM_STEPS

    new_w, new_h, new_x, new_y = current_w, current_h, current_x, current_y
    wid = str(window_id)

    for _ in range(ANIM_STEPS):
        new_w += w_step
        new_h += h_step
        new_x -= x_step
        new_y -= y_step
        subprocess.run([
            "xdotool",
            "windowsize", wid, str(round(new_w)), str(round(new_h)),
            "windowmove", wid, str(round(new_x)), str(round(new_y)),
        ])

    subprocess.run([
        "xdotool",
        "windowsize", wid, str(int(target_w)), str(int(target_h)),
        "windowmove", wid, str(int(target_x)), str(int(target_y)),
    ])


# ── Actions ────────────────────────────────────────────────────────────────

def fullscreen():
    win = get_window_position()
    save_cache(win["WINDOW"], win, get_wm_class(win["WINDOW"]))
    screen_w, screen_h, base_x = get_screen_for_window(win["X"])
    move_window(
        screen_w - 2 * PADDING, screen_h - 2 * PADDING,
        win["WINDOW"],
        win["WIDTH"], win["HEIGHT"], win["X"], win["Y"],
        base_x + PADDING, PADDING,
    )


def unscreen():
    win   = get_window_position()
    saved = load_cache(win["WINDOW"], get_wm_class(win["WINDOW"]))
    if saved:
        move_window(
            saved["WIDTH"], saved["HEIGHT"],
            win["WINDOW"],
            win["WIDTH"],  win["HEIGHT"],
            win["X"],      win["Y"],
            saved["X"],    saved["Y"],
        )


def toggle_fullscreen():
    win = get_window_position()
    screen_w, _, _ = get_screen_for_window(win["X"])
    if win["WIDTH"] == screen_w - 2 * PADDING:
        unscreen()
    else:
        fullscreen()


def direction(direction_code):
    win = get_window_position()
    screen_w, screen_h, base_x = get_screen_for_window(win["X"])
    half_w = screen_w / 2
    half_h = screen_h / 2

    targets = {
        "N":  (screen_w, half_h,        base_x,          0),
        "S":  (screen_w, half_h,        base_x,          half_h),
        "E":  (half_w,   screen_h,      base_x + half_w, 0),
        "W":  (half_w,   screen_h,      base_x,          0),
        "NE": (half_w,   half_h,        base_x + half_w, 0),
        "NW": (half_w,   half_h,        base_x,          0),
        "SE": (half_w,   half_h,        base_x + half_w, half_h),
        "SW": (half_w,   half_h,        base_x,          half_h),
        "C":  (win["WIDTH"], win["HEIGHT"],
               (screen_w - win["WIDTH"])  / 2 + base_x,
               (screen_h - win["HEIGHT"]) / 2),
    }
    tw, th, tx, ty = targets[direction_code]
    move_window(tw, th, win["WINDOW"], win["WIDTH"], win["HEIGHT"], win["X"], win["Y"], tx, ty)


def toggle_display():
    win = get_window_position()
    primary, others = get_screens()
    if not primary or not others:
        return

    all_screens = [primary] + others
    current = next(
        (s for s in all_screens if s["x"] <= win["X"] < s["x"] + s["width"]),
        primary,
    )
    target = all_screens[(all_screens.index(current) + 1) % len(all_screens)]

    move_window(
        win["WIDTH"], win["HEIGHT"],
        win["WINDOW"],
        win["WIDTH"],  win["HEIGHT"], win["X"], win["Y"],
        target["x"] + (win["X"] - current["x"]),
        target["y"] + (win["Y"] - current["y"]),
    )


# ── Daemon ─────────────────────────────────────────────────────────────────

VALID_ACTIONS = ["N", "S", "E", "W", "NE", "NW", "SE", "SW", "C", "F", "U", "TF", "TD", "CC"]


def dispatch(action):
    if action in ["N", "S", "E", "W", "NE", "NW", "SE", "SW", "C"]:
        direction(action)
    elif action == "F":  fullscreen()
    elif action == "U":  unscreen()
    elif action == "TF": toggle_fullscreen()
    elif action == "TD": toggle_display()
    elif action == "CC": clear_cache()
    else: raise ValueError(f"Unknown action: {action!r}")


class _CommandHandler(socketserver.StreamRequestHandler):
    timeout = 5

    def handle(self):
        line = self.rfile.readline(256).decode().strip()
        if not line or line not in VALID_ACTIONS:
            self.wfile.write(b"ERROR: invalid action\n")
            return
        self.wfile.write(b"OK\n")
        self.wfile.flush()
        dispatch(line)


def _cleanup_stale_runtime():
    if PID_PATH.exists():
        try:
            pid = int(PID_PATH.read_text().strip())
            os.kill(pid, 0)
            print(f"winjitsu daemon already running (PID {pid})", file=sys.stderr)
            sys.exit(1)
        except (ValueError, ProcessLookupError):
            PID_PATH.unlink(missing_ok=True)
        except PermissionError:
            print("winjitsu daemon already running", file=sys.stderr)
            sys.exit(1)
    SOCKET_PATH.unlink(missing_ok=True)


def _cleanup_runtime_files():
    SOCKET_PATH.unlink(missing_ok=True)
    PID_PATH.unlink(missing_ok=True)


def run_daemon():
    _RUNTIME_DIR.mkdir(parents=True, exist_ok=True)
    _cleanup_stale_runtime()
    PID_PATH.write_text(str(os.getpid()))

    server     = socketserver.ThreadingUnixStreamServer(str(SOCKET_PATH), _CommandHandler)
    stop_event = threading.Event()

    def _on_signal(signum, frame):
        stop_event.set()

    signal.signal(signal.SIGTERM, _on_signal)
    signal.signal(signal.SIGINT,  _on_signal)

    threading.Thread(target=server.serve_forever, daemon=True).start()
    stop_event.wait()

    try:
        clear_cache()
    finally:
        server.shutdown()
        server.server_close()
        _cleanup_runtime_files()


def send_command(action):
    if not SOCKET_PATH.exists():
        return False
    try:
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as s:
            s.settimeout(2.0)
            s.connect(str(SOCKET_PATH))
            s.sendall(f"{action}\n".encode())
            with s.makefile("r") as f:
                response = f.readline().strip()
        return response == "OK"
    except (FileNotFoundError, ConnectionRefusedError, TimeoutError, OSError):
        return False


# ── Entry point ────────────────────────────────────────────────────────────

_HELP_EPILOG = """
actions:
  grid snapping:
    N / S           snap to top / bottom half of the screen
    E / W           snap to right / left half of the screen
    NE / NW         snap to top-right / top-left quarter
    SE / SW         snap to bottom-right / bottom-left quarter
    C               center window (keeps current size)

  fullscreen:
    F               fullscreen (covers the entire monitor)
    U               restore window to its state before fullscreen
    TF              toggle fullscreen / restore

  multi-monitor:
    TD              move window to the next monitor

  cache:
    CC              clear the window state cache

config file: ~/.config/winjitsu/config.ini  (XDG_CONFIG_HOME honoured)
  --write-config    create config file with defaults (all options commented out)
  --read-config     use a different config file path
  --see-config      show active config file and current values
"""

def main():
    # Pre-parse --read-config before the main parser so globals are updated
    # before any action uses them.
    pre = argparse.ArgumentParser(add_help=False)
    pre.add_argument("--read-config", metavar="PATH")
    pre_args, _ = pre.parse_known_args()
    if pre_args.read_config:
        global ANIM_STEPS, PADDING, FALLBACK_W, FALLBACK_H, _active_config_path
        _active_config_path = Path(pre_args.read_config)
        _cfg = _load_config(_active_config_path)
        ANIM_STEPS = _cfg.getint("animation", "steps")
        PADDING    = _cfg.getint("display",   "padding")
        FALLBACK_W = _cfg.getint("display",   "fallback_width")
        FALLBACK_H = _cfg.getint("display",   "fallback_height")

    parser = argparse.ArgumentParser(
        description="Animated window management tool for Linux X11.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=_HELP_EPILOG,
    )
    parser.add_argument("action", nargs="?", choices=VALID_ACTIONS, metavar="ACTION",
                        help="window management action (see below)")
    parser.add_argument("--daemon",       action="store_true", help="start background daemon")
    parser.add_argument("--write-config", action="store_true", help="create config file with defaults and exit")
    parser.add_argument("--read-config",  metavar="PATH",      help="use a custom config file path")
    parser.add_argument("--see-config",   action="store_true", help="print current config values and exit")
    args = parser.parse_args()

    if args.write_config:
        _write_config(_active_config_path)
        return

    if args.see_config:
        status = "exists" if _active_config_path.exists() else "not found — using defaults"
        print(f"config file : {_active_config_path}  ({status})")
        print(f"steps       : {ANIM_STEPS}")
        print(f"padding     : {PADDING}")
        print(f"fallback_w  : {FALLBACK_W}")
        print(f"fallback_h  : {FALLBACK_H}")
        return

    if args.daemon:
        _RUNTIME_DIR.mkdir(parents=True, exist_ok=True)
        if PID_PATH.exists():
            try:
                existing_pid = int(PID_PATH.read_text().strip())
                os.kill(existing_pid, 0)
                print(f"winjitsu daemon already running (PID {existing_pid})", file=sys.stderr)
                sys.exit(1)
            except (ValueError, ProcessLookupError):
                PID_PATH.unlink(missing_ok=True)
            except PermissionError:
                print("winjitsu daemon already running", file=sys.stderr)
                sys.exit(1)
        pid = os.fork()
        if pid > 0:
            print(f"winjitsu daemon starting (PID {pid})")
            sys.exit(0)
        os.setsid()
        devnull = open(os.devnull, "r+")
        for fd in (0, 1, 2):
            os.dup2(devnull.fileno(), fd)
        devnull.close()
        run_daemon()
        return

    if args.action is None:
        parser.print_help()
        sys.exit(1)

    try:
        if not send_command(args.action):
            dispatch(args.action)
    except RuntimeError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
