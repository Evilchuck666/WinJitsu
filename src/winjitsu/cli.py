import os
import sys
import argparse
import signal
import time
from pathlib  import Path
from .config  import _load_config, _write_config, validate
from .client  import VALID_ACTIONS, LOG_PATH, send_command, running_daemon_pid

# daemon.py (and python-xlib with it) is imported only by --daemon and
# --reload-daemon, so sending an action from a hotkey starts fast.


_HELP_EPILOG = """
actions:
  grid snapping:
    N / S           snap to top / bottom half of the screen
    E / W           snap to right / left half of the screen
    NE / NW         snap to top-right / top-left quarter
    SE / SW         snap to bottom-right / bottom-left quarter
    C               center window (keeps current size)

  fullscreen:
    F               fullscreen (the monitor minus panels and padding)
    U               undo the last action on the window (repeat to go further back)
    TF              toggle fullscreen (leaving it undoes the move into it)

  multi-monitor:
    TD              move window to the next monitor

  cache:
    CC              clear the undo history of every window

config file: ~/.config/winjitsu/config.ini  (XDG_CONFIG_HOME honoured)
  --write-config    write the current settings (defaults, config file and flags) to it
  --read-config     use a different config file path
  --see-config      show active config file and current values
"""


def _option_type(option):
    def parse(value):
        try:
            return validate(option, value)
        except ValueError as error:
            raise argparse.ArgumentTypeError(str(error)) from None

    return parse


def _wait_for_daemon_exit(timeout=5.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if running_daemon_pid() is None:
            return True
        time.sleep(0.1)

    return False


def main():
    import winjitsu.config as _config_module

    # Pre-parse --read-config before the main parser, so globals are updated
    # before any action uses them.
    pre_parser = argparse.ArgumentParser(add_help=False)
    pre_parser.add_argument("--read-config", metavar="PATH")
    pre_parsed_args, _ = pre_parser.parse_known_args()

    if pre_parsed_args.read_config:
        new_cfg = _load_config(Path(pre_parsed_args.read_config))
        _config_module.cfg.steps    = new_cfg.steps
        _config_module.cfg.padding  = new_cfg.padding
        _config_module.cfg.delay_ms = new_cfg.delay_ms
        _config_module.cfg.path     = new_cfg.path

    parser = argparse.ArgumentParser(
        description="Animated window management tool for Linux X11.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=_HELP_EPILOG,
    )
    parser.add_argument("action", nargs="?", choices=VALID_ACTIONS, metavar="ACTION", help="window management action (see below)")
    parser.add_argument("--daemon",         action="store_true",                      help="start background daemon")
    parser.add_argument("--reload-daemon",  action="store_true",                      help="restart the background daemon")
    parser.add_argument("--write-config",   action="store_true",                      help="write the current settings to the config file and exit")
    parser.add_argument("--read-config",    metavar="PATH",                           help="use a custom config file path")
    parser.add_argument("--see-config",     action="store_true",                      help="print current config values and exit")
    parser.add_argument("--steps",    type=_option_type("steps"),    metavar="N",  help="animation steps for --daemon, overrides config (1-1000, default: 25)")
    parser.add_argument("--padding",  type=_option_type("padding"),  metavar="PX", help="fullscreen padding in pixels for --daemon, overrides config (0-500, default: 0)")
    parser.add_argument("--delay-ms", type=_option_type("delay_ms"), metavar="MS", help="debounce delay in milliseconds for --daemon, overrides config (0-5000, default: 250)")
    parsed_args = parser.parse_args()

    config = _config_module.cfg

    # CLI flags override config file and defaults
    if parsed_args.steps    is not None:
        config.steps    = parsed_args.steps

    if parsed_args.padding  is not None:
        config.padding  = parsed_args.padding

    if parsed_args.delay_ms is not None:
        config.delay_ms = parsed_args.delay_ms

    if parsed_args.write_config:
        _write_config(config.path, config)
        return

    if parsed_args.see_config:
        status = "exists" if config.path.exists() else "not found — using defaults"
        print(f"config file : {config.path}  ({status})")
        print(f"steps       : {config.steps}")
        print(f"padding     : {config.padding}")
        print(f"delay_ms    : {config.delay_ms}")
        print(f"daemon log  : {LOG_PATH}")
        return

    if parsed_args.daemon:
        from .daemon import _fork_daemon
        _fork_daemon()
        return

    if parsed_args.reload_daemon:
        from .daemon import _fork_daemon

        # Only a PID confirmed to be the daemon gets the signal, never a stale
        # PID reused by another process.
        old_pid = running_daemon_pid()
        if old_pid is None:
            print("No daemon running.", file=sys.stderr)
            sys.exit(1)

        try:
            os.kill(old_pid, signal.SIGTERM)
        except ProcessLookupError:
            pass  # it stopped in the meantime
        except PermissionError:
            print("Permission denied sending SIGTERM.", file=sys.stderr)
            sys.exit(1)

        if not _wait_for_daemon_exit():
            print("Daemon did not stop within 5 seconds.", file=sys.stderr)
            sys.exit(1)

        _fork_daemon()
        return

    if parsed_args.action is None:
        parser.print_help()
        sys.exit(1)

    sent = send_command(parsed_args.action)

    if sent is None:
        print("Error: WinJitsu daemon is not running. Start it with: winjitsu --daemon", file=sys.stderr)
        sys.exit(1)

    if not sent:
        sys.exit(1)
