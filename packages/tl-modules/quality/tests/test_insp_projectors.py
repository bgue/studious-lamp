"""The checklist and inspection projectors (P2-INSP S1): events appended through the ledger."""

from __future__ import annotations

from typing import Any

from sqlalchemy import text
from tl_adapters.db import DbTarget, open_uow, rebuild_projections
from tl_core.ledger import NewEvent
from tl_core.util import new_ulid
from tl_mod_quality.names import (
    CHECKLIST,
    CHECKLIST_TABLE,
    INSPECTION,
    INSPECTION_TABLE,
    PUNCH_ITEM_TABLE,
)

SCOPE = "project:P123"
QUESTIONS = [
    {
        "id": "q1",
        "text": "Gauge fitted?",
        "kind": "yes_no_na",
        "required": True,
        "fails_when": "no",
    },
    {"id": "q2", "text": "Pressure", "kind": "number", "required": False, "unit": "bar"},
]


class Stream:
    """One record's stream: ``Record.Created``, then its module events, each its own append."""

    def __init__(self, db: DbTarget, record_type: str, key: str) -> None:
        self.db = db
        self.type = record_type
        self.id = new_ulid()
        self.version = 0
        self.key = key

    def append(self, *events: tuple[str, dict[str, Any]]) -> None:
        new = [NewEvent(event_type=e, payload={"record_id": self.id, **p}) for e, p in events]
        with open_uow(self.db) as uow:
            result = uow.append(
                stream_id=self.id,
                stream_type=self.type,
                scope=SCOPE,
                expected_version=self.version,
                events=new,
                actor="user:uma",
                source="test",
                correlation_id=new_ulid(),
            )
        self.version = result.new_version

    def create(self, *events: tuple[str, dict[str, Any]]) -> None:
        envelope = NewEvent(
            event_type="Record.Created",
            payload={
                "record_type": self.type,
                "key": self.key,
                "title": self.key,
                "description": None,
                "psets": {},
            },
        )
        with open_uow(self.db) as uow:
            result = uow.append(
                stream_id=self.id,
                stream_type=self.type,
                scope=SCOPE,
                expected_version=0,
                events=[
                    envelope,
                    *[
                        NewEvent(event_type=e, payload={"record_id": self.id, **p})
                        for e, p in events
                    ],
                ],
                actor="user:uma",
                source="test",
                correlation_id=new_ulid(),
            )
        self.version = result.new_version


def _row(db: DbTarget, table: str, stream: Stream) -> dict[str, Any]:
    with open_uow(db) as uow:
        found = (
            uow.conn()
            .execute(text(f"SELECT * FROM {table} WHERE id = :id"), {"id": stream.id})
            .mappings()
            .one()
        )
    return dict(found)


def _all(db: DbTarget, table: str) -> list[dict[str, Any]]:
    with open_uow(db) as uow:
        rows = uow.conn().execute(text(f"SELECT * FROM {table} ORDER BY id")).mappings().all()
    return [dict(r) for r in rows]


def _count(db: DbTarget, table: str) -> int:
    with open_uow(db) as uow:
        return int(uow.conn().execute(text(f"SELECT COUNT(*) FROM {table}")).scalar_one())


def _questions(row: dict[str, Any]) -> Any:
    import json

    value = row["questions_json"]
    return json.loads(value) if isinstance(value, str) else value


def _checklist(db: DbTarget) -> Stream:
    chk = Stream(db, CHECKLIST, "P123-CHK-0001")
    chk.create(
        (
            "Checklist.Created",
            {
                "discipline": "piping",
                "questions": QUESTIONS,
                "question_count": 2,
                "version": 1,
                "supersedes_id": None,
            },
        )
    )
    return chk


def test_a_checklist_created_edited_published_retired(db: DbTarget) -> None:
    chk = _checklist(db)
    row = _row(db, CHECKLIST_TABLE, chk)
    assert (row["discipline"], row["checklist_version"], row["question_count"]) == ("piping", 1, 2)
    assert _questions(row) == QUESTIONS
    assert row["published_on"] is None and row["retired_on"] is None

    chk.append(
        (
            "Checklist.Edited",
            {
                "changes": {
                    "discipline": ["piping", "civil"],
                    "questions": [QUESTIONS, QUESTIONS[:1]],
                    "question_count": [2, 1],
                }
            },
        )
    )
    row = _row(db, CHECKLIST_TABLE, chk)
    assert (row["discipline"], row["question_count"]) == ("civil", 1)
    assert _questions(row) == QUESTIONS[:1]

    chk.append(("Checklist.Published", {"published_on": "2026-12-01"}))
    row = _row(db, CHECKLIST_TABLE, chk)
    assert (row["published_on"], row["published_by"]) == ("2026-12-01", "user:uma")
    assert row["retired_on"] is None

    chk.append(("Checklist.Retired", {"retired_on": "2026-12-09"}))
    row = _row(db, CHECKLIST_TABLE, chk)
    assert row["retired_on"] == "2026-12-09" and row["published_on"] == "2026-12-01"
    with open_uow(db) as uow:
        version = (
            uow.conn()
            .execute(text("SELECT version FROM cur_core_record WHERE id = :id"), {"id": chk.id})
            .scalar_one()
        )
    assert version == chk.version == 5


def test_an_edit_of_the_questions_alone_recounts_them(db: DbTarget) -> None:
    chk = _checklist(db)
    chk.append(("Checklist.Edited", {"changes": {"questions": [QUESTIONS, QUESTIONS * 2]}}))
    assert _row(db, CHECKLIST_TABLE, chk)["question_count"] == 4


def _planned(db: DbTarget) -> Stream:
    ins = Stream(db, INSPECTION, "P123-INS-0001")
    ins.create(
        (
            "Inspection.Planned",
            {
                "subject_id": None,
                "for_iwp_id": None,
                "point": "hold",
                "area": "A1",
                "planned_on": "2026-12-05",
                "reinspection_of_id": None,
            },
        )
    )
    return ins


def _scheduled(day: str, version: int, checklist: str) -> tuple[str, dict[str, Any]]:
    return (
        "Inspection.Scheduled",
        {
            "checklist_id": checklist,
            "checklist_version": version,
            "scheduled_for": day,
            "inspector": "user:ian",
        },
    )


def test_an_inspection_planned_scheduled_rescheduled_recorded_verified(db: DbTarget) -> None:
    chk = _checklist(db)
    ins = _planned(db)
    row = _row(db, INSPECTION_TABLE, ins)
    assert (row["point"], row["area"], row["planned_on"], row["punch_count"]) == (
        "hold",
        "A1",
        "2026-12-05",
        0,
    )
    assert row["checklist_id"] is None and row["result"] is None and row["scheduled_for"] is None

    ins.append(_scheduled("2026-12-06", 1, chk.id))
    row = _row(db, INSPECTION_TABLE, ins)
    assert (row["checklist_id"], row["checklist_version"], row["scheduled_for"]) == (
        chk.id,
        1,
        "2026-12-06",
    )
    ins.append(_scheduled("2026-12-08", 2, chk.id))
    row = _row(db, INSPECTION_TABLE, ins)
    assert (row["checklist_version"], row["scheduled_for"], row["inspector"]) == (
        2,
        "2026-12-08",
        "user:ian",
    )

    answers = [{"q": "q1", "value": "no", "note": "loose"}]
    ins.append(
        (
            "Inspection.ResultRecorded",
            {
                "answers": answers,
                "result": "reject",
                "done_at": "2026-12-08T10:00:00Z",
                "note": "see punch",
                "punch_item_ids": [new_ulid(), new_ulid()],
            },
        )
    )
    row = _row(db, INSPECTION_TABLE, ins)
    assert (row["result"], row["note"], row["recorded_by"], row["punch_count"]) == (
        "reject",
        "see punch",
        "user:uma",
        2,
    )
    assert row["done_at"] is not None and "2026-12-08" in str(row["done_at"])
    import json

    held = row["answers_json"]
    assert (json.loads(held) if isinstance(held, str) else held) == answers
    assert row["verified_on"] is None

    ins.append(("Inspection.Verified", {"verified_on": "2026-12-09"}))
    row = _row(db, INSPECTION_TABLE, ins)
    assert (row["verified_on"], row["verified_by"]) == ("2026-12-09", "user:uma")
    assert row["punch_count"] == 2


def test_an_inspection_cancelled_from_planned(db: DbTarget) -> None:
    ins = _planned(db)
    ins.append(("Inspection.Cancelled", {"reason": "Work moved"}))
    row = _row(db, INSPECTION_TABLE, ins)
    assert row["cancel_reason"] == "Work moved" and row["result"] is None


def test_rebuild_equals_the_live_rows_and_the_punch_table_is_untouched(db: DbTarget) -> None:
    chk = _checklist(db)
    chk.append(("Checklist.Published", {"published_on": "2026-12-01"}))
    ins = _planned(db)
    ins.append(_scheduled("2026-12-06", 1, chk.id))
    ins.append(
        (
            "Inspection.ResultRecorded",
            {
                "answers": [],
                "result": "accept",
                "done_at": "2026-12-06T10:00:00Z",
                "note": None,
                "punch_item_ids": [],
            },
        )
    )
    other = Stream(db, INSPECTION, "P123-INS-0002")
    other.create(
        (
            "Inspection.Planned",
            {
                "subject_id": None,
                "for_iwp_id": None,
                "point": "witness",
                "area": None,
                "planned_on": None,
                "reinspection_of_id": ins.id,
            },
        )
    )
    other.append(("Inspection.Cancelled", {"reason": "dup"}))
    tables = (CHECKLIST_TABLE, INSPECTION_TABLE, "cur_core_record")
    before = [_all(db, t) for t in tables]
    assert len(before[0]) == 1 and len(before[1]) == 2
    rebuild_projections(db)
    assert before == [_all(db, t) for t in tables]
    assert _count(db, PUNCH_ITEM_TABLE) == 0
