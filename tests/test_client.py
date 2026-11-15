import io
import os
import shutil
import socket
import tempfile
import threading
import unittest
from contextlib import redirect_stderr
from pathlib    import Path
from unittest   import mock

from winjitsu import client


class _RuntimeDirTestCase(unittest.TestCase):
    def setUp(self):
        # Unix socket paths are limited to 108 bytes: keep the directory short.
        base     = os.environ.get("XDG_RUNTIME_DIR") or "/tmp"
        temp_dir = tempfile.mkdtemp(prefix="wj", dir=base if len(base) < 40 else "/tmp")
        self.addCleanup(shutil.rmtree, temp_dir, True)

        runtime = Path(temp_dir)
        for name, path in {
            "RUNTIME_DIR": runtime,
            "SOCKET_PATH": runtime / "winjitsu.sock",
            "PID_PATH":    runtime / "winjitsu.pid",
            "LOCK_PATH":   runtime / "winjitsu.lock",
        }.items():
            patcher = mock.patch.object(client, name, path)
            patcher.start()
            self.addCleanup(patcher.stop)


class SendCommandTest(_RuntimeDirTestCase):
    def _serve_once(self, reply):
        # A daemon stand-in that reads one action and answers `reply` (None: no answer, b"": just close).
        server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        server.bind(str(client.SOCKET_PATH))
        server.listen(1)
        self.addCleanup(server.close)
        done = threading.Event()
        self.addCleanup(done.set)

        def serve():
            connection, _ = server.accept()
            with connection:
                connection.recv(64)
                if reply is None:
                    done.wait(5)
                else:
                    connection.sendall(reply)

        threading.Thread(target=serve, daemon=True).start()

    def _send(self, action="W"):
        stderr = io.StringIO()
        with redirect_stderr(stderr):
            result = client.send_command(action)
        return result, stderr.getvalue().strip()

    def test_no_socket_means_no_daemon(self):
        self.assertEqual(self._send(), (None, ""))

    def test_stale_socket_means_no_daemon(self):
        stale = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        stale.bind(str(client.SOCKET_PATH))
        stale.close()  # the file stays, nobody listens

        self.assertEqual(self._send(), (None, ""))

    def test_ok_and_warnings_succeed(self):
        self._serve_once(b"WARN: no cached state for this window\n")
        self.assertEqual(self._send(), (True, "no cached state for this window"))

    def test_errors_fail(self):
        self._serve_once(b"ERROR: No active window.\n")
        self.assertEqual(self._send(), (False, "No active window."))

    def test_a_daemon_that_does_not_answer_is_not_reported_as_missing(self):
        self._serve_once(None)
        with mock.patch.object(client, "_CLIENT_TIMEOUT", 0.2):
            self.assertEqual(self._send(), (False, "The WinJitsu daemon did not answer in time."))

    def test_closing_without_answer_fails(self):
        self._serve_once(b"")
        self.assertEqual(self._send(), (False, "The WinJitsu daemon closed the connection without answering."))


class DaemonLockTest(_RuntimeDirTestCase):
    def test_only_one_daemon_can_hold_the_lock(self):
        first = client.acquire_daemon_lock()
        self.addCleanup(first.close)

        self.assertIsNone(client.acquire_daemon_lock())

    def test_running_daemon_is_the_lock_holder(self):
        lock_file = client.acquire_daemon_lock()
        client.PID_PATH.write_text("4242")

        self.assertEqual(client.running_daemon_pid(), 4242)

        lock_file.close()  # the daemon died: the kernel drops its lock
        with mock.patch.object(client, "_is_winjitsu_process", lambda pid: False):
            self.assertIsNone(client.running_daemon_pid(), "a stale PID must not be trusted")

    def test_daemon_from_before_the_lock_is_recognised_by_its_command_line(self):
        client.PID_PATH.write_text("4242")

        with mock.patch.object(client, "_is_winjitsu_process", lambda pid: pid == 4242):
            self.assertEqual(client.running_daemon_pid(), 4242)
        with mock.patch.object(client, "_is_winjitsu_process", lambda pid: False):
            self.assertIsNone(client.running_daemon_pid())

    def test_reads_the_real_command_line(self):
        own_command_line = Path("/proc/self/cmdline").read_bytes()
        self.assertEqual(client._is_winjitsu_process(os.getpid()), b"winjitsu" in own_command_line)
        self.assertFalse(client._is_winjitsu_process(2 ** 22 + 1))  # above pid_max: no such process


if __name__ == "__main__":
    unittest.main()
