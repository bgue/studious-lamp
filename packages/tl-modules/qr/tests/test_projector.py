"""The scan code projector: Issued then Revoked, and a rebuild (P2-QR S1)."""

from __future__ import annotations

from collections.abc import Callable, Iterator
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from sqlalchemy import Engine, text
from tl_core.ledger import Event, iso_utc
from tl_core.projection.record import RecordProjector
from tl_mod_qr.names import SCAN_CODE, SCAN_CODE_TABLE
from tl_mod_qr.projectors import ScanCodeProjector

BASE = datetime(2026, 12, 1, 9, 0, tzinfo=UTC)
STREAM = "01J9Z6Q4W3X2Y1V0T9S8R7Q6P2"
TARGET = "01J9Z6Q4W3X2Y1V0T9S8R7Q6P3"
NEXT = "01J9Z6Q4W3X2Y1V0T9S8R7Q6P4"
HASH = "ab" * 32


def events() -> list[Event]:
    def make(seq: int, event_type: str, payload: dict[str, Any], actor: str) -> Event:
        at = BASE + timedelta(minutes=seq)
        return Event(
            event_type=event_type,
            payload=payload,
            seq=seq,
            event_id=f"EVT{seq:06d}",
            stream_id=STREAM,
            stream_type=SCAN_CODE,
            stream_version=seq,
            scope="project:P123",
            actor=actor,
            recorded_at=at,
            effective_at=at,
            correlation_id="corr-1",
            causation_id=None,
            source="test",
            prev_hash=None,
            hash=f"hash-{seq}",
        )

    return [
        make(
            1,
            "Record.Created",
            {
                "record_type": SCAN_CODE,
                "key": STREAM,
                "title": "Pump",
                "description": "",
                "psets": {},
            },
            "user:uma",
        ),
        make(
            2,
            "ScanCode.Issued",
            {
                "record_id": STREAM,
                "code_hash": HASH,
                "target_id": TARGET,
                "target_type": "engineering.Tag",
                "label_text": "Pump P-101",
                "size": "tag",
                "expires_on": "2027-01-31",
                "feed_policy": "none",
            },
            "user:uma",
        ),
        make(
            3,
            "ScanCode.Revoked",
            {
                "record_id": STREAM,
                "reason": "Label lost",
                "replaced_by_id": NEXT,
                "feed_policy": "none",
            },
            "user:sue",
        ),
    ]


@pytest.fixture
def make_engine(new_engine: Callable[[], Engine], dialect: str) -> Iterator[Callable[[], Engine]]:
    made: list[Engine] = []

    def build() -> Engine:
        eng = new_engine()
        with eng.begin() as conn:
            for stmt in RecordProjector().ddl(dialect) + ScanCodeProjector().ddl(dialect):
                conn.execute(text(stmt))
        made.append(eng)
        return eng

    yield build
    for eng in made:
        eng.dispose()


def _apply(engine: Engine, *evs: Event) -> None:
    record, scan = RecordProjector(), ScanCodeProjector()
    for event in evs:
        with engine.begin() as conn:
            (scan if event.event_type in scan.handles else record).apply(conn, event)


def _row(engine: Engine) -> dict[str, Any]:
    with engine.connect() as conn:
        return dict(
            conn.execute(text(f"SELECT * FROM {SCAN_CODE_TABLE} WHERE id = :id"), {"id": STREAM})
            .mappings()
            .one()
        )


def test_issued_inserts_the_row(make_engine: Callable[[], Engine]) -> None:
    engine = make_engine()
    _apply(engine, *events()[:2])
    row = _row(engine)
    assert (row["code_hash"], row["target_id"], row["target_type"]) == (
        HASH,
        TARGET,
        "engineering.Tag",
    )
    assert (row["label_text"], row["size"], row["issued_by"]) == ("Pump P-101", "tag", "user:uma")
    assert row["issued_at"] == iso_utc(BASE + timedelta(minutes=2))
    assert str(row["expires_on"]) == "2027-01-31"
    assert row["scope"] == "project:P123" and row["last_seq"] == 2
    for column in ("revoked_at", "revoked_by", "revoke_reason", "replaced_by_id"):
        assert row[column] is None, column


def test_revoked_sets_the_revoke_fields(make_engine: Callable[[], Engine]) -> None:
    engine = make_engine()
    _apply(engine, *events())
    row = _row(engine)
    assert (row["revoked_by"], row["revoke_reason"], row["replaced_by_id"]) == (
        "user:sue",
        "Label lost",
        NEXT,
    )
    assert row["revoked_at"] == iso_utc(BASE + timedelta(minutes=3))
    assert row["last_seq"] == 3
    assert row["code_hash"] == HASH  # nothing else moved
    with engine.connect() as conn:
        version = conn.execute(
            text("SELECT version FROM cur_core_record WHERE id = :id"), {"id": STREAM}
        ).scalar_one()
    assert version == 3


def test_a_rebuild_gives_the_same_row(make_engine: Callable[[], Engine]) -> None:
    first, second = make_engine(), make_engine()
    _apply(first, *events())
    _apply(second, *events())
    assert _row(first) == _row(second)


def test_reset_empties_the_table_and_a_replay_rebuilds_the_row(
    make_engine: Callable[[], Engine],
) -> None:
    engine = make_engine()
    _apply(engine, *events())
    before = _row(engine)
    with engine.begin() as conn:
        ScanCodeProjector().reset(conn)
        assert conn.execute(text(f"SELECT COUNT(*) FROM {SCAN_CODE_TABLE}")).scalar_one() == 0
        conn.execute(text("DELETE FROM cur_core_record"))
    _apply(engine, *events())
    assert _row(engine) == before


def test_a_code_hash_is_used_once(make_engine: Callable[[], Engine]) -> None:
    engine = make_engine()
    _apply(engine, *events()[:2])
    with pytest.raises(Exception, match="(?i)unique"):
        with engine.begin() as conn:
            conn.execute(
                text(
                    f"INSERT INTO {SCAN_CODE_TABLE} (id, scope, code_hash, target_id, target_type, "
                    "size, issued_by, issued_at, last_seq) VALUES ('X', 's', :h, 't', 'x', 'tag', "
                    "'u', 'now', 1)"
                ),
                {"h": HASH},
            )


def test_an_event_for_a_missing_row_is_a_broken_stream(make_engine: Callable[[], Engine]) -> None:
    engine = make_engine()
    with pytest.raises(LookupError):
        _apply(engine, events()[2])
