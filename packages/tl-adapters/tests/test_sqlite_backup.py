"""Online SQLite snapshots (P0-I7-T02)."""

from __future__ import annotations

import hashlib
import sqlite3
import threading
from pathlib import Path

import pytest
from tl_adapters.sqlite.backup import BackupError, backup_database
from tl_adapters.sqlite.engine import make_engine
from tl_adapters.sqlite.ledger import SqliteLedger
from tl_adapters.sqlite.uow import create_schema, open_uow
from tl_core.ledger import NewEvent


def add_events(db: Path, start: int, count: int) -> None:
    engine = make_engine(db)
    try:
        ledger = SqliteLedger(engine)
        for n in range(start, start + count):
            ledger.append(
                stream_id=f"s-{n}",
                stream_type="test.Thing",
                scope="project:P1",
                expected_version=0,
                events=[NewEvent(event_type="Thing.Created", payload={"n": n})],
                actor="user:u-1",
                source="test",
                correlation_id=f"c-{n}",
            )
    finally:
        engine.dispose()


@pytest.fixture
def ledger(tmp_path: Path) -> Path:
    db = tmp_path / "tl.db"
    create_schema(db)
    add_events(db, 1, 5)
    return db


def test_the_snapshot_is_a_standalone_ledger_with_the_same_events(
    ledger: Path, tmp_path: Path
) -> None:
    dest = tmp_path / "out" / "snap.db"  # the parent directory is created
    result = backup_database(ledger, dest)

    assert result.dest == dest and result.source == ledger
    assert result.head_seq == 5
    assert result.bytes == dest.stat().st_size > 0
    assert result.sha256 == hashlib.sha256(dest.read_bytes()).hexdigest()
    assert result.seconds >= 0
    assert not list(dest.parent.glob("*-wal")) and not list(dest.parent.glob("*-shm"))
    assert [p.name for p in dest.parent.iterdir()] == ["snap.db"]  # no temp file left

    reader = sqlite3.connect(f"file:{dest}?mode=ro", uri=True)
    try:
        assert reader.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
        assert reader.execute("PRAGMA journal_mode").fetchone()[0] == "delete"
        snap = reader.execute("SELECT seq, hash FROM events ORDER BY seq").fetchall()
    finally:
        reader.close()
    original = sqlite3.connect(f"file:{ledger}?mode=ro", uri=True)
    try:
        assert snap == original.execute("SELECT seq, hash FROM events ORDER BY seq").fetchall()
    finally:
        original.close()


def test_the_snapshot_opens_as_a_ledger_and_accepts_new_events(
    ledger: Path, tmp_path: Path
) -> None:
    copy = tmp_path / "copy.db"
    backup_database(ledger, copy)
    copy.chmod(0o644)  # a snapshot is read-only; a restore copies it first
    add_events(copy, 100, 1)
    with open_uow(copy, readonly=True) as uow:
        assert uow.ledger.head_seq() == 6


def test_a_destination_that_exists_is_never_replaced(ledger: Path, tmp_path: Path) -> None:
    dest = tmp_path / "snap.db"
    dest.write_bytes(b"precious")
    with pytest.raises(BackupError, match="destination exists"):
        backup_database(ledger, dest)
    assert dest.read_bytes() == b"precious"
    assert not [p for p in tmp_path.iterdir() if p.name.startswith(".snap.db.tmp-")]


def test_a_missing_source_fails_and_creates_nothing(tmp_path: Path) -> None:
    with pytest.raises(BackupError, match="source database not found"):
        backup_database(tmp_path / "nope.db", tmp_path / "snap.db")
    assert list(tmp_path.iterdir()) == []


def test_a_source_that_is_not_a_database_fails_and_leaves_no_file(tmp_path: Path) -> None:
    bad = tmp_path / "bad.db"
    bad.write_bytes(b"this is not a database" * 100)
    with pytest.raises(BackupError):
        backup_database(bad, tmp_path / "snap.db")
    assert [p.name for p in tmp_path.iterdir()] == ["bad.db"]


def test_a_database_without_events_gives_head_seq_zero(tmp_path: Path) -> None:
    empty = tmp_path / "empty.db"
    sqlite3.connect(empty).close()
    result = backup_database(empty, tmp_path / "snap.db")
    assert result.head_seq == 0


def test_a_snapshot_taken_while_events_are_being_written_is_consistent(
    ledger: Path, tmp_path: Path
) -> None:
    stop = threading.Event()
    errors: list[BaseException] = []

    def writer() -> None:
        n = 1000
        try:
            while not stop.is_set():
                add_events(ledger, n, 1)
                n += 1
        except BaseException as error:  # noqa: BLE001
            errors.append(error)

    thread = threading.Thread(target=writer, daemon=True)
    thread.start()
    try:
        results = [backup_database(ledger, tmp_path / f"snap{i}.db") for i in range(3)]
    finally:
        stop.set()
        thread.join(timeout=10)
    assert not errors
    for result in results:
        reader = sqlite3.connect(f"file:{result.dest}?mode=ro", uri=True)
        try:
            count, head = reader.execute("SELECT COUNT(*), MAX(seq) FROM events").fetchone()
            assert count == head == result.head_seq >= 5  # gap-free up to the head it reports
            assert reader.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
        finally:
            reader.close()
