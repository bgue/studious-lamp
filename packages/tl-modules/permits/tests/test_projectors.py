"""The permits projectors (P2-PTW S1). Events go through the ledger; no test writes a projection."""

from __future__ import annotations

from typing import Any

import pytest
from sqlalchemy import text
from tl_adapters.db import DbTarget, open_uow, rebuild_projections
from tl_core.ledger import NewEvent
from tl_core.services.commands import Command
from tl_core.services.records import create_module_record
from tl_mod_permits.names import (
    GAS_TEST,
    GAS_TEST_TABLE,
    ISOLATION,
    ISOLATION_TABLE,
    PERMIT,
    PERMIT_TABLE,
)

SCOPE = "project:P123"
TABLES = (PERMIT_TABLE, ISOLATION_TABLE, GAS_TEST_TABLE)


def _event(kind: str, record: str, **payload: Any) -> NewEvent:
    return NewEvent(
        event_type=kind, payload={"record_id": record, "feed_policy": "none", **payload}
    )


def _make(db: DbTarget, record_type: str, key: str, first: str, actor: str, **payload: Any) -> str:
    """A record: ``Record.Created`` and its first event in one append."""
    cmd = Command(actor=actor, source="test", scope=SCOPE)
    with open_uow(db) as uow:
        # the stream id is not known before the append, so the first payload names it after
        probe = create_module_record(uow, cmd, record_type=record_type, title=key, key=key)
        # a module event follows the envelope event on the same stream
        uow.append(
            stream_id=probe.stream_id,
            stream_type=record_type,
            scope=SCOPE,
            expected_version=probe.version,
            events=[_event(first, probe.stream_id, **payload)],
            actor=actor,
            source="test",
            correlation_id="corr-1",
        )
        return str(probe.stream_id)


def _step(
    db: DbTarget, record_type: str, record: str, kind: str, actor: str, **payload: Any
) -> None:
    with open_uow(db) as uow:
        version = int(
            uow.conn()
            .execute(text("SELECT version FROM cur_core_record WHERE id = :i"), {"i": record})
            .scalar_one()
        )
        uow.append(
            stream_id=record,
            stream_type=record_type,
            scope=SCOPE,
            expected_version=version,
            events=[_event(kind, record, **payload)],
            actor=actor,
            source="test",
            correlation_id="corr-1",
        )


def _row(db: DbTarget, table: str, record: str) -> dict[str, Any]:
    with open_uow(db, readonly=True) as uow:
        found = uow.conn().execute(text(f"SELECT * FROM {table} WHERE id = :i"), {"i": record})
        return dict(found.mappings().one())


def _all(db: DbTarget) -> dict[str, list[dict[str, Any]]]:
    with open_uow(db, readonly=True) as uow:
        return {
            t: [
                dict(r)
                for r in uow.conn().execute(text(f"SELECT * FROM {t} ORDER BY id")).mappings()
            ]
            for t in TABLES
        }


def _requested(db: DbTarget) -> str:
    return _make(
        db,
        PERMIT,
        "P123-PTW-0001",
        "Permit.Requested",
        "user:rob",
        permit_type="hot_work",
        for_record_id=None,
        area="A1",
        location_text="Pump room",
        holder="Rob",
        needed_from="2026-12-01",
        needed_until="2026-12-01",
    )


def test_a_permit_through_its_whole_life(db: DbTarget) -> None:
    permit = _requested(db)
    row = _row(db, PERMIT_TABLE, permit)
    assert (row["permit_type"], row["area"], row["holder"], row["requested_by"]) == (
        "hot_work",
        "A1",
        "Rob",
        "user:rob",
    )
    assert row["valid_until"] is None and row["revalidation_count"] == 0
    assert row["precautions_json"] == "[]" and row["lapse_flagged_for"] is None

    _step(db, PERMIT, permit, "Permit.Approved", "user:sue")
    assert _row(db, PERMIT_TABLE, permit)["approved_by"] == "user:sue"

    _step(
        db,
        PERMIT,
        permit,
        "Permit.Issued",
        "user:pam",
        issued_at="2026-12-01T06:30:00Z",
        valid_until="2026-12-01T18:00:00Z",
        precautions=[{"id": "fire_watch", "text": "Fire watch named"}],
    )
    row = _row(db, PERMIT_TABLE, permit)
    assert row["issued_by"] == "user:pam"
    assert row["valid_until"] == "2026-12-01T18:00:00.000000+00:00"
    assert row["issued_at"] == "2026-12-01T06:30:00.000000+00:00"
    assert '"fire_watch"' in row["precautions_json"]

    _step(
        db,
        PERMIT,
        permit,
        "Permit.Revalidated",
        "user:rob",
        at="2026-12-01T17:50:00Z",
        valid_until="2026-12-02T06:00:00Z",
    )
    row = _row(db, PERMIT_TABLE, permit)
    assert row["valid_until"] == "2026-12-02T06:00:00.000000+00:00"
    assert row["revalidation_count"] == 1
    assert row["last_revalidated_at"] == "2026-12-01T17:50:00.000000+00:00"
    assert row["issued_by"] == "user:pam" and row["lapse_flagged_for"] is None

    _step(db, PERMIT, permit, "Permit.Lapsed", "svc:permits", valid_until="2026-12-02T06:00:00Z")
    row = _row(db, PERMIT_TABLE, permit)
    assert row["lapse_flagged_for"] == "2026-12-02T06:00:00.000000+00:00"
    assert row["valid_until"] == "2026-12-02T06:00:00.000000+00:00"
    assert row["revalidation_count"] == 1

    _step(db, PERMIT, permit, "Permit.Suspended", "user:rob", reason="Gas alarm", gas_test_id=None)
    assert _row(db, PERMIT_TABLE, permit)["suspend_reason"] == "Gas alarm"

    _step(
        db,
        PERMIT,
        permit,
        "Permit.Resumed",
        "user:pam",
        at="2026-12-02T07:00:00Z",
        valid_until="2026-12-02T18:00:00Z",
    )
    row = _row(db, PERMIT_TABLE, permit)
    assert row["valid_until"] == "2026-12-02T18:00:00.000000+00:00"
    assert row["suspend_reason"] == "Gas alarm" and row["revalidation_count"] == 1
    assert row["lapse_flagged_for"] == "2026-12-02T06:00:00.000000+00:00"

    _step(db, PERMIT, permit, "Permit.HandedBack", "user:rob", note="Site clear")
    assert _row(db, PERMIT_TABLE, permit)["handback_note"] == "Site clear"

    _step(db, PERMIT, permit, "Permit.Closed", "user:pam")
    row = _row(db, PERMIT_TABLE, permit)
    assert row["closed_by"] == "user:pam" and row["handback_note"] == "Site clear"
    version = _row(db, "cur_core_record", permit)["version"]
    assert version == 10  # Created, Requested and eight more
    assert row["last_seq"] == _row(db, "cur_core_record", permit)["last_seq"]


def test_reject_and_cancel_and_the_link_events(db: DbTarget) -> None:
    rejected = _requested(db)
    _step(db, PERMIT, rejected, "Permit.Rejected", "user:sue", reason="Not this week")
    assert _row(db, PERMIT_TABLE, rejected)["reject_reason"] == "Not this week"
    cancelled = _make(
        db, PERMIT, "P123-PTW-0002", "Permit.Requested", "user:rob", permit_type="general"
    )
    _step(db, PERMIT, cancelled, "Permit.IsolationLinked", "user:rob", isolation_id="X")
    before = _row(db, PERMIT_TABLE, cancelled)
    _step(db, PERMIT, cancelled, "Permit.IsolationUnlinked", "user:rob", isolation_id="X")
    after = _row(db, PERMIT_TABLE, cancelled)
    assert after["last_seq"] > before["last_seq"]
    assert {k: v for k, v in after.items() if k != "last_seq"} == {
        k: v for k, v in before.items() if k != "last_seq"
    }
    _step(db, PERMIT, cancelled, "Permit.Cancelled", "user:rob", reason="Work moved")
    assert _row(db, PERMIT_TABLE, cancelled)["cancel_reason"] == "Work moved"


def test_isolation_applied_verified_removed(db: DbTarget) -> None:
    iso = _make(
        db,
        ISOLATION,
        "P123-ISL-0001",
        "Isolation.Applied",
        "user:ian",
        point_text="Pump P-101 breaker",
        point_record_id=None,
        energy="electrical",
        method="Lock and tag",
        lock_number="L-12",
        tag_number="T-12",
        applied_at="2026-12-01T06:00:00Z",
    )
    row = _row(db, ISOLATION_TABLE, iso)
    assert (row["energy"], row["lock_number"], row["applied_by"]) == (
        "electrical",
        "L-12",
        "user:ian",
    )
    assert row["applied_at"] == "2026-12-01T06:00:00.000000+00:00"
    assert row["verified_by"] is None and row["removed_by"] is None

    _step(db, ISOLATION, iso, "Isolation.Verified", "user:sue", verified_at="2026-12-01T06:20:00Z")
    row = _row(db, ISOLATION_TABLE, iso)
    assert (row["verified_by"], row["verified_at"]) == (
        "user:sue",
        "2026-12-01T06:20:00.000000+00:00",
    )
    _step(db, ISOLATION, iso, "Isolation.Removed", "user:ian", removed_at="2026-12-01T17:00:00Z")
    row = _row(db, ISOLATION_TABLE, iso)
    assert (row["removed_by"], row["removed_at"]) == (
        "user:ian",
        "2026-12-01T17:00:00.000000+00:00",
    )
    assert row["verified_by"] == "user:sue"


def test_a_gas_test_row(db: DbTarget) -> None:
    permit = _requested(db)
    gas = _make(
        db,
        GAS_TEST,
        "P123-GAS-0001",
        "GasTest.Recorded",
        "user:gus",
        permit_id=permit,
        taken_at="2026-12-01T06:10:00Z",
        tester="Gus",
        instrument_text="MX6",
        o2_pct="20.9",
        lel_pct="0",
        h2s_ppm=None,
        co_ppm="2",
        result="pass",
        note=None,
    )
    row = _row(db, GAS_TEST_TABLE, gas)
    assert row["permit_id"] == permit and row["result"] == "pass" and row["tester"] == "Gus"
    assert float(row["o2_pct"]) == 20.9
    assert float(row["co_ppm"]) == 2.0
    assert row["h2s_ppm"] is None and row["note"] is None


def test_a_rebuild_of_the_three_tables_equals_the_live_rows(db: DbTarget) -> None:
    permit = _requested(db)
    _step(db, PERMIT, permit, "Permit.Approved", "user:sue")
    _step(
        db,
        PERMIT,
        permit,
        "Permit.Issued",
        "user:pam",
        issued_at="2026-12-01T06:30:00Z",
        valid_until="2026-12-01T18:00:00Z",
        precautions=[],
    )
    _step(
        db,
        PERMIT,
        permit,
        "Permit.Revalidated",
        "user:rob",
        at="2026-12-01T17:50:00Z",
        valid_until="2026-12-02T06:00:00Z",
    )
    iso = _make(
        db,
        ISOLATION,
        "P123-ISL-0001",
        "Isolation.Applied",
        "user:ian",
        point_text="Breaker",
        energy="process",
        applied_at="2026-12-01T06:00:00Z",
    )
    _step(db, ISOLATION, iso, "Isolation.Removed", "user:ian", removed_at="2026-12-01T17:00:00Z")
    _make(
        db,
        GAS_TEST,
        "P123-GAS-0001",
        "GasTest.Recorded",
        "user:gus",
        permit_id=permit,
        taken_at="2026-12-01T06:10:00Z",
        tester="Gus",
        o2_pct="20.9",
        result="pass",
    )
    live = _all(db)
    assert all(len(rows) == 1 for rows in live.values())
    rebuild_projections(db)
    rebuilt = _all(db)
    assert rebuilt.keys() == live.keys()
    for table in TABLES:
        assert [_norm(r) for r in rebuilt[table]] == [_norm(r) for r in live[table]], table


def _norm(row: dict[str, Any]) -> dict[str, Any]:
    return {
        k: (float(v) if k.endswith(("_pct", "_ppm")) and v is not None else v)
        for k, v in row.items()
    }


def test_an_event_for_a_missing_row_is_a_broken_stream(db: DbTarget) -> None:
    permit = _requested(db)
    with open_uow(db) as uow:
        uow.conn().execute(text(f"DELETE FROM {PERMIT_TABLE}"))
    with pytest.raises(LookupError):
        _step(db, PERMIT, permit, "Permit.Approved", "user:sue")
