# pyright: basic
"""S3 object store: boto3 behind the ObjectStore Protocol (ADR-0002, brief 5.2).

For MinIO or S3 in a real deployment; tests run it against moto's in-process mock. The caller
builds the boto3 client (so endpoint, region and credentials stay outside this class).

``put`` verifies size and SHA-256 while spooling the stream to a temporary file, and only then
uploads, so nothing unverified becomes visible. A content-addressed key (``sha256/...``) that
already exists is never replaced. Multipart upload for very large files is not part of Phase 0:
a single ``put_object`` is used (5 GiB limit), and ``presign_put`` URLs are single PUTs.

STUB (P0-I4-T21): the signatures are final; every method marked ``raise NotImplementedError`` is
the ticket. Remove this paragraph when done.
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any, BinaryIO


class S3ObjectStore:
    """An ``ObjectStore`` (see ``tl_core.files.types``) on an S3 bucket."""

    def __init__(
        self, client: Any, bucket: str, *, prefix: str = "", spool_max: int = 8 * 1024 * 1024
    ) -> None:
        self._client = client
        self._bucket = bucket
        self._prefix = prefix
        self._spool_max = spool_max

    def put(self, key: str, data: BinaryIO, *, size: int, sha256: str, content_type: str) -> None:
        """Verify while spooling, then ``put_object`` with the content type and ``sha256`` metadata.

        Raises ``ObjectIntegrityError`` (nothing uploaded) when the stream does not hold exactly
        ``size`` bytes or their SHA-256 differs from ``sha256`` (lower case). Skips the upload when
        a content-addressed key already exists.
        """
        raise NotImplementedError

    def get(self, key: str) -> BinaryIO:
        """Open for streaming reads. Raises ``ObjectNotFound`` when the key does not exist."""
        raise NotImplementedError

    def exists(self, key: str) -> bool:
        raise NotImplementedError

    def presign_put(self, key: str, *, expires_s: int) -> str:
        raise NotImplementedError

    def presign_get(self, key: str, *, expires_s: int) -> str:
        raise NotImplementedError

    def iter_keys(self) -> Iterator[str]:
        """Every key under the prefix, sorted, with the prefix removed."""
        raise NotImplementedError
