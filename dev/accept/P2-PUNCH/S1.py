"""Acceptance for P2-PUNCH S1: quality.PunchItem schema, fixtures and module spec (SQLite).

Run: ``uv run python dev/accept/P2-PUNCH/S1.py``. The schema checks are the tests of
``packages/tl-schema/tests/test_quality_schema.py``; the module checks run the projector on a
hand-written ``Record.Created`` plus ``PunchItem.Raised``, ``Cleared`` and ``Reopened``.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType

from sqlalchemy import create_engine, text
from tl_core.modules import load_modules
from tl_core.projection.record import RecordProjector
from tl_mod_quality.names import PUNCH_ITEM, PUNCH_ITEM_TABLE
from tl_mod_quality.projectors import PunchItemProjector

ROOT = Path(__file__).resolve().parents[3]
TESTS = ROOT / "packages" / "tl-schema" / "tests" / "test_quality_schema.py"
STREAM = "01J9Z6Q4W3X2Y1V0T9S8R7Q6P2"

CHECKS = [
    ("type label and offline class draft_only", "test_type_label_and_offline_class"),
    ("table, columns and four indexes in the DDL", "test_table_columns_in_order_and_indexes"),
    ("category enum A, B, C", "test_category_enum_is_a_b_c_default_b"),
    ("workflow moves, Void only terminal, no guard", "test_workflow_moves_and_terminal_state"),
    (
        "numbering P123-PUN-0001, -0002, gap-free",
        "test_numbering_pattern_is_gap_free_and_allocates",
    ),
    ("seven access words", "test_exactly_seven_quality_words_with_their_table_words"),
    (
        "events: type, record_id, feed_policy none",
        "test_every_event_has_a_type_the_record_id_and_feed_policy_none",
    ),
    (
        "valid-time tags on Cleared.at and Verified.at",
        "test_cleared_and_verified_at_are_valid_time_tagged",
    ),
]


def load_tests() -> ModuleType:
    spec = importlib.util.spec_from_file_location("test_quality_schema", TESTS)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def check_module_spec() -> None:
    by_name = {m.name: m for m in load_modules()}
    assert PUNCH_ITEM in by_name["quality"].record_types


def check_projector() -> None:
    from datetime import UTC, datetime

    from tl_core.ledger import Event

    seq = 0

    def event(kind: str, payload: dict[str, object]) -> Event:
        nonlocal seq
        seq += 1
        at = datetime(2026, 12, 1, 9, seq, tzinfo=UTC)
        return Event(
            event_type=kind,
            payload=payload,
            seq=seq,
            event_id=f"EVT{seq:06d}",
            stream_id=STREAM,
            stream_type=PUNCH_ITEM,
            stream_version=seq,
            scope="project:P123",
            actor="user:uma",
            recorded_at=at,
            effective_at=at,
            correlation_id="c",
            causation_id=None,
            source="accept",
            prev_hash=None,
            hash=f"h{seq}",
        )

    engine = create_engine("sqlite://")
    record, punch = RecordProjector(), PunchItemProjector()
    with engine.begin() as conn:
        for stmt in record.ddl("sqlite") + punch.ddl("sqlite"):
            conn.execute(text(stmt))
        feed_policy = {"feed_policy": "none", "record_id": STREAM}
        record.apply(
            conn,
            event(
                "Record.Created",
                {
                    "record_type": PUNCH_ITEM,
                    "key": "P123-PUN-0001",
                    "title": "Guard missing",
                    "description": "",
                    "psets": {},
                },
            ),
        )
        punch.apply(
            conn,
            event(
                "PunchItem.Raised",
                {
                    **feed_policy,
                    "area": "A1",
                    "system": "47-01",
                    "due_on": "2026-12-20",
                    "category": "A",
                    "assignee": "user:rob",
                    "raised_by": "user:uma",
                    "source_id": None,
                },
            ),
        )
        punch.apply(
            conn,
            event(
                "PunchItem.Cleared",
                {
                    **feed_policy,
                    "by": "user:rob",
                    "note": "fitted",
                    "at": "2026-12-02T09:30:00Z",
                },
            ),
        )
        punch.apply(
            conn,
            event(
                "PunchItem.Reopened",
                {
                    **feed_policy,
                    "by": "user:sue",
                    "reason": "loose",
                },
            ),
        )
        row = dict(conn.execute(text(f"SELECT * FROM {PUNCH_ITEM_TABLE}")).mappings().one())
    assert row["cleared_by"] is None and row["cleared_on"] is None and row["clear_note"] is None
    assert row["reopen_count"] == 1 and row["last_reopen_reason"] == "loose", row


def main() -> int:
    tests = load_tests()
    for label, name in CHECKS:
        getattr(tests, name)()
        print(f"PASS {label}")
    check_module_spec()
    print("PASS module spec loads through tl_core.modules")
    check_projector()
    print("PASS projector round trip: raise, clear, reopen (cleared columns null, reopen_count 1)")
    print("S1 ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
