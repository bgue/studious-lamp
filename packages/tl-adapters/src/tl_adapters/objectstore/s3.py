# pyright: basic
"""S3 object store: boto3 behind the ObjectStore Protocol (ADR-0002, brief 5.2).

For MinIO or S3 in a real deployment; tests run it against moto's in-process mock. The caller
builds the boto3 client (so endpoint, region and credentials stay outside this class).

``put`` verifies size and SHA-256 while spooling the stream to a temporary file, and only then
uploads, so nothing unverified becomes visible. A content-addressed key (``sha256/...``) that
already exists is never replaced. Multipart upload for very large files is not part of Phase 0:
a single ``put_object`` is used (5 GiB limit), and ``presign_put`` URLs are single PUTs.
"""

from __future__ import annotations

import hashlib
import io
import tempfile
from collections.abc import Iterator
from typing import Any, BinaryIO, cast

from botocore.exceptions import ClientError
from tl_core.files import InvalidObjectKey, ObjectIntegrityError, ObjectNotFound
from tl_core.files.keys import check_key, is_content_key

_MISSING_CODES = frozenset({"NoSuchKey", "404", "NotFound"})
_CHUNK = 1024 * 1024


def _error_code(exc: ClientError) -> str:
    return str(exc.response["Error"]["Code"])


class _BodyReader(io.RawIOBase):
    """Raw stream over a botocore ``StreamingBody``; reads are passed through, never buffered."""

    def __init__(self, body: Any) -> None:
        self._body = body

    def readable(self) -> bool:
        return True

    def readinto(self, buffer: Any) -> int:
        data = self._body.read(len(buffer))
        count = len(data)
        buffer[:count] = data
        return count

    def close(self) -> None:
        if not self.closed:
            self._body.close()
        super().close()


class S3ObjectStore:
    """An ``ObjectStore`` (see ``tl_core.files.types``) on an S3 bucket."""

    def __init__(
        self, client: Any, bucket: str, *, prefix: str = "", spool_max: int = 8 * 1024 * 1024
    ) -> None:
        self._client = client
        self._bucket = bucket
        self._prefix = prefix
        self._spool_max = spool_max

    def _full(self, key: str) -> str:
        return self._prefix + check_key(key)

    def put(self, key: str, data: BinaryIO, *, size: int, sha256: str, content_type: str) -> None:
        """Verify while spooling, then ``put_object`` with the content type and ``sha256`` metadata.

        Raises ``ObjectIntegrityError`` (nothing uploaded) when the stream does not hold exactly
        ``size`` bytes or their SHA-256 differs from ``sha256`` (lower case). Skips the upload when
        a content-addressed key already exists.
        """
        full = self._full(key)
        digest = hashlib.sha256()
        count = 0
        with tempfile.SpooledTemporaryFile(max_size=self._spool_max) as spool:
            while count <= size:
                chunk = data.read(min(_CHUNK, size + 1 - count))
                if not chunk:
                    break
                count += len(chunk)
                digest.update(chunk)
                spool.write(chunk)
            if count != size:
                raise ObjectIntegrityError(
                    f"{key!r}: stream holds {count} bytes, declared {size}; nothing stored"
                )
            if digest.hexdigest() != sha256.lower():
                raise ObjectIntegrityError(f"{key!r}: SHA-256 differs from the declaration")
            if is_content_key(key) and self.exists(key):
                return
            spool.seek(0)
            self._client.put_object(
                Bucket=self._bucket,
                Key=full,
                Body=spool,
                ContentType=content_type,
                ContentLength=size,
                Metadata={"sha256": digest.hexdigest()},
            )

    def get(self, key: str) -> BinaryIO:
        """Open for streaming reads. Raises ``ObjectNotFound`` when the key does not exist."""
        full = self._full(key)
        try:
            response = self._client.get_object(Bucket=self._bucket, Key=full)
        except ClientError as exc:
            if _error_code(exc) in _MISSING_CODES:
                raise ObjectNotFound(key) from None
            raise
        return cast(BinaryIO, io.BufferedReader(_BodyReader(response["Body"])))

    def exists(self, key: str) -> bool:
        full = self._full(key)
        try:
            self._client.head_object(Bucket=self._bucket, Key=full)
        except ClientError as exc:
            if _error_code(exc) in _MISSING_CODES:
                return False
            raise
        return True

    def presign_put(self, key: str, *, expires_s: int) -> str:
        """A one-upload URL. Content keys (``sha256/...``) are refused: they are written only by
        ``put``, which verifies the bytes, so an unverified URL upload can never create one."""
        full = self._full(key)
        if is_content_key(key):
            raise InvalidObjectKey(f"presigned uploads cannot target a content key: {key!r}")
        return str(
            self._client.generate_presigned_url(
                "put_object",
                Params={"Bucket": self._bucket, "Key": full},
                ExpiresIn=expires_s,
                HttpMethod="PUT",
            )
        )

    def presign_get(self, key: str, *, expires_s: int) -> str:
        full = self._full(key)
        return str(
            self._client.generate_presigned_url(
                "get_object",
                Params={"Bucket": self._bucket, "Key": full},
                ExpiresIn=expires_s,
            )
        )

    def iter_keys(self) -> Iterator[str]:
        """Every key under the prefix, sorted, with the prefix removed."""
        keys: list[str] = []
        paginator = self._client.get_paginator("list_objects_v2")
        for page in paginator.paginate(Bucket=self._bucket, Prefix=self._prefix):
            for item in page.get("Contents", []):
                keys.append(item["Key"][len(self._prefix) :])
        yield from sorted(keys)
