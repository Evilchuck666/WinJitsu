import os
import sys
import socket
import socketserver
import signal
import threading

from .config import cfg
from .actions import dispatch, VALID_ACTIONS
from .cache import init_db, clear_cache


_XDG_DATA_HOME = os.environ.get("XDG_DATA_HOME", str(os.path.join(os.path.expanduser("~"), ".local", "share")))

from pathlib import Path
_RUNTIME_DIR = Path(_XDG_DATA_HOME) / "winjitsu"
SOCKET_PATH  = _RUNTIME_DIR / "winjitsu.sock"
PID_PATH     = _RUNTIME_DIR / "winjitsu.pid"


class _Pending:
    __slots__ = ("action", "event", "result")
    def __init__(self, action):
        self.action = action
        self.event  = threading.Event()
        self.result = []  # populated with one string before event is set


_current_pending: "_Pending | None" = None
_pending_timer:   "threading.Timer | None" = None
_pending_lock = threading.Lock()


def _schedule_action(action) -> _Pending:
    # Delay: cancel the previous timer and supersede its waiter with "OK".
    # Only the last action in a rapid burst actually executes.
    global _current_pending, _pending_timer
    pending = _Pending(action)
    with _pending_lock:
        if _pending_timer is not None:
            _pending_timer.cancel()
        if _current_pending is not None:
            _current_pending.result.append("OK")
            _current_pending.event.set()
        _current_pending = pending
        new_timer = threading.Timer(cfg.delay_ms / 1000, _run_action)
        _pending_timer = new_timer
        new_timer.start()
    return pending


def _run_action():
    global _current_pending, _pending_timer
    with _pending_lock:
        pending = _current_pending
        _current_pending = None
        _pending_timer = None
    if pending is None:
        return
    try:
        result = dispatch(pending.action)
        pending.result.append(result if result else "OK")
    except Exception as e:
        pending.result.append(f"ERROR: {e}")
    pending.event.set()


class _CommandHandler(socketserver.StreamRequestHandler):
    timeout = 15

    def handle(self):
        received_action = self.rfile.readline(256).decode().strip()
        if not received_action or received_action not in VALID_ACTIONS:
            self.wfile.write(b"ERROR: invalid action\n")
            return
        pending = _schedule_action(received_action)
        pending.event.wait(timeout=10.0)
        response = pending.result[0] if pending.result else "ERROR: timeout"
        self.wfile.write(f"{response}\n".encode())


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


def run_daemon():
    _RUNTIME_DIR.mkdir(parents=True, exist_ok=True)
    _cleanup_stale_runtime()
    PID_PATH.write_text(str(os.getpid()))
    init_db()
    clear_cache()

    # noinspection PyTypeChecker
    socket_server = socketserver.ThreadingUnixStreamServer(str(SOCKET_PATH), _CommandHandler)
    stop_event    = threading.Event()

    def _on_signal(_signum, _frame):
        stop_event.set()

    signal.signal(signal.SIGTERM, _on_signal)
    signal.signal(signal.SIGINT,  _on_signal)

    threading.Thread(target=socket_server.serve_forever, daemon=True).start()
    stop_event.wait()

    socket_server.shutdown()
    socket_server.server_close()
    _cleanup_runtime_files()


def _fork_daemon():
    _cleanup_stale_runtime()
    child_pid = os.fork()
    if child_pid > 0:
        print(f"winjitsu daemon starting (PID {child_pid})")
        sys.exit(0)
    os.setsid()  # detach from the controlling terminal; become session leader
    # Redirect stdin/stdout/stderr to /dev/null — daemon must not touch the terminal
    devnull_file = open(os.devnull, "r+")
    for fd in (0, 1, 2):
        os.dup2(devnull_file.fileno(), fd)
    devnull_file.close()
    run_daemon()


def send_command(action):
    if not SOCKET_PATH.exists():
        return False
    try:
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as unix_socket:
            unix_socket.settimeout(10.0)
            unix_socket.connect(str(SOCKET_PATH))
            unix_socket.sendall(f"{action}\n".encode())
            with unix_socket.makefile("r") as response_reader:
                response = response_reader.readline().strip()
        if response.startswith("WARN:"):
            print(response[5:].strip(), file=sys.stderr)
        elif response.startswith("ERROR:"):
            print(response[6:].strip(), file=sys.stderr)
            return False
        return True
    except (FileNotFoundError, ConnectionRefusedError, TimeoutError, OSError):
        return False
