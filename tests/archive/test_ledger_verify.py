"""Database verification: `verify_ledger` and `verify_archive(conn=..., deep=True)` (brief 24.5).

Each edit is made to a copy of a ledger file with the append-only triggers dropped, the way an
attacker with file access would. Seq 5 is in the middle of scope `project:P2` (seqs 2, 5, 8, 11).
"""

from __future__ import annotations

import sqlite3
from collections.abc import Callable
from typing import Any

import pytest
from tl_adapters.sqlite.engine import read_tx
from tl_core.archive import (
    Ed25519Signer,
    seal_segment,
    verify_archive,
    verify_ledger,
)
from tl_core.ledger import event_hash
from typer.testing import CliRunner

MakeBox = Callable[[str], Any]
MakeStore = Callable[..., Any]
NEW_PAYLOAD = '{"n":999,"tag":"x","text":"café"}'


@pytest.fixture
def world(make_box: MakeBox, memory_store: MakeStore, signer: Ed25519Signer) -> tuple[Any, Any]:
    """Twelve events, the first eight sealed."""
    box = make_box("a")
    box.add(12)
    store = memory_store()
    with read_tx(box.engine) as conn:
        assert seal_segment(conn, store, signer, max_events=8) is not None
    return box, store


def edit(box: Any, seq: int, *, payload: str | None = None, hash_: str | None = None) -> None:
    """Rewrite one stored event; ``hash_="rehash"`` makes the hash fit the new fields."""
    conn = sqlite3.connect(box.path)
    try:
        conn.execute("DROP TRIGGER trg_events_no_update")
        row = conn.execute(
            "SELECT event_id, stream_id, stream_version, event_type, payload, recorded_at, "
            "prev_hash, hash FROM events WHERE seq = ?",
            (seq,),
        ).fetchone()
        new_payload = payload if payload is not None else row[4]
        new_hash = row[7]
        if hash_ == "rehash":
            new_hash = event_hash(row[6], row[0], row[1], row[2], row[3], new_payload, row[5])
        elif hash_ is not None:
            new_hash = hash_
        conn.execute(
            "UPDATE events SET payload = ?, hash = ? WHERE seq = ?", (new_payload, new_hash, seq)
        )
        conn.commit()
    finally:
        conn.close()
    box.engine.dispose()


def ledger_issues(box: Any) -> list[Any]:
    with read_tx(box.engine) as conn:
        return verify_ledger(conn)


def archive_issues(box: Any, store: Any, signer: Ed25519Signer, *, deep: bool) -> list[Any]:
    with read_tx(box.engine) as conn:
        return verify_archive(store, public_key=signer.public_key, conn=conn, deep=deep)


def test_an_intact_ledger_verifies_both_ways(world: tuple[Any, Any], signer: Any) -> None:
    box, store = world
    assert ledger_issues(box) == []
    assert archive_issues(box, store, signer, deep=True) == []


def test_a_payload_only_edit_is_invisible_to_the_hash_column_check_and_found_by_both_deep_checks(
    world: tuple[Any, Any], signer: Any
) -> None:
    box, store = world
    edit(box, 5, payload=NEW_PAYLOAD)
    assert archive_issues(box, store, signer, deep=False) == []  # the gap the review found
    [found] = ledger_issues(box)
    assert (found.kind, found.seq, found.segment) == ("event_hash", 5, None)
    [deep] = archive_issues(box, store, signer, deep=True)
    assert (deep.kind, deep.seq) == ("event_hash", 5)


def test_a_hash_only_edit_is_found(world: tuple[Any, Any], signer: Any) -> None:
    box, store = world
    edit(box, 5, hash_="0" * 64)
    [found] = ledger_issues(box)
    assert (found.kind, found.seq) == ("event_hash", 5)
    [shallow] = archive_issues(box, store, signer, deep=False)
    assert (shallow.kind, shallow.seq) == ("db_mismatch", 5)
    [deep] = archive_issues(box, store, signer, deep=True)
    assert (deep.kind, deep.seq) == ("event_hash", 5)


def test_a_consistent_payload_and_hash_edit_breaks_the_next_event_of_the_scope(
    world: tuple[Any, Any], signer: Any
) -> None:
    box, store = world
    edit(box, 5, payload=NEW_PAYLOAD, hash_="rehash")
    [found] = ledger_issues(box)
    assert (found.kind, found.seq) == ("scope_chain", 8)  # next event in project:P2
    assert archive_issues(box, store, signer, deep=False)[0].seq == 5  # the hash column differs
    [deep] = archive_issues(box, store, signer, deep=True)
    assert (deep.kind, deep.seq) == ("db_mismatch", 5)
    assert "payload" in deep.detail and "hash" in deep.detail


def test_an_edit_after_the_last_sealed_seq_is_found_by_the_deep_tail_check(
    world: tuple[Any, Any], signer: Any
) -> None:
    box, store = world
    edit(box, 10, payload=NEW_PAYLOAD)
    assert archive_issues(box, store, signer, deep=False) == []  # beyond the archive
    [deep] = archive_issues(box, store, signer, deep=True)
    assert (deep.kind, deep.seq, deep.segment) == ("event_hash", 10, None)


def test_a_missing_event_is_a_seq_gap(world: tuple[Any, Any], signer: Any) -> None:
    box, store = world
    conn = sqlite3.connect(box.path)
    conn.execute("DROP TRIGGER trg_events_no_delete")
    conn.execute("DELETE FROM events WHERE seq = 6")
    conn.commit()
    conn.close()
    box.engine.dispose()
    [found] = ledger_issues(box)
    assert (found.kind, found.seq) == ("seq_gap", 6)


def test_the_cli_verifies_a_ledger_and_reports_the_first_divergence(
    world: tuple[Any, Any],
) -> None:
    from tl_cli.main import app

    box, _ = world
    runner = CliRunner()
    ok = runner.invoke(app, ["ledger", "verify"], env={"TL_DB": str(box.path)})
    assert ok.exit_code == 0 and ok.exception is None, ok.output
    assert ok.stdout.splitlines() == [f"verified ledger {box.path}: 12 events, hash chains intact"]
    edit(box, 5, payload=NEW_PAYLOAD)
    bad = runner.invoke(app, ["ledger", "verify"], env={"TL_DB": str(box.path)})
    assert bad.exit_code == 1 and isinstance(bad.exception, SystemExit)
    assert bad.stdout.splitlines() == [
        "divergence: event_hash seq=5: the database event's stored hash does not match its fields"
    ]
    missing = runner.invoke(app, ["ledger", "verify", "--db", str(box.path.parent / "none.db")])
    assert missing.exit_code == 1 and "error: no ledger at" in missing.stderr
