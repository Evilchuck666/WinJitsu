import os
import sys
import argparse
import signal
import time
from pathlib import Path

from .config import _load_config, _write_config
from .actions import VALID_ACTIONS
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

    # Pre-parse --read-config before the main parser, so globals are updated
    # before any action uses them.
    pre_parser = argparse.ArgumentParser(add_help=False)
    pre_parser.add_argument("--read-config", metavar="PATH")
    pre_parsed_args, _ = pre_parser.parse_known_args()
    if pre_parsed_args.read_config:
        _config_module.cfg = _load_config(Path(pre_parsed_args.read_config))

    parser = argparse.ArgumentParser(
        description="Animated window management tool for Linux X11.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=_HELP_EPILOG,
    )
    parser.add_argument("action", nargs="?", choices=VALID_ACTIONS, metavar="ACTION",
                        help="window management action (see below)")
    parser.add_argument("--daemon",         action="store_true",    help="start background daemon")
    parser.add_argument("--reload-daemon",  action="store_true",    help="restart the background daemon")
    parser.add_argument("--write-config",   action="store_true",    help="create config file with defaults and exit")
    parser.add_argument("--read-config",    metavar="PATH",         help="use a custom config file path")
    parser.add_argument("--see-config",     action="store_true",    help="print current config values and exit")
    parser.add_argument("--steps",          type=int, metavar="N",  help="animation steps, overrides config (default: 25)")
    parser.add_argument("--padding",        type=int, metavar="PX", help="fullscreen padding in pixels, overrides config (default: 0)")
    parser.add_argument("--delay-ms",       type=int, metavar="MS", help="action delay in milliseconds, overrides config (default: 250)")
    parsed_args = parser.parse_args()

    config = _config_module.cfg

    # CLI flags override config file and defaults
    if parsed_args.steps    is not None: config.steps    = parsed_args.steps
    if parsed_args.padding  is not None: config.padding  = parsed_args.padding
    if parsed_args.delay_ms is not None: config.delay_ms = parsed_args.delay_ms

    if parsed_args.write_config:
        _write_config(config.path, config)
        return

    if parsed_args.see_config:
        status = "exists" if config.path.exists() else "not found — using defaults"
        print(f"config file : {config.path}  ({status})")
        print(f"steps       : {config.steps}")
        print(f"padding     : {config.padding}")
        print(f"delay_ms    : {config.delay_ms}")
        return

    if parsed_args.daemon:
        _fork_daemon()
        return

    if parsed_args.reload_daemon:
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
        for _ in range(50):  # poll up to 5 s (50 × 0.1 s)
            try:
                os.kill(old_pid, 0)  # signal 0: liveness check, no signal sent
                time.sleep(0.1)
            except ProcessLookupError:
                break
        else:
            # loop completed without break — daemon did not stop in time
            print("Daemon did not stop within 5 seconds.", file=sys.stderr)
            sys.exit(1)
        _fork_daemon()
        return

    if parsed_args.action is None:
        parser.print_help()
        sys.exit(1)

    if not send_command(parsed_args.action):
        print("Error: WinJitsu daemon is not running. Start it with: winjitsu --daemon", file=sys.stderr)
        sys.exit(1)
