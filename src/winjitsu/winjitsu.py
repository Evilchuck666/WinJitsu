#!/usr/bin/env python3
import os
import sys
import subprocess
import time
import argparse
import re
import json
import shutil
import signal
import socket
import socketserver
import threading
from pathlib import Path


# Constants
CACHE_DIR = Path.home() / ".cache" / "winjitsu"

_XDG_DATA_HOME = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share"))
_RUNTIME_DIR   = _XDG_DATA_HOME / "winjitsu"
SOCKET_PATH    = _RUNTIME_DIR / "winjitsu.sock"
PID_PATH       = _RUNTIME_DIR / "winjitsu.pid"

def get_window_position():
    """
    Returns the geometry of the active window.
    """
    try:
        active_window = subprocess.check_output(["xdotool", "getactivewindow"]).decode("utf-8").strip()
        output = subprocess.check_output(["xdotool", "getwindowgeometry", "--shell", active_window]).decode("utf-8")

        data = {}
        for line in output.splitlines():
            key, value = line.split("=", 1)
            data[key] = int(value)

        return data
    except subprocess.CalledProcessError:
        print("Error: Could not get window position. Is xdotool installed?")
        sys.exit(1)

def get_screens():
    """
    Parses xrandr output to find primary and other screens.
    Returns a dictionary with 'primary' and 'others' keys.
    """
    try:
        output = subprocess.check_output(["xrandr"]).decode("utf-8")
    except subprocess.CalledProcessError:
        print("Error: Could not run xrandr.")
        sys.exit(1)

    lines = output.splitlines()
    primary = None
    others = []

    for i, line in enumerate(lines):
        if " connected" in line:
            is_primary = " primary" in line
            # The script logic: get the NEXT line for resolution
            if i + 1 < len(lines):
                res_line = lines[i+1].strip()
                # Expected format: "1920x1080     60.00*+ ..."
                parts = res_line.split()
                if parts:
                    res_str = parts[0] # e.g., 1920x1080
                    if 'x' in res_str:
                        w, h = map(int, res_str.split('x'))

                        # We also need the offset if possible, but the original script
                        # mainly calculates offsets based on primary width for the "other" screen.
                        # The original script logic for 'others' (non-primary):
                        # screen_info=$(xrandr | awk '!/ primary/' | awk '/ connected/{getline; print $1}')
                        # It seems it assumes a simple dual monitor setup where the other is to the right?
                        # Or it calculates x_offset based on primary width.

                        screen_data = {'width': w, 'height': h}

                        if is_primary:
                            primary = screen_data
                        else:
                            others.append(screen_data)

    return primary, others

def get_wm_class(window_id):
    try:
        return subprocess.check_output(
            ["xdotool", "getwindowclassname", str(window_id)]
        ).decode().strip()
    except subprocess.CalledProcessError:
        return None

def save_cache(window_id, data, wm_class):
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    cache_file = CACHE_DIR / f"{window_id}.json"
    with open(cache_file, "w") as f:
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

def move_window(target_w, target_h, window_id, current_w, current_h, current_x, current_y, target_x, target_y):
    steps = 25

    # Calculate steps
    w_step = (target_w - current_w) / steps
    h_step = (target_h - current_h) / steps

    x_move_step = (current_x - target_x) / steps
    y_move_step = (current_y - target_y) / steps

    # Initial values
    new_w = current_w
    new_h = current_h
    new_x = current_x
    new_y = current_y

    # The original script logic for x_move_step seems to be subtraction:
    # new_x = X - x_move_step
    # x_move_step = (X - x_offset) / steps
    # So if X=100, target=0. step = 100/25 = 4.
    # new_x = 100 - 4 = 96. Correct.

    for _ in range(steps):
        new_w += w_step
        new_h += h_step
        new_x -= x_move_step
        new_y -= y_move_step

        subprocess.run(["xdotool", "windowsize", str(window_id), str(round(new_w)), str(round(new_h))])
        subprocess.run(["xdotool", "windowmove", str(window_id), str(round(new_x)), str(round(new_y))])

    subprocess.run(["xdotool", "windowsize", str(window_id), str(int(target_w)), str(int(target_h))])
    subprocess.run(["xdotool", "windowmove", str(window_id), str(int(target_x)), str(int(target_y))])


def get_primary_width():
    primary, _ = get_screens()
    if primary:
        return primary['width']
    return 1920 # Fallback

def get_screen_for_window(x_pos):
    """
    Determines which screen the window is on based on X position.
    Returns (width, height, x_offset_base)
    """
    primary, others = get_screens()
    if not primary:
        # Fallback
        return 1920, 1080, 0

    primary_width = primary['width']

    # Logic from script: if ((X > primary_width - 1)); then ...
    if x_pos > primary_width - 1:
        # On secondary screen
        if others:
            # Assuming the first other screen
            other = others[0]
            return other['width'], other['height'], primary_width
        else:
            # Fallback if no other screen found but X is large
            return primary_width, primary['height'], 0
    else:
        # On primary screen
        return primary_width, primary['height'], 0

# Actions

def fullscreen():
    win = get_window_position()
    save_cache(win['WINDOW'], win, get_wm_class(win['WINDOW']))

    screen_w, screen_h, base_x_offset = get_screen_for_window(win['X'])

    # Logic from script:
    # if on secondary: x_offset = primary_width + 5
    # else: x_offset = 5

    if base_x_offset > 0:
        x_offset = base_x_offset + 5
    else:
        x_offset = 5

    y_offset = 5

    target_w = screen_w - 10
    target_h = screen_h - 10

    move_window(target_w, target_h, win['WINDOW'], win['WIDTH'], win['HEIGHT'], win['X'], win['Y'], x_offset, y_offset)

def unscreen():
    win = get_window_position()

    # Logic from script:
    screen_w, screen_h, base_x_offset = get_screen_for_window(win['X'])

    if base_x_offset > 0:
        x_offset = base_x_offset
    else:
        x_offset = 5

    y_offset = 5

    # Original script calculates screen_width/height based on current WIDTH/HEIGHT - 10?
    # No, wait:
    # screen_width=$((WIDTH - 10));
    # screen_height=$((HEIGHT - 10));
    # load_pid;
    # move_window "$WIDTH" "$HEIGHT" "$WINDOW" "$screen_width" "$screen_height" "$x_offset" "$y_offset" "$X" "$Y";

    # It seems 'unscreen' restores the window.
    # 'load_pid' overwrites WIDTH, HEIGHT, X, Y with stored values.
    # The 'move_window' call in 'unscreen' seems to swap arguments?
    # move_window "$WIDTH" "$HEIGHT" "$WINDOW" "$screen_width" "$screen_height" "$x_offset" "$y_offset" "$X" "$Y";
    # definition: move_window screen_width screen_height WINDOW WIDTH HEIGHT X Y x_offset y_offset
    # So:
    # target_w = stored WIDTH
    # target_h = stored HEIGHT
    # current_w = screen_width (calculated from current WIDTH - 10? This seems odd in the script)
    # current_h = screen_height
    # current_x = x_offset (calculated)
    # current_y = y_offset
    # target_x = stored X
    # target_y = stored Y

    saved = load_cache(win['WINDOW'], get_wm_class(win['WINDOW']))
    if saved:
        target_w = saved['WIDTH']
        target_h = saved['HEIGHT']
        target_x = saved['X']
        target_y = saved['Y']

        # The script uses current WIDTH-10 as the 'start' width for animation?
        # If it was fullscreen, WIDTH is screen_width-10.
        # So WIDTH-10 is (screen_width-10)-10?
        # Let's stick to the script's logic literally.

        start_w = win['WIDTH'] - 10
        start_h = win['HEIGHT'] - 10

        # x_offset calculation in script:
        # if secondary: x_offset = primary_width
        # else: x_offset = 5

        move_window(target_w, target_h, win['WINDOW'], start_w, start_h, x_offset, y_offset, target_x, target_y)

def toggle_fullscreen():
    win = get_window_position()
    screen_w, _, _ = get_screen_for_window(win['X'])

    # screen_width=$((screen_width - 10));
    # if ((WIDTH == screen_width)); then unscreen; else fullscreen; fi

    if win['WIDTH'] == (screen_w - 10):
        unscreen()
    else:
        fullscreen()

def direction(direction_code):
    win = get_window_position()
    screen_w, screen_h, base_x_offset = get_screen_for_window(win['X'])

    # Common logic
    half_w = screen_w / 2
    half_h = screen_h / 2

    target_w = win['WIDTH']
    target_h = win['HEIGHT']
    target_x = 0
    target_y = 0

    # Determine target geometry based on direction
    if direction_code == "N":
        target_w = screen_w
        target_h = half_h
        target_x = base_x_offset
        target_y = 0

    elif direction_code == "S":
        target_w = screen_w
        target_h = half_h
        target_x = base_x_offset
        target_y = half_h

    elif direction_code == "E":
        target_w = half_w
        target_h = screen_h
        target_x = base_x_offset + half_w
        target_y = 0

    elif direction_code == "W":
        target_w = half_w
        target_h = screen_h
        target_x = base_x_offset
        target_y = 0

    elif direction_code == "NE":
        target_w = half_w
        target_h = half_h
        target_x = base_x_offset + half_w
        target_y = 0

    elif direction_code == "NW":
        target_w = half_w
        target_h = half_h
        target_x = base_x_offset
        target_y = 0

    elif direction_code == "SE":
        target_w = half_w
        target_h = half_h
        target_x = base_x_offset + half_w
        target_y = half_h

    elif direction_code == "SW":
        target_w = half_w
        target_h = half_h
        target_x = base_x_offset
        target_y = half_h

    elif direction_code == "C":
        # Center
        # x_offset=$(bc -l <<< "scale=3; ($screen_width - $WIDTH) / 2 + $x_offset");
        # y_offset=$(bc -l <<< "scale=3; ($screen_height - $HEIGHT) / 2");
        target_w = win['WIDTH']
        target_h = win['HEIGHT']
        target_x = (screen_w - win['WIDTH']) / 2 + base_x_offset
        target_y = (screen_h - win['HEIGHT']) / 2

    move_window(target_w, target_h, win['WINDOW'], win['WIDTH'], win['HEIGHT'], win['X'], win['Y'], target_x, target_y)

def toggle_display():
    win = get_window_position()
    primary, _ = get_screens()
    if not primary:
        return

    primary_width = primary['width']

    # if ((X > primary_width - 1)); then primary_width=$((-primary_width)); fi
    # x_offset=$((X + primary_width));

    if win['X'] > primary_width - 1:
        shift = -primary_width
    else:
        shift = primary_width

    target_x = win['X'] + shift

    move_window(win['WIDTH'], win['HEIGHT'], win['WINDOW'], win['WIDTH'], win['HEIGHT'], win['X'], win['Y'], target_x, win['Y'])

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

    server = socketserver.ThreadingUnixStreamServer(str(SOCKET_PATH), _CommandHandler)

    stop_event = threading.Event()

    def _on_signal(signum, frame):
        stop_event.set()

    signal.signal(signal.SIGTERM, _on_signal)
    signal.signal(signal.SIGINT,  _on_signal)

    server_thread = threading.Thread(target=server.serve_forever, daemon=True)
    server_thread.start()

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


def main():
    parser = argparse.ArgumentParser(description="Window management tool")
    parser.add_argument("action", nargs="?", choices=VALID_ACTIONS, help="Action to perform")
    parser.add_argument("--daemon", action="store_true", help="Start background daemon")
    args = parser.parse_args()

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

    if not send_command(args.action):
        dispatch(args.action)


if __name__ == "__main__":
    main()
