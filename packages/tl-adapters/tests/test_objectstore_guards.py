"""Presigned uploads never reach a content-addressed key (P0-I4-B, brief 5.2)."""

from __future__ import annotations

import hashlib
import io
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import boto3
import pytest
from moto import mock_aws
from tl_adapters.objectstore.fs import FsObjectStore
from tl_adapters.objectstore.s3 import S3ObjectStore
from tl_core.files import InvalidObjectKey, object_key

BODY = b"original bytes"
DIGEST = hashlib.sha256(BODY).hexdigest()
KEY = object_key(DIGEST)


def stored(store: FsObjectStore | S3ObjectStore) -> None:
    store.put(KEY, io.BytesIO(BODY), size=len(BODY), sha256=DIGEST, content_type="text/plain")


def test_fs_refuses_to_presign_an_upload_to_a_content_key(tmp_path: Path) -> None:
    store = FsObjectStore(tmp_path, secret=b"k")
    with pytest.raises(InvalidObjectKey):
        store.presign_put(KEY, expires_s=60)
    assert store.presign_put("staging/abc", expires_s=60).startswith("file://")
    assert store.presign_get(KEY, expires_s=60).startswith("file://")  # reading is fine


def test_fs_put_via_url_cannot_overwrite_a_content_key_even_with_a_valid_signature(
    tmp_path: Path,
) -> None:
    store = FsObjectStore(tmp_path, secret=b"k")
    stored(store)
    before = store.path_for(KEY).stat()
    forged = store._presign("put", KEY, 60)  # pyright: ignore[reportPrivateUsage]
    assert store.redeem(forged, op="put") == KEY  # the signature itself is good
    with pytest.raises(InvalidObjectKey):
        store.put_via_url(forged, io.BytesIO(b"tampered"))
    after = store.path_for(KEY).stat()
    assert store.path_for(KEY).read_bytes() == BODY
    assert (before.st_ino, before.st_mtime_ns) == (after.st_ino, after.st_mtime_ns)


@pytest.fixture
def s3_store(monkeypatch: pytest.MonkeyPatch) -> Iterator[S3ObjectStore]:
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "testing")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "testing")
    monkeypatch.setenv("AWS_DEFAULT_REGION", "us-east-1")
    with mock_aws():
        client: Any = boto3.client("s3", region_name="us-east-1")
        client.create_bucket(Bucket="tl-test")
        yield S3ObjectStore(client, "tl-test")


def test_s3_refuses_to_presign_an_upload_to_a_content_key(s3_store: S3ObjectStore) -> None:
    with pytest.raises(InvalidObjectKey):
        s3_store.presign_put(KEY, expires_s=60)
    assert "staging/abc" in s3_store.presign_put("staging/abc", expires_s=60)
    assert KEY in s3_store.presign_get(KEY, expires_s=60)
