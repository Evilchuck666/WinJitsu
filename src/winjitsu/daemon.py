import os
import sys
import socket
import socketserver
import signal
import threading

from .config import _CFG
from .actions import dispatch, VALID_ACTIONS
from .cache import clear_cache


_XDG_DATA_HOME = os.environ.get("XDG_DATA_HOME", str(os.path.join(os.path.expanduser("~"), ".local", "share")))

from pathlib import Path
_RUNTIME_DIR = Path(_XDG_DATA_HOME) / "winjitsu"
SOCKET_PATH  = _RUNTIME_DIR / "winjitsu.sock"
PID_PATH     = _RUNTIME_DIR / "winjitsu.pid"


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
        received_action = self.rfile.readline(256).decode().strip()
        if not received_action or received_action not in VALID_ACTIONS:
            self.wfile.write(b"ERROR: invalid action\n")
            return
        self.wfile.write(b"OK\n")
        self.wfile.flush()
        _schedule_action(received_action)


def _cleanup_stale_runtime():
    if PID_PATH.exists():
        try:
            stored_pid = int(PID_PATH.read_text().strip())
            os.kill(stored_pid, 0)
            print(f"winjitsu daemon already running (PID {stored_pid})", file=sys.stderr)
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
