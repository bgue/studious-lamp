"""Object-store reconciliation against the real fs store (P0-I4-T25). cur_files rows are inserted
with SQL; the store holds real bytes."""

from __future__ import annotations

import hashlib
import io
from pathlib import Path
from typing import BinaryIO

import pytest
from sqlalchemy import text
from tl_adapters.objectstore.fs import FsObjectStore
from tl_adapters.sqlite.uow import create_schema, open_uow
from tl_core.files import ObjectNotFound, object_key
from tl_core.files.reconcile import ReconcileReport, reconcile_objects

INSERT = text(
    "INSERT INTO cur_files (file_id, scope, record_id, slot, revision, sha256, size, content_type, "
    "filename, status, deduplicated, uploaded_by, uploaded_at, updated_at, version, last_seq) "
    "VALUES (:file_id, 'project:P123', 'REC', NULL, 1, :sha, :size, 'text/plain', 'f.txt', "
    ":status, 0, 'user:t', '2026-01-01T00:00:00+00:00', '2026-01-01T00:00:00+00:00', 1, 1)"
)


@pytest.fixture
def db(tmp_path: Path) -> Path:
    path = tmp_path / "tl.db"
    create_schema(path)
    return path


@pytest.fixture
def store(tmp_path: Path) -> FsObjectStore:
    return FsObjectStore(tmp_path / "objects", secret=b"k")


def digest(body: bytes) -> str:
    return hashlib.sha256(body).hexdigest()


def put_object(store: FsObjectStore, body: bytes) -> str:
    key = object_key(digest(body))
    store.put(key, io.BytesIO(body), size=len(body), sha256=digest(body), content_type="text/plain")
    return key


def add_row(
    db: Path, file_id: str, body: bytes, *, status: str = "available", size: int | None = None
) -> None:
    with open_uow(db) as uow:
        uow.conn().execute(
            INSERT,
            {
                "file_id": file_id,
                "sha": digest(body),
                "size": len(body) if size is None else size,
                "status": status,
            },
        )


def run(db: Path, store: object, *, verify: bool = False) -> ReconcileReport:
    with open_uow(db, readonly=True) as uow:
        return reconcile_objects(uow, store, verify=verify)  # type: ignore[arg-type]


def test_an_empty_ledger_reconciles_cleanly(db: Path, store: FsObjectStore) -> None:
    report = run(db, store)
    assert report.ok and report.checked == 0 and report.listed is True and report.verified is False
    assert (report.missing, report.corrupt, report.orphans, report.staging) == ([], [], [], [])


def test_every_referenced_object_present_is_ok(db: Path, store: FsObjectStore) -> None:
    for name in (b"one", b"two"):
        put_object(store, name)
        add_row(db, f"F-{name.decode()}", name)
    report = run(db, store, verify=True)
    assert report.ok and report.checked == 2 and report.verified is True
    assert report.missing == [] and report.corrupt == []


def test_a_missing_object_is_reported_with_every_file_that_references_it(
    db: Path, store: FsObjectStore
) -> None:
    put_object(store, b"present")
    add_row(db, "F-present", b"present")
    add_row(db, "F-b", b"gone")
    add_row(db, "F-a", b"gone")
    report = run(db, store)
    assert not report.ok and report.checked == 2
    (problem,) = report.missing
    assert problem.kind == "missing" and problem.sha256 == digest(b"gone")
    assert problem.key == object_key(digest(b"gone")) and problem.detail is None
    assert problem.file_ids == ["F-a", "F-b"]  # sorted


def test_rejected_and_quarantined_files_still_need_their_bytes(
    db: Path, store: FsObjectStore
) -> None:
    add_row(db, "F-q", b"q", status="quarantined")
    add_row(db, "F-r", b"r", status="rejected")
    report = run(db, store)
    assert sorted(p.file_ids[0] for p in report.missing) == ["F-q", "F-r"]


def test_missing_problems_are_sorted_by_hash(db: Path, store: FsObjectStore) -> None:
    bodies = [b"a", b"b", b"c", b"d"]
    for i, body in enumerate(bodies):
        add_row(db, f"F-{i}", body)
    report = run(db, store)
    assert [p.sha256 for p in report.missing] == sorted(digest(b) for b in bodies)


def test_corruption_is_found_only_when_verifying(db: Path, store: FsObjectStore) -> None:
    key = put_object(store, b"original bytes")
    add_row(db, "F-1", b"original bytes")
    store.path_for(key).write_bytes(b"flipped bits!!")  # same length, other content
    assert run(db, store).ok  # existence alone cannot see it
    report = run(db, store, verify=True)
    assert not report.ok and report.missing == []
    (problem,) = report.corrupt
    assert problem.kind == "corrupt" and problem.file_ids == ["F-1"]
    assert problem.detail == f"sha256 is {digest(b'flipped bits!!')}"


def test_a_size_that_differs_from_the_row_is_corruption(db: Path, store: FsObjectStore) -> None:
    put_object(store, b"abc")
    add_row(db, "F-1", b"abc", size=99)
    report = run(db, store, verify=True)
    (problem,) = report.corrupt
    assert problem.detail == "3 bytes, expected 99"


def test_orphans_and_staging_keys_are_listed(db: Path, store: FsObjectStore) -> None:
    put_object(store, b"kept")
    add_row(db, "F-1", b"kept")
    orphan = put_object(store, b"left over from a rolled-back upload")
    store.put(
        "staging/zzz", io.BytesIO(b"s"), size=1, sha256=digest(b"s"), content_type="text/plain"
    )
    store.put(
        "staging/aaa", io.BytesIO(b"s"), size=1, sha256=digest(b"s"), content_type="text/plain"
    )
    store.put("other/x", io.BytesIO(b"s"), size=1, sha256=digest(b"s"), content_type="text/plain")
    report = run(db, store)
    assert report.ok  # orphans and staging keys are noise, not damage
    assert report.orphans == [orphan]
    assert report.staging == ["staging/aaa", "staging/zzz"]


class MinimalStore:
    """An ObjectStore that cannot list its keys."""

    def __init__(self, objects: dict[str, bytes]) -> None:
        self.objects = objects

    def put(self, key: str, data: BinaryIO, *, size: int, sha256: str, content_type: str) -> None:
        raise AssertionError("reconciliation never writes")

    def get(self, key: str) -> BinaryIO:
        try:
            return io.BytesIO(self.objects[key])
        except KeyError:
            raise ObjectNotFound(key) from None

    def exists(self, key: str) -> bool:
        return key in self.objects

    def presign_put(self, key: str, *, expires_s: int) -> str:
        raise AssertionError("not used")

    def presign_get(self, key: str, *, expires_s: int) -> str:
        raise AssertionError("not used")


def test_a_store_that_cannot_list_still_checks_references(db: Path) -> None:
    add_row(db, "F-1", b"here")
    add_row(db, "F-2", b"gone")
    minimal = MinimalStore({object_key(digest(b"here")): b"here", "sha256/zz/zz/stray": b"x"})
    report = run(db, minimal)
    assert report.listed is False and report.orphans == [] and report.staging == []
    assert [p.file_ids for p in report.missing] == [["F-2"]]


def test_reconciliation_closes_the_streams_it_opens(db: Path) -> None:
    opened: list[io.BytesIO] = []

    class Tracking(MinimalStore):
        def get(self, key: str) -> BinaryIO:
            stream = io.BytesIO(self.objects[key])
            opened.append(stream)
            return stream

    add_row(db, "F-1", b"here")
    run(db, Tracking({object_key(digest(b"here")): b"here"}), verify=True)
    assert len(opened) == 1 and opened[0].closed


def test_without_verify_no_object_is_read(db: Path) -> None:
    class NoRead(MinimalStore):
        def get(self, key: str) -> BinaryIO:
            raise AssertionError("get must not be called without verify")

    add_row(db, "F-1", b"here")
    assert run(db, NoRead({object_key(digest(b"here")): b"here"})).ok


def test_the_report_is_read_only(db: Path, store: FsObjectStore) -> None:
    put_object(store, b"x")
    before = list(store.iter_keys())
    run(db, store, verify=True)
    assert list(store.iter_keys()) == before
