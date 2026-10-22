"""A private folder for the files a person opens (P1-UX2-S4).

``PrivateTemp`` makes one directory (mode 0700) under the system temporary folder, hands it to
``fetch_file`` (which writes each file 0600 under its sanitised name and never overwrites), checks
every file before it is opened (a regular file, not a link, ours, mode 0600) and removes everything
on ``cleanup()``, when the screen closes and at interpreter exit (best effort). It never follows a
symbolic link, neither when it checks nor when it deletes.
"""

from __future__ import annotations

import atexit
import os
import shutil
import stat
import tempfile
import threading
from pathlib import Path
from types import TracebackType

PREFIX = "throughline-open-"


class UnsafeTempError(OSError):
    """The folder or a file in it is not what this process made (a link, another owner, wide)."""


_lock = threading.Lock()
_live: set[PrivateTemp] = set()
_hooked = False


def _cleanup_all() -> None:
    for temp in list(_live):
        temp.cleanup()


def _register(temp: PrivateTemp) -> None:
    global _hooked
    with _lock:
        _live.add(temp)
        if not _hooked:
            atexit.register(_cleanup_all)
            _hooked = True


class PrivateTemp:
    """One private directory, created on first use. Also a context manager."""

    def __init__(self, base: Path | None = None) -> None:
        self._base = base
        self._dir: Path | None = None

    @property
    def directory(self) -> Path:
        """The directory (created on first use); ``UnsafeTempError`` if it was swapped meanwhile."""
        if self._dir is None:
            base = self._base if self._base is not None else Path(tempfile.gettempdir())
            self._dir = Path(tempfile.mkdtemp(prefix=PREFIX, dir=base))
            os.chmod(self._dir, 0o700)
            _register(self)
        self._check_dir(self._dir)
        return self._dir

    @staticmethod
    def _check_dir(path: Path) -> None:
        info = os.lstat(path)  # lstat: a link in place of the folder is seen as a link
        if not stat.S_ISDIR(info.st_mode):
            raise UnsafeTempError(f"{path} is not a plain directory")
        if hasattr(os, "getuid") and info.st_uid != os.getuid():
            raise UnsafeTempError(f"{path} belongs to someone else")
        if info.st_mode & 0o077:
            raise UnsafeTempError(f"{path} is open to other users")

    def verify(self, path: Path) -> Path:
        """``path`` if it is a plain 0600 file of ours in the folder, else ``UnsafeTempError``."""
        folder = self.directory
        if path.parent != folder:
            raise UnsafeTempError(f"{path} is not in the private folder")
        info = os.lstat(path)
        if not stat.S_ISREG(info.st_mode):  # a link, a device, a folder
            raise UnsafeTempError(f"{path} is not a plain file")
        if hasattr(os, "getuid") and info.st_uid != os.getuid():
            raise UnsafeTempError(f"{path} belongs to someone else")
        if info.st_mode & 0o077:
            raise UnsafeTempError(f"{path} is open to other users")
        return path

    def cleanup(self) -> None:
        """Remove the folder and everything in it; links are removed, never followed."""
        folder, self._dir = self._dir, None
        with _lock:
            _live.discard(self)
        if folder is None:
            return
        try:
            if stat.S_ISDIR(os.lstat(folder).st_mode):
                shutil.rmtree(folder, ignore_errors=True)  # rmtree does not follow links
            else:
                os.unlink(folder)  # a link put in the folder's place: drop the link only
        except OSError:
            pass

    def __enter__(self) -> PrivateTemp:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        self.cleanup()
