"""Running the pictures in several processes, so they use several CPU cores.

Python runs only one thread of Python code at a time, so one process can
only ever keep one core busy. Instead, each worker is a separate process
with its own share of the pictures, its own see-through layers on every
monitor, its own physics and its own drawing, and Windows spreads the
workers across the cores. The main process plays the video and keeps count
of how many pictures every worker still has open.

Workers never outlive the main process: they sit in a Windows job object
that kills them when it goes, and they also stop when its pipe closes.
A worker that crashes is started again, so pictures cannot be got rid of
that way either.
"""

from __future__ import annotations

import multiprocessing as mp
import os
import random
import sys
from pathlib import Path

from PySide6.QtCore import QObject, QTimer, Signal

POLL_MS = 50


def default_count() -> int:
    """Half the logical cores (the other half is left for the video and the
    rest of the PC), at least 1, at most 4."""
    return max(1, min(4, (os.cpu_count() or 2) // 2))


def split(sources: list[Path], count: int, rng: random.Random) -> list[list[Path]]:
    """Deal *sources* out like cards into *count* shares."""
    shuffled = sources[:]
    rng.shuffle(shuffled)
    return [shuffled[i::count] for i in range(count)]


# --- inside a worker process --------------------------------------------------
def worker_main(conn, sources: list[Path], first: list[Path], seed: float) -> None:
    os.environ.setdefault("QT_LOGGING_RULES", "qt.multimedia*=false")
    import signal

    signal.signal(signal.SIGINT, signal.SIG_DFL)
    if sys.platform == "win32":
        import ctypes

        ctypes.windll.kernel32.SetConsoleCtrlHandler(None, False)

    from PySide6.QtGui import QKeySequence, QShortcut
    from PySide6.QtWidgets import QApplication

    from .killswitch import HOTKEY_TEXT
    from .swarm import Swarm

    app = QApplication([sys.argv[0]])
    swarm = Swarm(sources, rng=random.Random(seed), first=first)
    last_status = None

    def stop() -> None:
        swarm.shutdown()
        app.exit(0)

    def send(message) -> None:
        try:
            conn.send(message)
        except (OSError, EOFError):
            stop()

    def poll() -> None:
        nonlocal last_status
        try:
            while conn.poll():
                message = conn.recv()
                if message == "raise":
                    swarm.raise_()
                elif message == "quit":
                    stop()
                    return
        except (OSError, EOFError):  # the main process is gone
            stop()
            return
        status = ("status", swarm.open_count, swarm.all_closed(), swarm.frames)
        if status[:3] != (last_status or (None,) * 3)[:3] or swarm.frames - last_status[3] >= 60:
            last_status = status
            send(status)

    for overlay in swarm.overlays.values():
        shortcut = QShortcut(QKeySequence(HOTKEY_TEXT), overlay)
        shortcut.activated.connect(lambda: send(("stop",)))

    timer = QTimer()
    timer.timeout.connect(poll)
    timer.start(POLL_MS)
    swarm.start()
    app.exec()


# --- in the main process ------------------------------------------------------
class _Worker:
    def __init__(self, process, conn) -> None:
        self.process = process
        self.conn = conn
        self.open_count = 0
        self.all_closed = False
        self.frames = 0


class WorkerPool(QObject):
    """The pictures, spread over *count* worker processes.

    Has the same face as ``Swarm`` for the main program: ``start``,
    ``open_count``, ``all_closed``, ``raise_`` and ``shutdown``.
    """

    stop_requested = Signal()  # Ctrl+Shift+Q pressed on a worker's picture

    def __init__(self, sources: list[Path], count: int, rng: random.Random | None = None) -> None:
        super().__init__()
        self.rng = rng or random.Random()
        self.sources = list(sources)
        self.shares = split(self.sources, max(1, count), self.rng)
        self.workers: list[_Worker | None] = [None] * len(self.shares)
        self.restarts = 0
        self.started = False
        self.quitting = False
        self._context = mp.get_context("spawn")
        self._job = _job_that_dies_with_us()
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._poll)

    @property
    def open_count(self) -> int:
        return sum(w.open_count for w in self.workers if w is not None)

    def all_closed(self) -> bool:
        if not self.sources:
            return True
        return self.started and all(w is not None and w.all_closed for w in self.workers)

    def start(self) -> None:
        self.started = True
        for i in range(len(self.shares)):
            self._launch(i)
        self._timer.start(POLL_MS)

    def raise_(self) -> None:
        self._broadcast("raise")

    def shutdown(self) -> None:
        if self.quitting:
            return
        self.quitting = True
        self._timer.stop()
        self._broadcast("quit")
        for worker in self.workers:
            if worker is None:
                continue
            worker.process.join(2.0)
            if worker.process.is_alive():
                worker.process.terminate()
                worker.process.join(1.0)
            worker.conn.close()

    # --- internals ---------------------------------------------------------------
    def _launch(self, i: int) -> None:
        here, there = self._context.Pipe()
        process = self._context.Process(
            target=worker_main,
            args=(there, self.sources, self.shares[i], self.rng.random()),
            name=f"snow-leopards-{i + 1}",
            daemon=True,
        )
        process.start()
        there.close()
        if self._job is not None:
            _add_to_job(self._job, process)
        self.workers[i] = _Worker(process, here)

    def _broadcast(self, message) -> None:
        for worker in self.workers:
            if worker is not None:
                try:
                    worker.conn.send(message)
                except (OSError, EOFError):
                    pass

    def _poll(self) -> None:
        for i, worker in enumerate(self.workers):
            try:
                while worker.conn.poll():
                    message = worker.conn.recv()
                    if message[0] == "status":
                        _, worker.open_count, worker.all_closed, worker.frames = message
                    elif message[0] == "stop":
                        self.stop_requested.emit()
            except (OSError, EOFError):
                pass
            if self.quitting:
                return
            if not worker.process.is_alive():  # crashed or killed: bring it back
                worker.conn.close()
                self.restarts += 1
                self._launch(i)


# --- Windows job object --------------------------------------------------------
def _job_that_dies_with_us():
    """A job object that kills its processes when this process ends, however it ends."""
    if sys.platform != "win32":
        return None
    import ctypes
    from ctypes import wintypes

    class BasicLimits(ctypes.Structure):
        _fields_ = [
            ("PerProcessUserTimeLimit", ctypes.c_int64),
            ("PerJobUserTimeLimit", ctypes.c_int64),
            ("LimitFlags", wintypes.DWORD),
            ("MinimumWorkingSetSize", ctypes.c_size_t),
            ("MaximumWorkingSetSize", ctypes.c_size_t),
            ("ActiveProcessLimit", wintypes.DWORD),
            ("Affinity", ctypes.c_size_t),
            ("PriorityClass", wintypes.DWORD),
            ("SchedulingClass", wintypes.DWORD),
        ]

    class ExtendedLimits(ctypes.Structure):
        _fields_ = [
            ("BasicLimitInformation", BasicLimits),
            ("IoInfo", ctypes.c_uint64 * 6),
            ("ProcessMemoryLimit", ctypes.c_size_t),
            ("JobMemoryLimit", ctypes.c_size_t),
            ("PeakProcessMemoryUsed", ctypes.c_size_t),
            ("PeakJobMemoryUsed", ctypes.c_size_t),
        ]

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.CreateJobObjectW.restype = wintypes.HANDLE
    kernel32.CreateJobObjectW.argtypes = [ctypes.c_void_p, wintypes.LPCWSTR]
    kernel32.SetInformationJobObject.argtypes = [wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD]
    kernel32.AssignProcessToJobObject.argtypes = [wintypes.HANDLE, wintypes.HANDLE]
    job = kernel32.CreateJobObjectW(None, None)
    if not job:
        return None
    info = ExtendedLimits()
    info.BasicLimitInformation.LimitFlags = 0x2000  # JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
    if not kernel32.SetInformationJobObject(job, 9, ctypes.byref(info), ctypes.sizeof(info)):
        return None
    return (kernel32, job)


def _add_to_job(job, process) -> None:
    kernel32, handle = job
    kernel32.AssignProcessToJobObject(handle, process.sentinel)  # sentinel is the process handle
