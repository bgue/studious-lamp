"""Object store contract (P0-I4; build spec 03 section 7, ADR-0002).

Backends live in tl_adapters: ``fs`` (default in dev and every test) and ``s3`` (boto3, tested
with moto). Keys are content-addressed, so an object is never replaced (brief 5.2).
"""

from __future__ import annotations

from typing import BinaryIO, Protocol


class ObjectNotFound(KeyError):
    """No object is stored under the key."""


def object_key(sha256_hex: str) -> str:
    """The content-addressed key for a SHA-256 hex digest: ``sha256/<aa>/<bb>/<digest>``."""
    digest = sha256_hex.lower()
    if len(digest) != 64 or any(c not in "0123456789abcdef" for c in digest):
        raise ValueError(f"not a SHA-256 hex digest: {sha256_hex!r}")
    return f"sha256/{digest[:2]}/{digest[2:4]}/{digest}"


class ObjectStore(Protocol):
    def put(self, key: str, data: BinaryIO, *, size: int, sha256: str, content_type: str) -> None:
        """Store bytes; verify size and SHA-256 before the object becomes visible."""
        ...

    def get(self, key: str) -> BinaryIO:
        """Open the object for reading. Raises ObjectNotFound."""
        ...

    def exists(self, key: str) -> bool: ...

    def presign_put(self, key: str, *, expires_s: int) -> str:
        """A URL (fs backend: a signed local token URL) that accepts one upload."""
        ...

    def presign_get(self, key: str, *, expires_s: int) -> str: ...
