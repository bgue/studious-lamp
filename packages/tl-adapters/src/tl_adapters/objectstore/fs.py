"""Filesystem object store: content-addressed files under a root (ADR-0002, brief 5.2).

The default backend in dev and in every test. Writes are atomic and verified: the bytes go to a
temporary file under ``<root>/.tmp``, are flushed and fsynced, size and SHA-256 are checked, and
only then is the file renamed to its final path, so a reader never sees a partial or unverified
object. A content-addressed key (``sha256/...``) is never replaced: if the object is already there,
the new bytes are verified and discarded.

Presigned URLs are ``file://`` URLs for the object's path plus a query ``op``, ``exp`` (epoch
seconds) and ``sig`` (HMAC-SHA256 over ``op``, key and ``exp`` with the store's secret). ``redeem``
checks one; ``put_via_url`` and ``get_via_url`` are what a local client does with it.

STUB (P0-I4-T20): the signatures are final; every method marked ``raise NotImplementedError`` is
the ticket. Remove this paragraph when done.
"""

from __future__ import annotations

import time
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import BinaryIO, Literal


class FsObjectStore:
    """An ``ObjectStore`` (see ``tl_core.files.types``) on a local directory."""

    def __init__(
        self, root: Path, *, secret: bytes, clock: Callable[[], float] = time.time
    ) -> None:
        self._root = Path(root)
        self._secret = secret
        self._clock = clock

    @property
    def root(self) -> Path:
        return self._root

    def path_for(self, key: str) -> Path:
        """The file that holds ``key`` (``root / key``); ``InvalidObjectKey`` for a bad key."""
        raise NotImplementedError

    def put(self, key: str, data: BinaryIO, *, size: int, sha256: str, content_type: str) -> None:
        """Store verified bytes atomically; see the module docstring.

        Reads at most ``size + 1`` bytes. Raises ``ObjectIntegrityError`` when the stream does not
        hold exactly ``size`` bytes or their SHA-256 differs from ``sha256`` (compared as lower
        case); nothing is left behind in that case. ``content_type`` is not stored by this backend.
        """
        raise NotImplementedError

    def get(self, key: str) -> BinaryIO:
        """Open for reading in binary mode. Raises ``ObjectNotFound``."""
        raise NotImplementedError

    def exists(self, key: str) -> bool:
        raise NotImplementedError

    def presign_put(self, key: str, *, expires_s: int) -> str:
        raise NotImplementedError

    def presign_get(self, key: str, *, expires_s: int) -> str:
        raise NotImplementedError

    def redeem(self, url: str, *, op: Literal["put", "get"]) -> str:
        """Verify a presigned URL for ``op`` and return its key.

        Raises ``PresignInvalid`` (malformed, wrong operation, wrong root, or bad signature) or
        ``PresignExpired`` (``exp`` earlier than now).
        """
        raise NotImplementedError

    def put_via_url(self, url: str, data: BinaryIO) -> None:
        """Redeem a ``put`` URL and write the bytes at its key, atomically, without a hash check.

        For staging keys, whose content is verified later by the upload service.
        """
        raise NotImplementedError

    def get_via_url(self, url: str) -> BinaryIO:
        """Redeem a ``get`` URL and open its object. Raises ``ObjectNotFound``."""
        raise NotImplementedError

    def iter_keys(self) -> Iterator[str]:
        """Every stored key, sorted, as posix paths relative to the root. Skips ``.tmp``."""
        raise NotImplementedError
