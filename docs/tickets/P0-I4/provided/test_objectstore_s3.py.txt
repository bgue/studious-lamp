"""The S3 object store against moto's in-process mock (P0-I4-T21). No network, no MinIO."""

from __future__ import annotations

import hashlib
import io
from collections.abc import Iterator
from typing import Any

import boto3
import pytest
import requests
from moto import mock_aws
from tl_adapters.objectstore.s3 import S3ObjectStore
from tl_core.files import InvalidObjectKey, ObjectIntegrityError, ObjectNotFound, object_key

BUCKET = "tl-test"
BODY = b"mill test report, heat 4711"
DIGEST = hashlib.sha256(BODY).hexdigest()
KEY = object_key(DIGEST)


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch) -> Iterator[Any]:
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "testing")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "testing")
    monkeypatch.setenv("AWS_DEFAULT_REGION", "us-east-1")
    with mock_aws():
        s3 = boto3.client("s3", region_name="us-east-1")
        s3.create_bucket(Bucket=BUCKET)
        yield s3


@pytest.fixture
def store(client: Any) -> S3ObjectStore:
    return S3ObjectStore(client, BUCKET)


def put(store: S3ObjectStore, body: bytes = BODY, key: str = KEY) -> None:
    store.put(
        key,
        io.BytesIO(body),
        size=len(body),
        sha256=hashlib.sha256(body).hexdigest(),
        content_type="application/pdf",
    )


def test_put_then_get_returns_the_bytes_and_records_type_and_hash(
    store: S3ObjectStore, client: Any
) -> None:
    assert store.exists(KEY) is False
    put(store)
    assert store.exists(KEY) is True
    with store.get(KEY) as handle:
        assert handle.read() == BODY
    head = client.head_object(Bucket=BUCKET, Key=KEY)
    assert head["ContentType"] == "application/pdf"
    assert head["Metadata"] == {"sha256": DIGEST}
    assert head["ContentLength"] == len(BODY)


def test_get_streams_in_pieces(store: S3ObjectStore) -> None:
    body = b"0123456789" * 1000
    put(store, body, object_key(hashlib.sha256(body).hexdigest()))
    with store.get(object_key(hashlib.sha256(body).hexdigest())) as handle:
        assert handle.read(10) == b"0123456789"
        assert handle.read(5) == b"01234"
        assert handle.read() == body[15:]


def test_an_upper_case_digest_is_accepted(store: S3ObjectStore) -> None:
    store.put(
        KEY, io.BytesIO(BODY), size=len(BODY), sha256=DIGEST.upper(), content_type="text/plain"
    )
    assert store.exists(KEY)


def test_an_empty_object_can_be_stored(store: S3ObjectStore) -> None:
    empty = object_key(hashlib.sha256(b"").hexdigest())
    put(store, b"", empty)
    with store.get(empty) as handle:
        assert handle.read() == b""


def test_get_of_a_missing_key_raises_object_not_found(store: S3ObjectStore) -> None:
    with pytest.raises(ObjectNotFound):
        store.get(KEY)


@pytest.mark.parametrize(
    ("body", "size", "digest"),
    [
        (BODY, len(BODY), hashlib.sha256(b"different").hexdigest()),
        (BODY, len(BODY) + 1, DIGEST),
        (BODY, len(BODY) - 1, DIGEST),
        (BODY + b"!", len(BODY), DIGEST),
    ],
    ids=["wrong hash", "size too large", "size too small", "stream longer than declared"],
)
def test_bytes_that_do_not_match_are_refused_and_never_uploaded(
    store: S3ObjectStore, body: bytes, size: int, digest: str
) -> None:
    with pytest.raises(ObjectIntegrityError):
        store.put(KEY, io.BytesIO(body), size=size, sha256=digest, content_type="text/plain")
    assert store.exists(KEY) is False
    assert list(store.iter_keys()) == []


def test_a_content_addressed_object_is_never_replaced(
    store: S3ObjectStore, client: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    put(store)
    uploads: list[str] = []
    real_put_object = client.put_object

    def spy(**kwargs: Any) -> Any:
        uploads.append(kwargs["Key"])
        return real_put_object(**kwargs)

    monkeypatch.setattr(client, "put_object", spy)
    put(store)
    assert uploads == []
    with store.get(KEY) as handle:
        assert handle.read() == BODY


def test_a_second_put_with_wrong_bytes_still_fails_and_keeps_the_object(
    store: S3ObjectStore,
) -> None:
    put(store)
    with pytest.raises(ObjectIntegrityError):
        store.put(KEY, io.BytesIO(b"tampered"), size=8, sha256=DIGEST, content_type="text/plain")
    with store.get(KEY) as handle:
        assert handle.read() == BODY


def test_a_staging_key_may_be_overwritten(store: S3ObjectStore) -> None:
    put(store, b"first", "staging/abc")
    put(store, b"second", "staging/abc")
    with store.get("staging/abc") as handle:
        assert handle.read() == b"second"


def test_a_large_object_goes_through_the_spool_file(client: Any) -> None:
    small_spool = S3ObjectStore(client, BUCKET, spool_max=1024)
    body = b"abcdefgh" * 100_000
    key = object_key(hashlib.sha256(body).hexdigest())
    put(small_spool, body, key)
    with small_spool.get(key) as handle:
        assert handle.read() == body


@pytest.mark.parametrize("key", ["", "/abs", "../x", "a//b", "a/./b", "a b"])
def test_unsafe_keys_are_refused(store: S3ObjectStore, key: str) -> None:
    with pytest.raises(InvalidObjectKey):
        store.exists(key)
    with pytest.raises(InvalidObjectKey):
        store.get(key)
    with pytest.raises(InvalidObjectKey):
        put(store, key=key)
    with pytest.raises(InvalidObjectKey):
        store.presign_put(key, expires_s=60)


def test_a_prefix_namespaces_the_keys(client: Any) -> None:
    prefixed = S3ObjectStore(client, BUCKET, prefix="tenant-a/")
    plain = S3ObjectStore(client, BUCKET)
    put(prefixed)
    assert prefixed.exists(KEY) is True
    assert plain.exists(KEY) is False
    assert plain.exists("tenant-a/" + KEY) is True
    assert list(prefixed.iter_keys()) == [KEY]


def test_iter_keys_lists_every_key_sorted(store: S3ObjectStore) -> None:
    other = b"another"
    other_key = object_key(hashlib.sha256(other).hexdigest())
    put(store, other, other_key)
    put(store)
    put(store, b"s", "staging/zzz")
    assert list(store.iter_keys()) == sorted([KEY, other_key, "staging/zzz"])


def test_presigned_urls_work_with_a_plain_http_client(store: S3ObjectStore) -> None:
    put_url = store.presign_put("staging/abc", expires_s=60)
    assert requests.put(put_url, data=b"client bytes", timeout=5).status_code == 200
    with store.get("staging/abc") as handle:
        assert handle.read() == b"client bytes"
    get_url = store.presign_get("staging/abc", expires_s=60)
    response = requests.get(get_url, timeout=5)
    assert response.status_code == 200 and response.content == b"client bytes"


def test_presigned_urls_carry_the_expiry(store: S3ObjectStore) -> None:
    url = store.presign_get(KEY, expires_s=123)
    assert "Expires=" in url or "X-Amz-Expires=123" in url


def test_the_store_satisfies_the_protocol(store: S3ObjectStore) -> None:
    from tl_core.files.types import ObjectStore

    as_protocol: ObjectStore = store
    put(store)
    as_protocol.get(KEY).close()
