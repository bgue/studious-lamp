"""Filesystem object store: content-addressed files under a root (ADR-0002, brief 5.2).

The default backend in dev and in every test. Writes are atomic and verified: the bytes go to a
temporary file under ``<root>/.tmp``, are flushed and fsynced, size and SHA-256 are checked, and
only then is the file renamed to its final path, so a reader never sees a partial or unverified
object. A content-addressed key (``sha256/...``) is never replaced: if the object is already there,
the new bytes are verified and discarded.

Presigned URLs are ``file://`` URLs for the object's path plus a query ``op``, ``exp`` (epoch
seconds) and ``sig`` (HMAC-SHA256 over ``op``, key and ``exp`` with the store's secret). ``redeem``
checks one; ``put_via_url`` and ``get_via_url`` are what a local client does with it.
"""

from __future__ import annotations

import hashlib
import hmac
import os
import tempfile
import time
import urllib.parse
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import BinaryIO, Literal, cast

from tl_core.files.errors import (
    InvalidObjectKey,
    ObjectIntegrityError,
    PresignExpired,
    PresignInvalid,
)
from tl_core.files.keys import check_key, is_content_key
from tl_core.files.types import ObjectNotFound

_TMP_DIR = ".tmp"
_CHUNK = 1024 * 1024


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
        return self._root / check_key(key)

    def put(self, key: str, data: BinaryIO, *, size: int, sha256: str, content_type: str) -> None:
        """Store verified bytes atomically; see the module docstring.

        Reads at most ``size + 1`` bytes. Raises ``ObjectIntegrityError`` when the stream does not
        hold exactly ``size`` bytes or their SHA-256 differs from ``sha256`` (compared as lower
        case); nothing is left behind in that case. ``content_type`` is not stored by this backend.
        """
        del content_type  # part of the ObjectStore contract; this backend does not store it
        self._store(
            self.path_for(key),
            data,
            expected=(size, sha256.lower()),
            overwrite=not is_content_key(key),
        )

    def get(self, key: str) -> BinaryIO:
        """Open for reading in binary mode. Raises ``ObjectNotFound``."""
        path = self.path_for(key)
        try:
            return cast(BinaryIO, path.open("rb"))
        except (FileNotFoundError, IsADirectoryError, NotADirectoryError):
            raise ObjectNotFound(key) from None

    def exists(self, key: str) -> bool:
        return self.path_for(key).is_file()

    def presign_put(self, key: str, *, expires_s: int) -> str:
        """A one-upload URL. Content keys (``sha256/...``) are refused: they are written only by
        ``put``, which verifies the bytes, so an unverified URL upload can never create one."""
        if is_content_key(check_key(key)):
            raise InvalidObjectKey(f"presigned uploads cannot target a content key: {key!r}")
        return self._presign("put", key, expires_s)

    def presign_get(self, key: str, *, expires_s: int) -> str:
        return self._presign("get", key, expires_s)

    def redeem(self, url: str, *, op: Literal["put", "get"]) -> str:
        """Verify a presigned URL for ``op`` and return its key.

        Raises ``PresignInvalid`` (malformed, wrong operation, wrong root, or bad signature) or
        ``PresignExpired`` (``exp`` earlier than now).
        """
        try:
            parts = urllib.parse.urlsplit(url)
        except ValueError as exc:
            raise PresignInvalid("not a presigned URL") from exc
        if parts.scheme != "file":
            raise PresignInvalid("presigned URLs of this store use the file:// scheme")
        query = urllib.parse.parse_qs(parts.query)
        url_op = _one(query, "op")
        exp_text = _one(query, "exp")
        sig_given = _one(query, "sig")
        try:
            exp = int(exp_text)
        except ValueError as exc:
            raise PresignInvalid("expiry is not an integer") from exc
        if url_op != op:
            raise PresignInvalid(f"URL is for {url_op!r}, not {op!r}")
        candidate = Path(urllib.parse.unquote(parts.path))
        try:
            key = candidate.relative_to(self._root.resolve()).as_posix()
        except ValueError as exc:
            raise PresignInvalid("URL does not point inside this store's root") from exc
        try:
            check_key(key)
        except InvalidObjectKey as exc:
            raise PresignInvalid("URL names an invalid object key") from exc
        expected = self._sign(op, key, exp)
        if not hmac.compare_digest(sig_given.encode("utf-8"), expected.encode("ascii")):
            raise PresignInvalid("signature does not verify")
        if exp < int(self._clock()):
            raise PresignExpired("URL has expired")
        return key

    def put_via_url(self, url: str, data: BinaryIO) -> None:
        """Redeem a ``put`` URL and write the bytes at its key, atomically, without a hash check.

        For staging keys, whose content is verified later by the upload service.
        """
        key = self.redeem(url, op="put")
        if is_content_key(key):
            raise InvalidObjectKey(f"a URL upload cannot write a content key: {key!r}")
        self._store(self.path_for(key), data, expected=None, overwrite=True)

    def get_via_url(self, url: str) -> BinaryIO:
        """Redeem a ``get`` URL and open its object. Raises ``ObjectNotFound``."""
        return self.get(self.redeem(url, op="get"))

    def iter_keys(self) -> Iterator[str]:
        """Every stored key, sorted, as posix paths relative to the root. Skips ``.tmp``."""
        found: list[str] = []
        for dirpath, dirnames, filenames in os.walk(self._root):
            here = Path(dirpath)
            if here == self._root:
                dirnames[:] = [name for name in dirnames if name != _TMP_DIR]
            for name in filenames:
                path = here / name
                if path.is_file():
                    found.append(path.relative_to(self._root).as_posix())
        yield from sorted(found)

    def _sign(self, op: str, key: str, expiry: int) -> str:
        message = f"{op}\n{key}\n{expiry}".encode()
        return hmac.new(self._secret, message, hashlib.sha256).hexdigest()

    def _presign(self, op: Literal["put", "get"], key: str, expires_s: int) -> str:
        path = self.path_for(key)
        expiry = int(self._clock()) + expires_s
        sig = self._sign(op, key, expiry)
        return (
            "file://" + urllib.parse.quote(str(path.resolve())) + f"?op={op}&exp={expiry}&sig={sig}"
        )

    def _store(
        self,
        final: Path,
        data: BinaryIO,
        *,
        expected: tuple[int, str] | None,
        overwrite: bool,
    ) -> None:
        """Write ``data`` to a temporary file, verify it if ``expected``, then move it into place.

        ``expected`` is ``(size, lower-case sha256)``; ``None`` skips verification and reads the
        stream to its end. With ``overwrite`` False, an existing file at ``final`` is kept and the
        new bytes are discarded after verification.
        """
        tmp_dir = self._root / _TMP_DIR
        tmp_dir.mkdir(parents=True, exist_ok=True)
        fd, name = tempfile.mkstemp(dir=tmp_dir)
        tmp = Path(name)
        try:
            limit = None if expected is None else expected[0] + 1
            hasher = hashlib.sha256()
            count = 0
            with os.fdopen(fd, "wb") as out:
                while limit is None or count < limit:
                    want = _CHUNK if limit is None else min(_CHUNK, limit - count)
                    chunk = data.read(want)
                    if not chunk:
                        break
                    hasher.update(chunk)
                    out.write(chunk)
                    count += len(chunk)
                out.flush()
                os.fsync(out.fileno())
            if expected is not None:
                _verify(count, hasher.hexdigest(), expected)
            if overwrite or not final.is_file():
                final.parent.mkdir(parents=True, exist_ok=True)
                os.replace(tmp, final)
                _fsync_dir(final.parent)
        finally:
            tmp.unlink(missing_ok=True)


def _verify(count: int, digest: str, expected: tuple[int, str]) -> None:
    size, sha256 = expected
    if count > size:
        raise ObjectIntegrityError(f"stream holds more than the declared {size} bytes")
    if count < size:
        raise ObjectIntegrityError(f"stream holds {count} bytes, declared {size}")
    if digest != sha256:
        raise ObjectIntegrityError(f"SHA-256 differs: declared {sha256}, computed {digest}")


def _fsync_dir(path: Path) -> None:
    fd = os.open(path, os.O_RDONLY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def _one(query: dict[str, list[str]], name: str) -> str:
    values = query.get(name, [])
    if len(values) != 1:
        raise PresignInvalid(f"URL needs exactly one {name!r} parameter")
    return values[0]
