"""Object store backends (ADR-0002): ``fs`` (default) and ``s3`` (boto3, MinIO/S3).

``make_object_store`` picks one from the environment, so the CLI, the API and tests configure
storage the same way. Nothing here is imported by ``tl_core``; the Protocol it uses lives in
``tl_core.files.types``.
"""

from __future__ import annotations

import os
from collections.abc import Mapping
from pathlib import Path

from tl_core.files.types import ObjectStore

from tl_adapters.objectstore.fs import FsObjectStore
from tl_adapters.objectstore.s3 import S3ObjectStore

DEFAULT_ROOT = "./dev/data/objects"
#: Documented local dev default. Real deployments set TL_OBJECT_SECRET.
DEV_SECRET = "dev-only-object-secret"

__all__ = ["DEFAULT_ROOT", "DEV_SECRET", "FsObjectStore", "S3ObjectStore", "make_object_store"]


def object_secret(env: Mapping[str, str] | None = None) -> bytes:
    """The signing secret: ``TL_OBJECT_SECRET``, else the dev default."""
    source = os.environ if env is None else env
    return source.get("TL_OBJECT_SECRET", DEV_SECRET).encode()


def make_object_store(env: Mapping[str, str] | None = None) -> ObjectStore:
    """Build the store named by ``TL_OBJECT_STORE`` (``fs`` by default, or ``s3``).

    ``fs``: ``TL_OBJECT_ROOT`` (default ``./dev/data/objects``) and ``TL_OBJECT_SECRET``.
    ``s3``: ``TL_S3_BUCKET`` (required), ``TL_S3_PREFIX``, ``TL_S3_ENDPOINT`` (MinIO), and the usual
    AWS credential variables read by boto3.
    """
    source = os.environ if env is None else env
    kind = source.get("TL_OBJECT_STORE", "fs")
    if kind == "fs":
        return FsObjectStore(
            Path(source.get("TL_OBJECT_ROOT", DEFAULT_ROOT)), secret=object_secret(source)
        )
    if kind == "s3":
        import boto3  # pyright: ignore[reportMissingTypeStubs]

        bucket = source.get("TL_S3_BUCKET")
        if not bucket:
            raise ValueError("TL_S3_BUCKET is required when TL_OBJECT_STORE=s3")
        client = boto3.client("s3", endpoint_url=source.get("TL_S3_ENDPOINT") or None)  # pyright: ignore
        return S3ObjectStore(client, bucket, prefix=source.get("TL_S3_PREFIX", ""))
    raise ValueError(f"TL_OBJECT_STORE must be 'fs' or 's3', got {kind!r}")
