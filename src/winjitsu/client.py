"""What the winjitsu command needs to reach the daemon.

Kept free of X imports so sending an action from a hotkey starts fast; the
daemon side lives in daemon.py.
"""
import fcntl
import os
import socket
import sys
from pathlib import Path

from .config import _xdg_dir


VALID_ACTIONS = ["N", "S", "E", "W", "NE", "NW", "SE", "SW", "C", "F", "U", "TF", "TD", "CC"]

RUNTIME_DIR = Path(os.environ.get("XDG_RUNTIME_DIR") or f"/run/user/{os.getuid()}") / "winjitsu"
SOCKET_PATH = RUNTIME_DIR / "winjitsu.sock"
PID_PATH    = RUNTIME_DIR / "winjitsu.pid"
LOCK_PATH   = RUNTIME_DIR / "winjitsu.lock"
LOG_PATH    = _xdg_dir("XDG_STATE_HOME", ".local/state") / "winjitsu" / "daemon.log"

# The daemon answers within its delay (at most 5 s) plus ACTION_TIMEOUT. The
# client waits longer, so it gets that answer instead of timing out first.
ACTION_TIMEOUT  = 20
_CLIENT_TIMEOUT = ACTION_TIMEOUT + 10


def send_command(action):
    """True: done (warnings printed). False: failed (reason printed). None: no daemon is listening."""
    try:
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as unix_socket:
            unix_socket.settimeout(_CLIENT_TIMEOUT)
            unix_socket.connect(str(SOCKET_PATH))
            unix_socket.sendall(f"{action}\n".encode())

            with unix_socket.makefile("r") as response_reader:
                response = response_reader.readline().strip()
    except (FileNotFoundError, ConnectionRefusedError):
        return None
    except TimeoutError:
        print("The WinJitsu daemon did not answer in time.", file=sys.stderr)
        return False
    except OSError as error:
        print(f"Could not talk to the WinJitsu daemon: {error}", file=sys.stderr)
        return False

    if not response:
        print("The WinJitsu daemon closed the connection without answering.", file=sys.stderr)
        return False

    if response.startswith("WARN:"):
        print(response[5:].strip(), file=sys.stderr)
    elif response.startswith("ERROR:"):
        print(response[6:].strip(), file=sys.stderr)
        return False

    return True


# --- Which daemon is running ------------------------------------------------
# The daemon holds an exclusive flock on LOCK_PATH while it runs. The kernel
# drops it when the process dies, so unlike a PID file it can't go stale or
# point at an unrelated process that got the same PID.

def acquire_daemon_lock():
    """Lock LOCK_PATH for this process: the returned file must stay open while the daemon runs.

    None if another daemon holds it.
    """
    RUNTIME_DIR.mkdir(parents=True, exist_ok=True)
    lock_file = open(LOCK_PATH, "a")

    try:
        fcntl.flock(lock_file, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        lock_file.close()
        return None

    return lock_file


def _lock_is_held():
    if not LOCK_PATH.exists():
        return False

    with open(LOCK_PATH, "a") as lock_file:
        try:
            fcntl.flock(lock_file, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            return True

        fcntl.flock(lock_file, fcntl.LOCK_UN)
        return False


def _read_pid():
    try:
        return int(PID_PATH.read_text().strip())
    except (OSError, ValueError):
        return None


def _is_winjitsu_process(pid):
    try:
        return b"winjitsu" in Path(f"/proc/{pid}/cmdline").read_bytes()
    except OSError:
        return False


def legacy_daemon_pid():
    """PID of a daemon from a version without the lock file, still running, or None."""
    pid = _read_pid()
    if pid is not None and pid != os.getpid() and _is_winjitsu_process(pid):
        return pid

    return None


def running_daemon_pid():
    """PID of the running daemon, or None. Never the PID of an unrelated process."""
    if _lock_is_held():
        return _read_pid()

    return legacy_daemon_pid()
