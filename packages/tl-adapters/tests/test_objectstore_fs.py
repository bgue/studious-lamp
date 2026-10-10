"""The filesystem object store (P0-I4-T20)."""

from __future__ import annotations

import hashlib
import io
import os
from pathlib import Path
from typing import BinaryIO

import pytest
from tl_adapters.objectstore.fs import FsObjectStore
from tl_core.files import (
    InvalidObjectKey,
    ObjectIntegrityError,
    ObjectNotFound,
    PresignExpired,
    PresignInvalid,
    object_key,
)

BODY = b"mill test report, heat 4711"
DIGEST = hashlib.sha256(BODY).hexdigest()
KEY = object_key(DIGEST)


class Clock:
    def __init__(self) -> None:
        self.now = 1_000_000.0

    def __call__(self) -> float:
        return self.now


@pytest.fixture
def clock() -> Clock:
    return Clock()


@pytest.fixture
def store(tmp_path: Path, clock: Clock) -> FsObjectStore:
    return FsObjectStore(tmp_path / "objects", secret=b"s3cret", clock=clock)


def put(store: FsObjectStore, body: bytes = BODY, key: str = KEY) -> None:
    store.put(
        key,
        io.BytesIO(body),
        size=len(body),
        sha256=hashlib.sha256(body).hexdigest(),
        content_type="application/pdf",
    )


def leftovers(store: FsObjectStore) -> list[str]:
    tmp = store.root / ".tmp"
    return sorted(p.name for p in tmp.iterdir()) if tmp.exists() else []


# --- put, get, exists ---------------------------------------------------------------------


def test_put_then_get_returns_the_bytes_at_the_content_path(store: FsObjectStore) -> None:
    assert store.exists(KEY) is False
    put(store)
    assert store.exists(KEY) is True
    assert store.path_for(KEY) == store.root / "sha256" / DIGEST[:2] / DIGEST[2:4] / DIGEST
    assert store.path_for(KEY).read_bytes() == BODY
    with store.get(KEY) as handle:
        assert handle.read() == BODY
    assert leftovers(store) == []


def test_an_upper_case_digest_is_accepted(store: FsObjectStore) -> None:
    store.put(
        KEY, io.BytesIO(BODY), size=len(BODY), sha256=DIGEST.upper(), content_type="application/pdf"
    )
    assert store.exists(KEY)


def test_an_empty_object_can_be_stored(store: FsObjectStore) -> None:
    empty = object_key(hashlib.sha256(b"").hexdigest())
    put(store, b"", empty)
    with store.get(empty) as handle:
        assert handle.read() == b""


def test_get_of_a_missing_key_raises_object_not_found(store: FsObjectStore) -> None:
    with pytest.raises(ObjectNotFound):
        store.get(KEY)
    put(store)
    other = object_key(hashlib.sha256(b"other").hexdigest())
    with pytest.raises(ObjectNotFound):
        store.get(other)


def test_a_directory_is_not_an_object(store: FsObjectStore) -> None:
    put(store)
    assert store.exists(f"sha256/{DIGEST[:2]}") is False
    with pytest.raises(ObjectNotFound):
        store.get(f"sha256/{DIGEST[:2]}")


# --- verification -------------------------------------------------------------------------


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
def test_bytes_that_do_not_match_are_refused_and_never_visible(
    store: FsObjectStore, body: bytes, size: int, digest: str
) -> None:
    with pytest.raises(ObjectIntegrityError):
        store.put(KEY, io.BytesIO(body), size=size, sha256=digest, content_type="text/plain")
    assert store.exists(KEY) is False
    assert list(store.iter_keys()) == []
    assert leftovers(store) == []


class CountingReader(io.RawIOBase):
    """An endless stream that records how many bytes were asked of it."""

    def __init__(self) -> None:
        self.served = 0

    def readable(self) -> bool:
        return True

    def readinto(self, buffer: bytearray | memoryview) -> int:  # type: ignore[override]
        self.served += len(buffer)
        buffer[:] = b"x" * len(buffer)
        return len(buffer)


def test_a_stream_longer_than_declared_is_not_read_to_the_end(store: FsObjectStore) -> None:
    endless = CountingReader()
    with pytest.raises(ObjectIntegrityError):
        store.put(
            KEY,
            io.BufferedReader(endless),  # type: ignore[arg-type]
            size=10,
            sha256=DIGEST,
            content_type="text/plain",
        )
    assert endless.served < 1_000_000
    assert leftovers(store) == []


class FailingReader(io.RawIOBase):
    def readable(self) -> bool:
        return True

    def readinto(self, buffer: bytearray | memoryview) -> int:  # type: ignore[override]
        raise OSError("connection reset")


def test_a_failing_stream_leaves_nothing_behind(store: FsObjectStore) -> None:
    with pytest.raises(OSError, match="connection reset"):
        store.put(
            KEY,
            io.BufferedReader(FailingReader()),
            size=len(BODY),
            sha256=DIGEST,
            content_type="text/plain",
        )
    assert store.exists(KEY) is False
    assert leftovers(store) == []


def test_bytes_are_fsynced_before_the_rename(
    store: FsObjectStore, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: list[str] = []
    real_fsync, real_replace = os.fsync, os.replace

    def fsync(fd: int) -> None:
        calls.append("fsync")
        real_fsync(fd)

    def replace(src: str | os.PathLike[str], dst: str | os.PathLike[str]) -> None:
        calls.append("replace")
        real_replace(src, dst)

    monkeypatch.setattr(os, "fsync", fsync)
    monkeypatch.setattr(os, "replace", replace)
    put(store)
    assert "replace" in calls
    assert "fsync" in calls[: calls.index("replace")]


# --- immutability -------------------------------------------------------------------------


def test_a_content_addressed_object_is_never_replaced(store: FsObjectStore) -> None:
    put(store)
    before = store.path_for(KEY).stat()
    put(store)
    after = store.path_for(KEY).stat()
    assert (before.st_ino, before.st_mtime_ns) == (after.st_ino, after.st_mtime_ns)
    assert leftovers(store) == []


def test_a_second_put_with_wrong_bytes_still_fails_and_keeps_the_object(
    store: FsObjectStore,
) -> None:
    put(store)
    with pytest.raises(ObjectIntegrityError):
        store.put(KEY, io.BytesIO(b"tampered"), size=8, sha256=DIGEST, content_type="text/plain")
    assert store.path_for(KEY).read_bytes() == BODY


def test_a_staging_key_may_be_overwritten(store: FsObjectStore) -> None:
    put(store, b"first", "staging/abc")
    put(store, b"second", "staging/abc")
    with store.get("staging/abc") as handle:
        assert handle.read() == b"second"


# --- keys ---------------------------------------------------------------------------------


@pytest.mark.parametrize(
    "key", ["", "/etc/passwd", "../outside", "a/../../b", "a//b", "a/./b", ".hidden", "a b", "a\\b"]
)
def test_unsafe_keys_are_refused_everywhere(store: FsObjectStore, key: str) -> None:
    with pytest.raises(InvalidObjectKey):
        store.path_for(key)
    with pytest.raises(InvalidObjectKey):
        store.exists(key)
    with pytest.raises(InvalidObjectKey):
        store.get(key)
    with pytest.raises(InvalidObjectKey):
        put(store, key=key)
    with pytest.raises(InvalidObjectKey):
        store.presign_get(key, expires_s=60)


def test_iter_keys_lists_every_object_sorted_and_skips_temporary_files(
    store: FsObjectStore,
) -> None:
    assert list(store.iter_keys()) == []
    other = b"another"
    put(store, other, object_key(hashlib.sha256(other).hexdigest()))
    put(store)
    put(store, b"s", "staging/zzz")
    (store.root / ".tmp").mkdir(exist_ok=True)
    (store.root / ".tmp" / "partial").write_bytes(b"x")
    keys = list(store.iter_keys())
    assert keys == sorted(keys)
    assert set(keys) == {KEY, object_key(hashlib.sha256(other).hexdigest()), "staging/zzz"}


# --- presigned URLs -----------------------------------------------------------------------


def test_presigned_put_url_carries_a_signed_expiring_token(
    store: FsObjectStore, clock: Clock
) -> None:
    url = store.presign_put("staging/abc", expires_s=60)
    assert url.startswith("file://")
    assert "op=put" in url and f"exp={int(clock.now) + 60}" in url and "sig=" in url
    assert str(store.root.resolve()) in url
    assert store.redeem(url, op="put") == "staging/abc"


def test_a_local_client_uploads_and_downloads_through_urls(store: FsObjectStore) -> None:
    put_url = store.presign_put("staging/abc", expires_s=60)
    store.put_via_url(put_url, io.BytesIO(b"client bytes"))
    get_url = store.presign_get("staging/abc", expires_s=60)
    with store.get_via_url(get_url) as handle:
        assert handle.read() == b"client bytes"
    assert leftovers(store) == []


def test_urls_expire(store: FsObjectStore, clock: Clock) -> None:
    url = store.presign_get(KEY, expires_s=60)
    clock.now += 60
    assert store.redeem(url, op="get") == KEY  # the last second is still valid
    clock.now += 1
    with pytest.raises(PresignExpired):
        store.redeem(url, op="get")


def test_a_url_is_good_only_for_its_operation(store: FsObjectStore) -> None:
    with pytest.raises(PresignInvalid):
        store.redeem(store.presign_get(KEY, expires_s=60), op="put")
    with pytest.raises(PresignInvalid):
        store.put_via_url(store.presign_get("staging/a", expires_s=60), io.BytesIO(b"x"))
    assert store.exists("staging/a") is False


def test_a_tampered_url_does_not_verify(store: FsObjectStore, clock: Clock) -> None:
    url = store.presign_put("staging/abc", expires_s=60)
    later = url.replace(f"exp={int(clock.now) + 60}", f"exp={int(clock.now) + 6000}")
    other_key = url.replace("staging/abc", "staging/abd")
    flipped = url[:-1] + ("0" if url[-1] != "0" else "1")
    for bad in (later, other_key, flipped):
        with pytest.raises(PresignInvalid):
            store.redeem(bad, op="put")


def test_a_url_from_another_secret_or_root_does_not_verify(
    store: FsObjectStore, tmp_path: Path, clock: Clock
) -> None:
    stranger = FsObjectStore(tmp_path / "objects", secret=b"other", clock=clock)
    elsewhere = FsObjectStore(tmp_path / "elsewhere", secret=b"s3cret", clock=clock)
    with pytest.raises(PresignInvalid):
        store.redeem(stranger.presign_get(KEY, expires_s=60), op="get")
    with pytest.raises(PresignInvalid):
        store.redeem(elsewhere.presign_get(KEY, expires_s=60), op="get")


@pytest.mark.parametrize(
    "url", ["", "not a url", "file:///tmp/x", "https://example.com/a?op=get&exp=1&sig=x"]
)
def test_garbage_is_not_a_url(store: FsObjectStore, url: str) -> None:
    with pytest.raises(PresignInvalid):
        store.redeem(url, op="get")


def test_get_via_url_of_a_missing_object_raises_object_not_found(store: FsObjectStore) -> None:
    with pytest.raises(ObjectNotFound):
        store.get_via_url(store.presign_get(KEY, expires_s=60))


def test_the_store_satisfies_the_protocol(store: FsObjectStore) -> None:
    from tl_core.files.types import ObjectStore

    as_protocol: ObjectStore = store
    reader: BinaryIO
    put(store)
    reader = as_protocol.get(KEY)
    reader.close()
