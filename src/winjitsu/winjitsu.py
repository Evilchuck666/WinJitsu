#!/usr/bin/env python3
import os
import sys
import subprocess
import time
import argparse
import re
from pathlib import Path


# Constants
CACHE_DIR = Path.home() / ".cache" / "winjitsu"

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

def save_pid(window_id, data):
    if not CACHE_DIR.exists():
        CACHE_DIR.mkdir(parents=True)

    pid_file = CACHE_DIR / f"{window_id}.pid"
    # Save in shell variable format to match original, or just JSON?
    # The original uses 'eval "$position"' which implies KEY=VALUE.
    # We can just save the raw data we need.
    with open(pid_file, "w") as f:
        for k, v in data.items():
            f.write(f"{k}={v}\n")

def load_pid(window_id):
    pid_file = CACHE_DIR / f"{window_id}.pid"
    if pid_file.exists():
        data = {}
        with open(pid_file, "r") as f:
            for line in f:
                if "=" in line:
                    k, v = line.strip().split("=", 1)
                    data[k] = int(v)
        return data
    return None

def clear_cache():
    import shutil
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
    save_pid(win['WINDOW'], win)

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

    saved = load_pid(win['WINDOW'])
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

def main():
    parser = argparse.ArgumentParser(description="Window management script")
    parser.add_argument("action", choices=["N", "S", "E", "W", "NE", "NW", "SE", "SW", "C", "F", "U", "TF", "TD", "CC"], help="Action to perform")

    args = parser.parse_args()

    action = args.action

    if action in ["N", "S", "E", "W", "NE", "NW", "SE", "SW", "C"]:
        direction(action)
    elif action == "F":
        fullscreen()
    elif action == "U":
        unscreen()
    elif action == "TF":
        toggle_fullscreen()
    elif action == "TD":
        toggle_display()
    elif action == "CC":
        clear_cache()

if __name__ == "__main__":
    main()
