import os
import sys
import time
import queue
import signal
import logging
import threading
import socketserver
from logging.handlers import RotatingFileHandler

from Xlib import error as xerror

from .         import __version__
from .config   import cfg
from .actions  import dispatch
from .cache    import init_db, clear_cache, CACHE_ERRORS
from .screen   import reset_display
from .client   import (
    VALID_ACTIONS, SOCKET_PATH, PID_PATH, LOG_PATH, ACTION_TIMEOUT,
    acquire_daemon_lock, legacy_daemon_pid, running_daemon_pid,
)


log = logging.getLogger("winjitsu")

# Exit status of a daemon that found another one running, so `--daemon` can say so.
_ALREADY_RUNNING_EXIT = 3
_STARTUP_TIMEOUT      = 3.0

# What python-xlib raises once the X server has closed the connection.
_X_CONNECTION_ERRORS = (xerror.ConnectionClosedError, ConnectionError)


class _Pending:
    __slots__ = ("action", "event", "result", "cancelled")
    def __init__(self, action):
        self.action    = action
        self.event     = threading.Event()
        self.result    = []  # populated with one string before event is set
        self.cancelled = False


_current_pending: "_Pending | None" = None   # last action of the burst in progress
_pending_timer:   "threading.Timer | None" = None
_burst_first:     "str | None" = None         # the action that started that burst
_last_request  = float("-inf")                # time.monotonic() of the last action received
_pending_lock  = threading.Lock()
_action_queue: "queue.Queue[_Pending]" = queue.Queue()


def _schedule_action(action) -> _Pending:
    # The first action after a quiet period runs at once. Actions arriving
    # within delay_ms of the previous one form a burst: only the last runs, when
    # the burst is over, and not at all if it repeats the first one, so holding
    # a key down still makes a single move. Superseded callers get "OK".
    global _current_pending, _pending_timer, _burst_first, _last_request

    pending = _Pending(action)
    delay   = cfg.delay_ms / 1000
    now     = time.monotonic()

    with _pending_lock:
        in_burst      = now - _last_request < delay
        _last_request = now

        if _pending_timer is not None:
            _pending_timer.cancel()
            _pending_timer = None

        if _current_pending is not None:
            _current_pending.result.append("OK")
            _current_pending.event.set()
            _current_pending = None

        if in_burst:
            _current_pending = pending
            _pending_timer   = threading.Timer(delay, _end_burst)
            _pending_timer.start()
        else:
            _burst_first = action
            _action_queue.put(pending)

    return pending


def _end_burst():
    # Timer callback: the burst is over, hand its last action to the worker.
    global _current_pending, _pending_timer

    with _pending_lock:
        pending          = _current_pending
        first            = _burst_first
        _current_pending = None
        _pending_timer   = None

    if pending is None:
        return

    if pending.action == first:
        pending.result.append("OK")
        pending.event.set()
        return

    _action_queue.put(pending)


def _action_worker():
    # The only thread that runs actions: one at a time and in arrival order, so
    # an action never starts while the previous animation is still moving the
    # window, and the shared X connection is never used from two threads.
    while True:
        _run_action(_action_queue.get())


def _dispatch(action):
    # A closed X connection (server restarted, connection dropped) stays closed:
    # drop it and try once more with a new one.
    try:
        return dispatch(action)
    except _X_CONNECTION_ERRORS as error:
        log.warning("X connection lost (%s), reconnecting", error)
        reset_display()

    try:
        return dispatch(action)
    except _X_CONNECTION_ERRORS:
        reset_display()
        raise


def _run_action(pending):
    if pending.cancelled:
        return

    try:
        result = _dispatch(pending.action)
        if result:
            log.warning("%s: %s", pending.action, result)
        pending.result.append(result if result else "OK")
    except Exception as error:
        log.exception("%s failed", pending.action)
        pending.result.append(f"ERROR: {error}")

    pending.event.set()


class _CommandHandler(socketserver.StreamRequestHandler):
    timeout = 15

    def handle(self):
        received_action = self.rfile.readline(256).decode(errors="replace").strip()

        if not received_action or received_action not in VALID_ACTIONS:
            self.wfile.write(b"ERROR: invalid action\n")
            return

        pending = _schedule_action(received_action)

        if not pending.event.wait(timeout=cfg.delay_ms / 1000 + ACTION_TIMEOUT):
            pending.cancelled = True
            log.error("%s did not finish within %s s", received_action, ACTION_TIMEOUT)
            self.wfile.write(b"ERROR: the action did not finish in time\n")
            return

        self.wfile.write(f"{pending.result[0]}\n".encode())


def _setup_logging(foreground):
    formatter = logging.Formatter("%(asctime)s %(levelname)s %(message)s")
    handlers  = []

    try:
        LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        handlers.append(RotatingFileHandler(LOG_PATH, maxBytes=256 * 1024, backupCount=1))
    except OSError as error:
        print(f"winjitsu: cannot write the log file {LOG_PATH}: {error}", file=sys.stderr)

    if foreground:
        handlers.append(logging.StreamHandler())

    for handler in handlers:
        handler.setFormatter(formatter)
        log.addHandler(handler)
    log.setLevel(logging.INFO)

    def _log_uncaught(args):
        thread_name = args.thread.name if args.thread else "unknown thread"
        log.error("Uncaught exception in %s", thread_name, exc_info=(args.exc_type, args.exc_value, args.exc_traceback))

    threading.excepthook = _log_uncaught


def run_daemon(foreground=True):
    lock_file = acquire_daemon_lock()
    legacy    = legacy_daemon_pid()

    if lock_file is None or legacy is not None:
        print("winjitsu daemon already running", file=sys.stderr)
        sys.exit(_ALREADY_RUNNING_EXIT)

    _setup_logging(foreground)

    # Holding the lock means no other daemon uses these: they are leftovers.
    SOCKET_PATH.unlink(missing_ok=True)
    PID_PATH.write_text(str(os.getpid()))

    try:
        init_db()
        clear_cache()
    except CACHE_ERRORS as error:
        log.warning("window state database unavailable: %s", error)

    # noinspection PyTypeChecker
    socket_server = socketserver.ThreadingUnixStreamServer(str(SOCKET_PATH), _CommandHandler)
    os.chmod(SOCKET_PATH, 0o600)
    stop_event    = threading.Event()

    def _on_signal(_signum, _frame):
        stop_event.set()

    signal.signal(signal.SIGTERM, _on_signal)
    signal.signal(signal.SIGINT,  _on_signal)

    threading.Thread(target=_action_worker, name="actions", daemon=True).start()
    threading.Thread(target=socket_server.serve_forever, name="socket", daemon=True).start()
    log.info("winjitsu %s daemon started (PID %d, steps=%d, padding=%d, delay_ms=%d)",
             __version__, os.getpid(), cfg.steps, cfg.padding, cfg.delay_ms)
    stop_event.wait()

    socket_server.shutdown()
    socket_server.server_close()
    SOCKET_PATH.unlink(missing_ok=True)
    PID_PATH.unlink(missing_ok=True)
    log.info("daemon stopped")
    lock_file.close()


def _report_startup(child_pid):
    # Wait until the daemon listens (or gives up), so the message is true and
    # an action sent right after `winjitsu --daemon` finds the socket.
    deadline = time.monotonic() + _STARTUP_TIMEOUT

    while time.monotonic() < deadline:
        finished_pid, status = os.waitpid(child_pid, os.WNOHANG)

        if finished_pid:
            if os.waitstatus_to_exitcode(status) == _ALREADY_RUNNING_EXIT:
                print(f"winjitsu daemon already running (PID {running_daemon_pid()})", file=sys.stderr)
            else:
                print(f"winjitsu daemon failed to start, see {LOG_PATH}", file=sys.stderr)
            sys.exit(1)

        if SOCKET_PATH.exists() and _pid_file_says(child_pid):
            print(f"winjitsu daemon started (PID {child_pid})")
            sys.exit(0)

        time.sleep(0.05)

    print(f"winjitsu daemon starting (PID {child_pid})")
    sys.exit(0)


def _pid_file_says(pid):
    try:
        return int(PID_PATH.read_text().strip()) == pid
    except (OSError, ValueError):
        return False


def _fork_daemon():
    running_pid = running_daemon_pid()
    if running_pid is not None:
        print(f"winjitsu daemon already running (PID {running_pid})", file=sys.stderr)
        sys.exit(1)

    child_pid = os.fork()

    if child_pid > 0:
        _report_startup(child_pid)

    # detach from the controlling terminal; become session leader
    os.setsid()

    # Redirect stdin/stdout/stderr to /dev/null — daemon must not touch the
    # terminal. Errors go to the log file.
    devnull_file = open(os.devnull, "r+")

    for fd in (0, 1, 2):
        os.dup2(devnull_file.fileno(), fd)

    devnull_file.close()
    run_daemon(foreground=False)
