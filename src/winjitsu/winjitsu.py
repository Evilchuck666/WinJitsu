#!/usr/bin/env python3
import os
import sys
import subprocess
import argparse
import json
import shutil
import signal
import socket
import socketserver
import threading
import configparser
import time
from dataclasses import dataclass
from pathlib import Path
from Xlib import display as Xdisplay
from Xlib.ext import randr


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

_display: "Xdisplay.Display | None" = None
_display_lock = threading.Lock()

def _get_display() -> Xdisplay.Display:
    global _display
    if _display is None:
        with _display_lock:
            if _display is None:
                _display = Xdisplay.Display()
    return _display


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
    display = _get_display()
    if not display.has_extension('RANDR'):
        raise RuntimeError("RandR extension not available.")
    root      = display.screen().root
    resources = root.xrandr_get_screen_resources()
    ts        = resources.config_timestamp  # config_timestamp, NOT timestamp — timestamp causes BadMatch on some drivers
    primary_id = root.xrandr_get_output_primary().output

    primary = None
    others  = []

    for output_id in resources.outputs:
        info = display.xrandr_get_output_info(output_id, ts)
        if info.connection != randr.Connected or not info.crtc:
            continue
        crtc = display.xrandr_get_crtc_info(info.crtc, ts)
        s = {"width": crtc.width, "height": crtc.height, "x": crtc.x, "y": crtc.y}
        if output_id == primary_id:
            primary = s
        else:
            others.append(s)

    return primary, others


def get_wm_class(window_id):
    try:
        return subprocess.check_output(
            ["xdotool", "getwindowclassname", str(window_id)]
        ).decode().strip()
    except subprocess.CalledProcessError:
        return None


def get_screen_for_window(win):
    primary, others = get_screens()
    if not primary:
        d = _get_display().screen()
        return d.width_in_pixels, d.height_in_pixels, 0, 0

    all_screens = [primary] + others
    win_cx = win["X"] + win["WIDTH"] / 2
    win_cy = win["Y"] + win["HEIGHT"] / 2

    def _dist(s):
        return (win_cx - (s["x"] + s["width"] / 2)) ** 2 + (win_cy - (s["y"] + s["height"] / 2)) ** 2

    screen = next(
        (s for s in all_screens
         if s["x"] <= win_cx < s["x"] + s["width"] and s["y"] <= win_cy < s["y"] + s["height"]),
        min(all_screens, key=_dist),
    )
    return screen["width"], screen["height"], screen["x"], screen["y"]


# ── Cache I/O ──────────────────────────────────────────────────────────────

def load_state(window_id, wm_class):
    path = CACHE_DIR / f"{window_id}.json"
    if not path.exists():
        return None
    try:
        with open(path) as f:
            data = json.load(f)
    except (json.JSONDecodeError, ValueError):
        return None
    if data.get("WM_CLASS") != wm_class:
        return None
    return data


def save_state(window_id, home, tx, ty, tw, th, wm_class):
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    with open(CACHE_DIR / f"{window_id}.json", "w") as f:
        json.dump({
            "WINDOW": home["WINDOW"],
            "X": home["X"], "Y": home["Y"],
            "WIDTH": home["WIDTH"], "HEIGHT": home["HEIGHT"],
            "SCREEN": home.get("SCREEN", 0),
            "WM_CLASS": wm_class,
            "_last_X": tx, "_last_Y": ty,
            "_last_W": tw, "_last_H": th,
        }, f)


def _resolve_home(win, existing):
    if existing is None:
        return win
    last = (existing.get("_last_X"), existing.get("_last_Y"),
            existing.get("_last_W"), existing.get("_last_H"))
    if None in last:
        return win
    if (win["X"] == last[0] and win["Y"] == last[1] and
            win["WIDTH"] == last[2] and win["HEIGHT"] == last[3]):
        return {k: existing[k] for k in ("WINDOW", "X", "Y", "WIDTH", "HEIGHT", "SCREEN")}
    return win


def _update_state(win, tx, ty, tw, th):
    wm = get_wm_class(win["WINDOW"])
    existing = load_state(win["WINDOW"], wm)
    home = _resolve_home(win, existing)
    save_state(win["WINDOW"], home, tx, ty, tw, th, wm)


def clear_cache():
    if CACHE_DIR.exists():
        shutil.rmtree(CACHE_DIR)


# ── Animation ──────────────────────────────────────────────────────────────

def move_window(target_w, target_h, window_id, current_w, current_h, current_x, current_y, target_x, target_y):
    def _ease(t):
        return t * t * (3.0 - 2.0 * t)

    screen = _get_display().screen()
    dw, dh = screen.width_in_pixels, screen.height_in_pixels
    target_w = min(target_w, dw)
    target_h = min(target_h, dh)
    target_x = max(0, min(target_x, dw - target_w))
    target_y = max(0, min(target_y, dh - target_h))

    wid = str(window_id)
    for i in range(1, _CFG.steps + 1):
        t = _ease(i / _CFG.steps)
        w = current_w + (target_w - current_w) * t
        h = current_h + (target_h - current_h) * t
        x = current_x + (target_x - current_x) * t
        y = current_y + (target_y - current_y) * t
        subprocess.run([
            "xdotool",
            "windowsize", wid, str(round(w)), str(round(h)),
            "windowmove", wid, str(round(x)), str(round(y)),
        ])


# ── Actions ────────────────────────────────────────────────────────────────

def fullscreen(win=None, screen_w=None, screen_h=None, base_x=None, base_y=None):
    win = win or get_window_position()
    if screen_w is None:
        screen_w, screen_h, base_x, base_y = get_screen_for_window(win)
    tx, ty = base_x + _CFG.padding, base_y + _CFG.padding
    tw, th = screen_w - 2 * _CFG.padding, screen_h - 2 * _CFG.padding
    _update_state(win, tx, ty, tw, th)
    move_window(tw, th, win["WINDOW"], win["WIDTH"], win["HEIGHT"], win["X"], win["Y"], tx, ty)


def restore(win=None):
    win = win or get_window_position()
    saved = load_state(win["WINDOW"], get_wm_class(win["WINDOW"]))
    if saved:
        move_window(
            saved["WIDTH"], saved["HEIGHT"],
            win["WINDOW"],
            win["WIDTH"],  win["HEIGHT"],
            win["X"],      win["Y"],
            saved["X"],    saved["Y"],
        )


def toggle_fullscreen(win=None):
    win = win or get_window_position()
    screen_w, screen_h, base_x, base_y = get_screen_for_window(win)
    if win["WIDTH"] == screen_w - 2 * _CFG.padding and win["HEIGHT"] == screen_h - 2 * _CFG.padding:
        restore(win)
    else:
        fullscreen(win, screen_w, screen_h, base_x, base_y)


def direction(direction_code):
    win = get_window_position()
    screen_w, screen_h, base_x, base_y = get_screen_for_window(win)
    half_w = screen_w / 2
    half_h = screen_h / 2

    targets = {
        "N":  (screen_w, half_h,        base_x,          base_y),
        "S":  (screen_w, half_h,        base_x,          base_y + half_h),
        "E":  (half_w,   screen_h,      base_x + half_w, base_y),
        "W":  (half_w,   screen_h,      base_x,          base_y),
        "NE": (half_w,   half_h,        base_x + half_w, base_y),
        "NW": (half_w,   half_h,        base_x,          base_y),
        "SE": (half_w,   half_h,        base_x + half_w, base_y + half_h),
        "SW": (half_w,   half_h,        base_x,          base_y + half_h),
        "C":  (win["WIDTH"], win["HEIGHT"],
               (screen_w - win["WIDTH"])  / 2 + base_x,
               (screen_h - win["HEIGHT"]) / 2 + base_y),
    }
    tw, th, tx, ty = targets[direction_code]
    _update_state(win, tx, ty, tw, th)
    move_window(tw, th, win["WINDOW"], win["WIDTH"], win["HEIGHT"], win["X"], win["Y"], tx, ty)


def toggle_display():
    win = get_window_position()
    primary, others = get_screens()
    if not primary or not others:
        return

    all_screens = [primary] + others
    win_cx = win["X"] + win["WIDTH"] / 2
    win_cy = win["Y"] + win["HEIGHT"] / 2

    def _dist(s):
        return (win_cx - (s["x"] + s["width"] / 2)) ** 2 + (win_cy - (s["y"] + s["height"] / 2)) ** 2

    current = next(
        (s for s in all_screens
         if s["x"] <= win_cx < s["x"] + s["width"] and s["y"] <= win_cy < s["y"] + s["height"]),
        min(all_screens, key=_dist),
    )
    target = all_screens[(all_screens.index(current) + 1) % len(all_screens)]

    tx = target["x"] + (win["X"] - current["x"])
    ty = target["y"] + (win["Y"] - current["y"])
    wm = get_wm_class(win["WINDOW"])
    target_home = {"WINDOW": win["WINDOW"], "X": tx, "Y": ty,
                   "WIDTH": win["WIDTH"], "HEIGHT": win["HEIGHT"],
                   "SCREEN": all_screens.index(target)}
    save_state(win["WINDOW"], target_home, tx, ty, win["WIDTH"], win["HEIGHT"], wm)
    move_window(win["WIDTH"], win["HEIGHT"], win["WINDOW"],
                win["WIDTH"], win["HEIGHT"], win["X"], win["Y"], tx, ty)


# ── Daemon ─────────────────────────────────────────────────────────────────

VALID_ACTIONS = ["N", "S", "E", "W", "NE", "NW", "SE", "SW", "C", "F", "U", "TF", "TD", "CC"]


def dispatch(action):
    if action in ["N", "S", "E", "W", "NE", "NW", "SE", "SW", "C"]:
        direction(action)
    elif action == "F":  fullscreen()
    elif action == "U":  restore()
    elif action == "TF": toggle_fullscreen()
    elif action == "TD": toggle_display()
    elif action == "CC": clear_cache()
    else: raise ValueError(f"Unknown action: {action!r}")


_pending_timer = None
_pending_lock  = threading.Lock()


def _schedule_action(action):
    global _pending_timer
    with _pending_lock:
        if _pending_timer is not None:
            _pending_timer.cancel()
        _pending_timer = threading.Timer(_CFG.debounce_ms / 1000, _run_action, args=(action,))
        _pending_timer.start()


def _run_action(action):
    global _pending_timer
    with _pending_lock:
        _pending_timer = None
    dispatch(action)


class _CommandHandler(socketserver.StreamRequestHandler):
    timeout = 5

    def handle(self):
        line = self.rfile.readline(256).decode().strip()
        if not line or line not in VALID_ACTIONS:
            self.wfile.write(b"ERROR: invalid action\n")
            return
        self.wfile.write(b"OK\n")
        self.wfile.flush()
        _schedule_action(line)


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


def run_daemon(clear_cache_on_stop=True):
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
        if clear_cache_on_stop:
            clear_cache()
    finally:
        server.shutdown()
        server.server_close()
        _cleanup_runtime_files()


def _fork_daemon(clear_cache_on_stop=True):
    _cleanup_stale_runtime()
    pid = os.fork()
    if pid > 0:
        print(f"winjitsu daemon starting (PID {pid})")
        sys.exit(0)
    os.setsid()
    devnull = open(os.devnull, "r+")
    for fd in (0, 1, 2):
        os.dup2(devnull.fileno(), fd)
    devnull.close()
    run_daemon(clear_cache_on_stop)


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
    U               restore window to its home position
    TF              toggle fullscreen / restore home position

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
        global _CFG
        _CFG = _load_config(Path(pre_args.read_config))

    parser = argparse.ArgumentParser(
        description="Animated window management tool for Linux X11.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=_HELP_EPILOG,
    )
    parser.add_argument("action", nargs="?", choices=VALID_ACTIONS, metavar="ACTION",
                        help="window management action (see below)")
    parser.add_argument("--daemon",         action="store_true", help="start background daemon")
    parser.add_argument("--reload-daemon",  action="store_true", help="restart the background daemon (preserves cache)")
    parser.add_argument("--write-config",   action="store_true", help="create config file with defaults and exit")
    parser.add_argument("--read-config",    metavar="PATH",      help="use a custom config file path")
    parser.add_argument("--see-config",     action="store_true", help="print current config values and exit")
    args = parser.parse_args()

    if args.write_config:
        _write_config(_CFG.path)
        return

    if args.see_config:
        status = "exists" if _CFG.path.exists() else "not found — using defaults"
        print(f"config file : {_CFG.path}  ({status})")
        print(f"steps       : {_CFG.steps}")
        print(f"padding     : {_CFG.padding}")
        print(f"debounce_ms : {_CFG.debounce_ms}")
        return

    if args.daemon:
        _fork_daemon()
        return

    if args.reload_daemon:
        if not PID_PATH.exists():
            print("No daemon running.", file=sys.stderr)
            sys.exit(1)
        try:
            old_pid = int(PID_PATH.read_text().strip())
            os.kill(old_pid, signal.SIGTERM)
        except (ValueError, ProcessLookupError):
            print("No daemon running (stale PID file).", file=sys.stderr)
            PID_PATH.unlink(missing_ok=True)
            sys.exit(1)
        except PermissionError:
            print("Permission denied sending SIGTERM.", file=sys.stderr)
            sys.exit(1)
        for _ in range(50):
            try:
                os.kill(old_pid, 0)
                time.sleep(0.1)
            except ProcessLookupError:
                break
        else:
            print("Daemon did not stop within 5 seconds.", file=sys.stderr)
            sys.exit(1)
        _fork_daemon(clear_cache_on_stop=False)
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
