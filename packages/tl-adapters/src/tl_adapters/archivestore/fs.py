"""A write-once ``ArchiveStore`` on a local directory (fanout decision D4).

The archive root is independent of the record object store's root. A key is a relative path with
``/`` separators; a value, once written, is never replaced.
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

from tl_core.archive import ArchiveExistsError

TMP_PREFIX = ".tmp-"
"""Files being written start with this; ``list_keys`` never shows them."""


class FsArchiveStore:
    """An ``ArchiveStore`` (``tl_core.archive.types``) on the directory ``root``."""

    def __init__(self, root: Path | str) -> None:
        self._root = Path(root)
        self._root.mkdir(parents=True, exist_ok=True)

    @property
    def root(self) -> Path:
        return self._root

    def put_bytes(self, key: str, data: bytes) -> None:
        final = self._path(key)
        final.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp_name = tempfile.mkstemp(dir=final.parent, prefix=TMP_PREFIX)
        tmp = Path(tmp_name)
        try:
            with os.fdopen(fd, "wb") as handle:
                handle.write(data)
                handle.flush()
                os.fsync(handle.fileno())
            os.chmod(tmp, 0o444)
            try:
                os.link(tmp, final)
            except FileExistsError as exc:
                raise ArchiveExistsError(key) from exc
        finally:
            try:
                tmp.unlink()
            except FileNotFoundError:
                pass

    def get_bytes(self, key: str) -> bytes:
        path = self._path(key)
        if not path.is_file():
            raise KeyError(key)
        return path.read_bytes()

    def exists(self, key: str) -> bool:
        return self._path(key).is_file()

    def list_keys(self, prefix: str) -> list[str]:
        keys: list[str] = []
        for dirpath, _dirnames, filenames in os.walk(self._root):
            for name in filenames:
                if name.startswith(TMP_PREFIX):
                    continue
                relative = Path(dirpath, name).relative_to(self._root)
                key = "/".join(relative.parts)
                if key.startswith(prefix):
                    keys.append(key)
        keys.sort()
        return keys

    def _path(self, key: str) -> Path:
        """Validate ``key`` (before any disk access) and return its path under the root."""
        if not key or "\0" in key or "\\" in key or key.startswith("/"):
            raise ValueError(f"unsafe archive key: {key!r}")
        for segment in key.split("/"):
            if segment in ("", ".", "..") or segment.startswith(TMP_PREFIX):
                raise ValueError(f"unsafe archive key: {key!r}")
        return self._root / key
