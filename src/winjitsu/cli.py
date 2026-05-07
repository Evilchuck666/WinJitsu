import os
import sys
import argparse
import signal
import time
from pathlib import Path

from .config import _CFG, _load_config, _write_config
from .actions import dispatch, VALID_ACTIONS
from .daemon import _fork_daemon, send_command, PID_PATH


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
    import winjitsu.config as _config_module

    # Pre-parse --read-config before the main parser so globals are updated
    # before any action uses them.
    pre = argparse.ArgumentParser(add_help=False)
    pre.add_argument("--read-config", metavar="PATH")
    pre_args, _ = pre.parse_known_args()
    if pre_args.read_config:
        _config_module._CFG = _load_config(Path(pre_args.read_config))

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

    cfg = _config_module._CFG

    if args.write_config:
        _write_config(cfg.path)
        return

    if args.see_config:
        status = "exists" if cfg.path.exists() else "not found — using defaults"
        print(f"config file : {cfg.path}  ({status})")
        print(f"steps       : {cfg.steps}")
        print(f"padding     : {cfg.padding}")
        print(f"debounce_ms : {cfg.debounce_ms}")
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
