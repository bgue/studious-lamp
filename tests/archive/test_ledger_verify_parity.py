"""`verify_ledger` and the deep database checks on SQLite and Postgres (brief 24.5).

Tampering goes through SQLAlchemy on a connection with the append-only triggers disabled, the way
an attacker with database access would, so the same tests run on both adapters. Pages are made
small so that a missing event at a page boundary is covered (the first review found an early stop).
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import pytest
from sqlalchemy import Connection, text
from tl_adapters.db import DbTarget, create_schema, make_engine, make_ledger, read_tx, write_tx
from tl_core.archive import (
    generate_signer,
    read_events,
    seal_segment,
    verify_archive,
    verify_ledger,
)
from tl_core.archive import verifier as verifier_module
from tl_core.ledger import NewEvent, canonical_json, event_hash, iso_utc

SCOPES = ("company", "project:P1", "project:P2")
NEW_PAYLOAD = {"n": 999, "tag": "x"}


def build(db: DbTarget, count: int) -> None:
    create_schema(db)
    engine = make_engine(db)
    try:
        ledger = make_ledger(engine)
        for n in range(1, count + 1):
            ledger.append(
                stream_id=f"s-{n}",
                stream_type="test.Thing",
                scope=SCOPES[n % 3],
                expected_version=0,
                events=[NewEvent(event_type="Thing.Created", payload={"n": n, "tag": "x"})],
                actor="user:u-1",
                source="test",
                correlation_id=f"c-{n}",
            )
    finally:
        engine.dispose()


def unprotect(conn: Connection) -> None:
    """Disable the append-only guards for this transaction's table (tampering only)."""
    if conn.dialect.name == "postgresql":
        conn.exec_driver_sql("ALTER TABLE events DISABLE TRIGGER trg_events_no_update_delete")
    else:
        conn.exec_driver_sql("DROP TRIGGER IF EXISTS trg_events_no_update")
        conn.exec_driver_sql("DROP TRIGGER IF EXISTS trg_events_no_delete")


def tamper(db: DbTarget, work: Callable[[Connection], None]) -> None:
    engine = make_engine(db)
    try:
        with write_tx(engine) as conn:
            unprotect(conn)
            work(conn)
    finally:
        engine.dispose()


def edit(
    db: DbTarget, seq: int, *, payload: dict[str, Any] | None = None, hash_: str | None = None
) -> None:
    """Rewrite one event; ``hash_="rehash"`` makes the hash fit the new fields."""

    def work(conn: Connection) -> None:
        [row] = read_events(conn, seq, seq)
        new_payload = payload if payload is not None else row.payload
        new_hash = row.hash
        if hash_ == "rehash":
            new_hash = event_hash(
                row.prev_hash,
                row.event_id,
                row.stream_id,
                row.stream_version,
                row.event_type,
                canonical_json(new_payload),
                iso_utc(row.recorded_at),
            )
        elif hash_ is not None:
            new_hash = hash_
        conn.execute(
            text("UPDATE events SET payload = :p, hash = :h WHERE seq = :s"),
            {"p": canonical_json(new_payload), "h": new_hash, "s": seq},
        )

    tamper(db, work)


def delete(db: DbTarget, *seqs: int) -> None:
    def work(conn: Connection) -> None:
        for seq in seqs:
            conn.execute(text("DELETE FROM events WHERE seq = :s"), {"s": seq})

    tamper(db, work)


def ledger_issues(db: DbTarget) -> list[Any]:
    engine = make_engine(db)
    try:
        with read_tx(engine) as conn:
            return verify_ledger(conn)
    finally:
        engine.dispose()


@pytest.fixture
def ledger(new_db: Callable[[], DbTarget]) -> DbTarget:
    db = new_db()
    build(db, 12)
    return db


@pytest.fixture
def sealed(ledger: DbTarget, memory_store: Callable[..., Any]) -> tuple[DbTarget, Any, Any]:
    """The same ledger with its first eight events sealed."""
    signer = generate_signer()
    store = memory_store()
    engine = make_engine(ledger)
    try:
        with read_tx(engine) as conn:
            assert seal_segment(conn, store, signer, max_events=8) is not None
    finally:
        engine.dispose()
    return ledger, store, signer


def archive_issues(db: DbTarget, store: Any, signer: Any, *, deep: bool = True) -> list[Any]:
    engine = make_engine(db)
    try:
        with read_tx(engine) as conn:
            return verify_archive(store, public_key=signer.public_key, conn=conn, deep=deep)
    finally:
        engine.dispose()


def test_an_intact_ledger_verifies(ledger: DbTarget) -> None:
    assert ledger_issues(ledger) == []


def test_a_payload_only_edit_is_an_event_hash_issue_at_that_seq(ledger: DbTarget) -> None:
    edit(ledger, 5, payload=NEW_PAYLOAD)
    [issue] = ledger_issues(ledger)
    assert (issue.kind, issue.seq) == ("event_hash", 5)


def test_a_hash_only_edit_is_an_event_hash_issue(ledger: DbTarget) -> None:
    edit(ledger, 5, hash_="0" * 64)
    [issue] = ledger_issues(ledger)
    assert (issue.kind, issue.seq) == ("event_hash", 5)


def test_a_consistent_edit_breaks_the_next_event_of_the_scope(ledger: DbTarget) -> None:
    edit(ledger, 5, payload=NEW_PAYLOAD, hash_="rehash")
    [issue] = ledger_issues(ledger)
    assert (issue.kind, issue.seq) == ("scope_chain", 8)  # seq 5 and 8 share project:P2


@pytest.mark.parametrize("page", [3, 4, 5, 12, 2000])
@pytest.mark.parametrize(
    ("missing", "first_gap"),
    [((4,), 4), ((6,), 6), ((4, 5), 4), ((8, 9), 8), ((5,), 5), ((12,), None)],
)
def test_missing_events_are_found_wherever_they_fall_in_a_page(
    ledger: DbTarget,
    monkeypatch: pytest.MonkeyPatch,
    page: int,
    missing: tuple[int, ...],
    first_gap: int | None,
) -> None:
    """Windows of 3, 4 and 5 put the missing seqs at the end, across and at the start of a page."""
    monkeypatch.setattr(verifier_module, "LEDGER_PAGE", page)
    delete(ledger, *missing)
    issues = ledger_issues(ledger)
    if first_gap is None:  # deleted trailing events leave nothing to contradict them
        assert issues == []
        return
    [issue] = issues
    assert (issue.kind, issue.seq) == ("seq_gap", first_gap)


def test_deep_verification_catches_each_kind_of_edit_against_the_archive(
    sealed: tuple[DbTarget, Any, Any],
) -> None:
    db, store, signer = sealed
    assert archive_issues(db, store, signer) == []
    edit(db, 5, payload=NEW_PAYLOAD)
    assert archive_issues(db, store, signer, deep=False) == []  # the hash column is untouched
    [deep] = archive_issues(db, store, signer)
    assert (deep.kind, deep.seq) == ("event_hash", 5)


def test_deep_verification_catches_a_consistent_edit_as_a_db_mismatch(
    sealed: tuple[DbTarget, Any, Any],
) -> None:
    db, store, signer = sealed
    edit(db, 5, payload=NEW_PAYLOAD, hash_="rehash")
    [deep] = archive_issues(db, store, signer)
    assert (deep.kind, deep.seq) == ("db_mismatch", 5)
    assert "payload" in deep.detail and "hash" in deep.detail


def test_the_deep_tail_check_reads_pages_across_gaps(
    sealed: tuple[DbTarget, Any, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    db, store, signer = sealed
    monkeypatch.setattr(verifier_module, "LEDGER_PAGE", 2)
    delete(db, 10)  # in the tail, after the sealed eight; the page [9, 10] ends at the gap
    [issue] = archive_issues(db, store, signer)
    assert (issue.kind, issue.seq, issue.segment) == ("seq_gap", 10, None)
