"""Cross-process writer lock for the single-file claim store.

The claim store is read-modify-write over one JSONL file. Two Agent sessions
recording at the same time must not read the same snapshot and overwrite each
other. This module combines an in-process re-entrant lock (threads) with an
OS-level advisory byte lock (processes). The lock file is left in place; only
the byte range is locked, so cleanup is crash-safe on both POSIX and Windows.

A stale lock cannot survive process death: POSIX ``flock`` and Windows
``msvcrt.locking`` are released by the operating system when the handle closes
or the process exits. The lock file itself is intentionally not deleted.
"""
from __future__ import annotations

import os
import threading
import time
from pathlib import Path

DEFAULT_LOCK_TIMEOUT = 10.0
DEFAULT_POLL_INTERVAL = 0.05

_thread_locks = {}
_registry_guard = threading.Lock()


class LockTimeout(TimeoutError):
    """The lock could not be acquired before the deadline."""


def _thread_lock(path):
    key = str(Path(path).resolve())
    with _registry_guard:
        lock = _thread_locks.get(key)
        if lock is None:
            lock = threading.RLock()
            _thread_locks[key] = lock
        return lock


class FileLock:
    """Exclusive advisory lock over a dedicated lock file.

    ``timeout`` bounds both thread and process contention. A timeout is an
    explicit failure, never a silent overwrite.
    """

    def __init__(self, path, *, timeout=DEFAULT_LOCK_TIMEOUT,
                 poll_interval=DEFAULT_POLL_INTERVAL):
        if not isinstance(timeout, (int, float)) or timeout < 0:
            raise ValueError("lock timeout must be a non-negative number")
        self.path = Path(path)
        self.timeout = float(timeout)
        self.poll_interval = float(poll_interval)
        self._thread = None
        self._handle = None

    def __enter__(self):
        self._thread = _thread_lock(self.path)
        acquired = (self._thread.acquire(blocking=False) if self.timeout <= 0
                    else self._thread.acquire(timeout=self.timeout))
        if not acquired:
            self._thread = None
            raise LockTimeout(
                f"claim store is busy; timed out after {self.timeout:g}s waiting for {self.path}")
        try:
            self._handle = self._open_and_lock()
        except BaseException:
            self._thread.release()
            self._thread = None
            raise
        return self

    def _open_and_lock(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        handle = os.open(str(self.path), os.O_CREAT | os.O_RDWR, 0o600)
        deadline = time.monotonic() + self.timeout
        try:
            if os.name == "nt":
                import msvcrt
                if os.fstat(handle).st_size == 0:
                    os.write(handle, b"\0")
                os.lseek(handle, 0, os.SEEK_SET)
                while True:
                    try:
                        msvcrt.locking(handle, msvcrt.LK_NBLCK, 1)
                        return handle
                    except OSError:
                        if time.monotonic() >= deadline:
                            raise LockTimeout(
                                f"claim store is busy; timed out after {self.timeout:g}s "
                                f"waiting for {self.path}") from None
                        time.sleep(self.poll_interval)
            import fcntl
            while True:
                try:
                    fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
                    return handle
                except OSError:
                    if time.monotonic() >= deadline:
                        raise LockTimeout(
                            f"claim store is busy; timed out after {self.timeout:g}s "
                            f"waiting for {self.path}") from None
                    time.sleep(self.poll_interval)
        except BaseException:
            os.close(handle)
            raise

    def __exit__(self, exc_type, exc, tb):
        if self._handle is not None:
            if os.name == "nt":
                import msvcrt
                try:
                    os.lseek(self._handle, 0, os.SEEK_SET)
                    msvcrt.locking(self._handle, msvcrt.LK_UNLCK, 1)
                except OSError:
                    pass
            else:
                import fcntl
                try:
                    fcntl.flock(self._handle, fcntl.LOCK_UN)
                except OSError:
                    pass
            os.close(self._handle)
            self._handle = None
        if self._thread is not None:
            self._thread.release()
            self._thread = None
