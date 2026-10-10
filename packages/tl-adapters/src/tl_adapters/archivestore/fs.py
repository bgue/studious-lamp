"""A write-once ``ArchiveStore`` on a local directory (fanout decision D4).

STUB (P0-I7-T01): the methods raise ``NotImplementedError``. Remove this paragraph when done.

The archive root is independent of the record object store's root. A key is a relative path with
``/`` separators; a value, once written, is never replaced.
"""

from __future__ import annotations

from pathlib import Path

TMP_PREFIX = ".tmp-"
"""Files being written start with this; ``list_keys`` never shows them."""


class FsArchiveStore:
    """An ``ArchiveStore`` (``tl_core.archive.types``) on the directory ``root``."""

    def __init__(self, root: Path | str) -> None:
        raise NotImplementedError

    @property
    def root(self) -> Path:
        raise NotImplementedError

    def put_bytes(self, key: str, data: bytes) -> None:
        raise NotImplementedError

    def get_bytes(self, key: str) -> bytes:
        raise NotImplementedError

    def exists(self, key: str) -> bool:
        raise NotImplementedError

    def list_keys(self, prefix: str) -> list[str]:
        raise NotImplementedError
