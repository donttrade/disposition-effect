"""Tester E16 (LOW): one way to run dt-private's local Worker (`scripts/rehearse.mjs --serve`, node + workerd) from a
test, so it never outlives the test: its own process group (start_new_session), --exit-with-stdin (it stops when
our end of the pipe closes, even if this process is killed), stderr to a file (a full pipe could block it), and a
stop() that closes stdin, sends SIGTERM, waits, then kills the whole group. An atexit hook stops any left running.
stop() returns the workerd pids that were its children and are still alive (none, when it works)."""
import atexit
import json
import os
import signal
import subprocess
import tempfile
import time

_RUNNING = set()


def _children(pid):
    r = subprocess.run(["pgrep", "-P", str(pid)], capture_output=True, text=True)
    return [int(x) for x in r.stdout.split()]


def _alive(pid):
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        return True


class ServeWorker:
    def __init__(self, private, origins, omit=()):
        cmd = ["node", "--no-warnings", "scripts/rehearse.mjs", "--serve", "--exit-with-stdin", "--origins", ",".join(origins)]
        for o in omit:
            cmd += ["--omit", o]
        self.err = tempfile.TemporaryFile(mode="w+")
        self.p = subprocess.Popen(cmd, cwd=private, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=self.err, text=True,
                                  start_new_session=True)
        _RUNNING.add(self)
        line = self.p.stdout.readline()
        if not line.startswith("{"):
            self.stop()
            self.err.seek(0)
            raise AssertionError("rehearse --serve did not start: " + line + self.err.read())
        self.info = json.loads(line)
        self.api = self.info["api"]
        self.children = []
        for _ in range(100):   # workerd starts before the line is printed; read its pid for the leak check
            self.children = _children(self.p.pid)
            if self.children:
                break
            time.sleep(0.05)

    def poll(self):
        return self.p.poll()

    def stop(self):
        if self not in _RUNNING:
            return []
        _RUNNING.discard(self)
        try:
            self.p.stdin.close()
        except OSError:
            pass
        if self.p.poll() is None:
            self.p.terminate()
        try:
            self.p.wait(timeout=15)
        except subprocess.TimeoutExpired:
            pass
        try:
            os.killpg(self.p.pid, signal.SIGKILL)   # the whole group: node and workerd, whatever is left
        except ProcessLookupError:
            pass
        try:
            self.p.wait(timeout=5)
        except subprocess.TimeoutExpired:
            pass
        end = time.time() + 5
        while time.time() < end and any(_alive(c) for c in self.children):
            time.sleep(0.1)
        return [c for c in self.children if _alive(c)]


@atexit.register
def _stop_all():
    for w in list(_RUNNING):
        w.stop()
