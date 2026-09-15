"""
Cross-platform file locking for the scoring log.
Uses a .lock sidecar file so both Woody and Buzz cannot claim the same
scoring-log row at the same time.
"""

import os
import time
import random

LOCK_TIMEOUT = 15   # seconds to wait before giving up
LOCK_POLL    = 0.1  # seconds between retries
STALE_AFTER  = 60   # seconds; a lock older than this is from a dead process


class ScoringLogLock:
    """
    Simple lock using a sidecar .lock file.
    Works across two Windows desktops on the same network share.
    Usage:
        with ScoringLogLock(path_to_xlsx):
            # safe to read + write scoring log here
    """

    def __init__(self, xlsx_path: str):
        self.lock_path = xlsx_path + ".lock"
        self._acquired = False

    def _break_if_stale(self):
        """A crashed process leaves its .lock behind and blocks every scorer
        forever. A lock older than STALE_AFTER can't belong to a live write
        (writes take well under a second), so reclaim it."""
        try:
            age = time.time() - os.path.getmtime(self.lock_path)
        except FileNotFoundError:
            return
        if age > STALE_AFTER:
            try:
                os.remove(self.lock_path)
            except FileNotFoundError:
                pass

    def acquire(self):
        deadline = time.time() + LOCK_TIMEOUT
        while time.time() < deadline:
            try:
                # O_CREAT | O_EXCL is atomic on Windows NTFS over SMB
                fd = os.open(self.lock_path,
                             os.O_CREAT | os.O_EXCL | os.O_WRONLY)
                os.write(fd, str(os.getpid()).encode())
                os.close(fd)
                self._acquired = True
                return
            except FileExistsError:
                # Another process holds the lock - or a dead one left it behind
                self._break_if_stale()
                time.sleep(LOCK_POLL + random.uniform(0, 0.05))
        raise TimeoutError(
            f"Could not acquire lock on scoring log after {LOCK_TIMEOUT}s. "
            "Is another process stuck? Delete the .lock file manually if needed."
        )

    def release(self):
        if self._acquired:
            try:
                os.remove(self.lock_path)
            except FileNotFoundError:
                pass
            self._acquired = False

    def __enter__(self):
        self.acquire()
        return self

    def __exit__(self, *_):
        self.release()
