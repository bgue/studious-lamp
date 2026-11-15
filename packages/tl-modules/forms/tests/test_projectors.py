"""The forms projectors (P2-FORMS S2): events go through the ledger, never a projection write."""

from __future__ import annotations

import json
from typing import Any

from sqlalchemy import text
from tl_adapters.db import DbTarget, open_uow, rebuild_projections
from tl_core.ledger import NewEvent
from tl_core.util import new_ulid
from tl_mod_forms.names import (
    INTAKE_CODE,
    INTAKE_CODE_TABLE,
    INTAKE_ITEM,
    INTAKE_ITEM_TABLE,
    SUBMISSION,
    SUBMISSION_TABLE,
    TEMPLATE,
    TEMPLATE_TABLE,
)

SCOPE = "project:P123"
HASH = "ab" * 32
HASH2 = "cd" * 32
FIELDS = [
    {
        "id": "q1",
        "text": "Guard fitted?",
        "kind": "yes_no_na",
        "required": True,
        "unit": None,
        "min": None,
        "max": None,
        "choices": None,
        "fails_when": "no",
    }
]
ANSWERS = [{"q": "q1", "value": "yes", "note": None}]


class Stream:
    """One record's stream: ``Record.Created``, then its module events, each its own append."""

    def __init__(self, db: DbTarget, record_type: str, key: str, scope: str = SCOPE) -> None:
        self.db, self.type, self.key, self.scope = db, record_type, key, scope
        self.id = new_ulid()
        self.version = 0

    def _append(self, events: list[NewEvent], actor: str) -> None:
        with open_uow(self.db) as uow:
            result = uow.append(
                stream_id=self.id,
                stream_type=self.type,
                scope=self.scope,
                expected_version=self.version,
                events=events,
                actor=actor,
                source="test",
                correlation_id=new_ulid(),
            )
        self.version = result.new_version

    def _new(self, events: tuple[tuple[str, dict[str, Any]], ...]) -> list[NewEvent]:
        return [
            NewEvent(event_type=e, payload={"record_id": self.id, **p, "feed_policy": "none"})
            for e, p in events
        ]

    def append(self, *events: tuple[str, dict[str, Any]], actor: str = "user:uma") -> None:
        self._append(self._new(events), actor)

    def create(self, *events: tuple[str, dict[str, Any]], actor: str = "user:uma") -> None:
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
        self._append([envelope, *self._new(events)], actor)


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


def _json(row: dict[str, Any], column: str) -> Any:
    value = row[column]
    return json.loads(value) if isinstance(value, str) else value


def _status_version(db: DbTarget, stream: Stream) -> int:
    with open_uow(db) as uow:
        return int(
            uow.conn()
            .execute(text("SELECT version FROM cur_core_record WHERE id = :id"), {"id": stream.id})
            .scalar_one()
        )


# ---- templates -------------------------------------------------------------------------------


def _template(db: DbTarget, **over: Any) -> Stream:
    t = Stream(db, TEMPLATE, "TPL-0001", "company")
    payload: dict[str, Any] = {
        "format_version": 2,
        "form_fields": FIELDS,
        "field_count": 1,
        "version": 1,
        "supersedes_id": None,
        "bound_record_type": None,
        "answer_class": None,
        "intake": None,
        "purpose": None,
        "accepts_as": None,
    }
    t.create(("Template.Created", {**payload, **over}))
    return t


def test_a_template_created_edited_published_retired(db: DbTarget) -> None:
    t = _template(db, bound_record_type="quality.Inspection", answer_class="restricted")
    row = _row(db, TEMPLATE_TABLE, t)
    assert (row["template_version"], row["format_version"], row["field_count"]) == (1, 2, 1)
    assert _json(row, "form_fields_json") == FIELDS
    assert (row["bound_record_type"], row["answer_class"]) == ("quality.Inspection", "restricted")
    assert row["intake"] is None and row["accepts_as_json"] is None
    assert row["content_hash"] is None and row["published_on"] is None
    assert row["scope"] == "company"

    t.append(
        (
            "Template.Edited",
            {"changes": {"form_fields": [FIELDS, FIELDS * 2], "bound_record_type": ["x", None]}},
        )
    )
    row = _row(db, TEMPLATE_TABLE, t)
    assert row["field_count"] == 2 and _json(row, "form_fields_json") == FIELDS * 2
    assert row["bound_record_type"] is None

    t.append(("Template.Published", {"published_on": "2026-12-01", "content_hash": HASH}))
    row = _row(db, TEMPLATE_TABLE, t)
    assert (row["published_on"], row["content_hash"], row["retired_on"]) == (
        "2026-12-01",
        HASH,
        None,
    )

    t.append(("Template.Retired", {"retired_on": "2026-12-09"}))
    row = _row(db, TEMPLATE_TABLE, t)
    assert row["retired_on"] == "2026-12-09" and row["published_on"] == "2026-12-01"
    assert _status_version(db, t) == t.version == 5


def test_a_public_template_keeps_its_intake_profile(db: DbTarget) -> None:
    t = _template(db, intake="public", purpose="sign_on", accepts_as=["SubmitForm"])
    row = _row(db, TEMPLATE_TABLE, t)
    assert (row["intake"], row["purpose"]) == ("public", "sign_on")
    assert _json(row, "accepts_as_json") == ["SubmitForm"]


# ---- submissions -----------------------------------------------------------------------------


def _content(**over: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "template_id": new_ulid(),
        "template_version": 1,
        "template_hash": HASH,
        "subject_id": None,
        "answers": ANSWERS,
        "answer_class": "restricted",
    }
    return {**base, **over}


def _saved(n: int, **over: Any) -> tuple[str, dict[str, Any]]:
    return ("Submission.DraftSaved", {**_content(**over), "save_no": n})


def _submitted(**over: Any) -> tuple[str, dict[str, Any]]:
    return ("Submission.Submitted", {**_content(**over), "submitted_on": "2026-12-02"})


def _draft(db: DbTarget, key: str = "P123-FRM-0001") -> Stream:
    s = Stream(db, SUBMISSION, key)
    s.create(_saved(1, subject_id="SUBJ"))
    return s


def test_a_draft_saved_twice_submitted_and_accepted(db: DbTarget) -> None:
    s = _draft(db)
    row = _row(db, SUBMISSION_TABLE, s)
    assert (row["draft_saves"], row["author"], row["subject_id"]) == (1, "user:uma", "SUBJ")
    assert row["submitted_on"] is None and _json(row, "answers_json") == ANSWERS

    more = [{"q": "q1", "value": "no", "note": "loose"}]
    s.append(_saved(2, answers=more, template_hash=HASH2), actor="user:ian")
    row = _row(db, SUBMISSION_TABLE, s)
    assert row["draft_saves"] == 2 and _json(row, "answers_json") == more
    assert row["template_hash"] == HASH2 and row["author"] == "user:uma"

    s.append(_submitted(answers=more, template_hash=HASH2, subject_id="SUBJ"))
    row = _row(db, SUBMISSION_TABLE, s)
    assert (row["submitted_on"], row["draft_saves"], row["template_hash"]) == (
        "2026-12-02",
        2,
        HASH2,
    )
    assert row["reviewed_by"] is None

    s.append(("Submission.Accepted", {"note": "good"}), actor="user:sue")
    row = _row(db, SUBMISSION_TABLE, s)
    assert (row["reviewed_by"], row["review_note"], row["void_reason"]) == (
        "user:sue",
        "good",
        None,
    )
    assert row["reviewed_on"] is not None and len(str(row["reviewed_on"])) == 10
    assert _status_version(db, s) == s.version == 5


def test_a_submission_with_no_draft_before_it(db: DbTarget) -> None:
    s = Stream(db, SUBMISSION, "P123-FRM-0002")
    s.create(_submitted())
    row = _row(db, SUBMISSION_TABLE, s)
    assert (row["draft_saves"], row["submitted_on"], row["author"]) == (0, "2026-12-02", "user:uma")
    assert row["template_hash"] == HASH and row["answer_class"] == "restricted"
    assert _json(row, "answers_json") == ANSWERS


def test_a_draft_discarded(db: DbTarget) -> None:
    s = _draft(db)
    s.append(("Submission.DraftDiscarded", {}))
    row = _row(db, SUBMISSION_TABLE, s)
    assert row["draft_saves"] == 1 and row["last_seq"] > 0
    assert _status_version(db, s) == s.version == 3


def test_returned_then_submitted_again(db: DbTarget) -> None:
    s = Stream(db, SUBMISSION, "P123-FRM-0003")
    s.create(_submitted())
    s.append(("Submission.Returned", {"note": "Section 2 unclear"}), actor="user:sue")
    row = _row(db, SUBMISSION_TABLE, s)
    assert (row["reviewed_by"], row["review_note"]) == ("user:sue", "Section 2 unclear")
    fixed = [{"q": "q1", "value": "no", "note": "fixed"}]
    s.append(_submitted(answers=fixed))
    row = _row(db, SUBMISSION_TABLE, s)
    assert _json(row, "answers_json") == fixed and row["draft_saves"] == 0


def test_a_submission_voided(db: DbTarget) -> None:
    s = Stream(db, SUBMISSION, "P123-FRM-0004")
    s.create(_submitted())
    s.append(("Submission.Voided", {"reason": "Wrong form"}), actor="user:sue")
    row = _row(db, SUBMISSION_TABLE, s)
    assert row["void_reason"] == "Wrong form" and row["reviewed_by"] is None


# ---- intake ----------------------------------------------------------------------------------


def _issued(db: DbTarget, key: str, code_hash: str) -> Stream:
    c = Stream(db, INTAKE_CODE, key)
    c.create(
        (
            "IntakeCode.Issued",
            {
                "code_hash": code_hash,
                "template_id": new_ulid(),
                "template_version": 1,
                "template_hash": HASH,
                "context_id": new_ulid(),
                "context_type": "engineering.Tag",
                "heading": "Scaffold request",
                "controller_role": "controller",
                "expires_on": "2027-01-31",
            },
        )
    )
    return c


def test_an_intake_code_issued_and_revoked(db: DbTarget) -> None:
    c = _issued(db, "IC-1", HASH)
    row = _row(db, INTAKE_CODE_TABLE, c)
    assert (row["code_hash"], row["heading"], row["controller_role"]) == (
        HASH,
        "Scaffold request",
        "controller",
    )
    assert (row["issued_by"], str(row["expires_on"])) == ("user:uma", "2027-01-31")
    assert row["issued_at"] is not None and row["revoked_at"] is None
    c.append(("IntakeCode.Revoked", {"reason": "Label lost"}), actor="user:sue")
    row = _row(db, INTAKE_CODE_TABLE, c)
    assert row["revoked_by"] == "user:sue" and row["revoked_at"] is not None
    assert row["code_hash"] == HASH
    assert _status_version(db, c) == 3


def _received(db: DbTarget, key: str) -> Stream:
    i = Stream(db, INTAKE_ITEM, key)
    i.create(
        (
            "IntakeItem.Received",
            {
                "item_id": i.id,
                "code_id": new_ulid(),
                "template_id": new_ulid(),
                "template_version": 1,
                "template_hash": HASH,
                "body_mac": HASH2,
                "body_bytes": 120,
                "received_at": "2026-12-01T09:00:00Z",
            },
        ),
        actor="svc:intake",
    )
    return i


def test_an_intake_item_received_and_accepted_with_a_claim(db: DbTarget) -> None:
    i = _received(db, "II-1")
    row = _row(db, INTAKE_ITEM_TABLE, i)
    assert (row["body_mac"], row["body_bytes"]) == (HASH2, 120)
    assert "2026-12-01" in str(row["received_at"])
    assert row["accepted_as"] is None and row["on_behalf_of_claim_json"] is None
    claim = {"name": "Sam", "company": "Acme"}
    i.append(
        (
            "IntakeItem.Accepted",
            {"accepted_as": "SubmitForm", "on_behalf_of_claim": claim, "cause_event_id": None},
        ),
        actor="user:sue",
    )
    row = _row(db, INTAKE_ITEM_TABLE, i)
    assert (row["accepted_as"], row["accepted_by"]) == ("SubmitForm", "user:sue")
    assert _json(row, "on_behalf_of_claim_json") == claim
    assert row["accepted_on"] is not None and row["rejected_reason"] is None


def test_an_intake_item_received_rejected_and_purged(db: DbTarget) -> None:
    i = _received(db, "II-2")
    i.append(("IntakeItem.Rejected", {"reason": "spam"}), actor="user:sue")
    row = _row(db, INTAKE_ITEM_TABLE, i)
    assert (row["rejected_reason"], row["rejected_by"]) == ("spam", "user:sue")
    assert row["purged_at"] is None
    i.append(("IntakeItem.Purged", {"purged_at": "2026-12-31T00:00:00Z"}), actor="svc:intake")
    row = _row(db, INTAKE_ITEM_TABLE, i)
    assert "2026-12-31" in str(row["purged_at"]) and row["rejected_reason"] == "spam"
    assert row["body_mac"] == HASH2  # the item keeps its MAC; only the body table loses the text


# ---- rebuild ---------------------------------------------------------------------------------


def test_a_rebuild_of_every_table_equals_the_live_rows(db: DbTarget) -> None:
    t = _template(db)
    t.append(("Template.Published", {"published_on": "2026-12-01", "content_hash": HASH}))
    s = _draft(db)
    s.append(_saved(2))
    s.append(_submitted())
    s.append(("Submission.Accepted", {"note": None}), actor="user:sue")
    direct = Stream(db, SUBMISSION, "P123-FRM-0009")
    direct.create(_submitted())
    direct.append(("Submission.Voided", {"reason": "dup"}))
    gone = _draft(db, "P123-FRM-0010")
    gone.append(("Submission.DraftDiscarded", {}))
    c = _issued(db, "IC-9", HASH)
    c.append(("IntakeCode.Revoked", {"reason": "done"}))
    a, b = _received(db, "II-9"), _received(db, "II-10")
    a.append(
        (
            "IntakeItem.Accepted",
            {"accepted_as": "SubmitForm", "on_behalf_of_claim": None, "cause_event_id": None},
        )
    )
    b.append(("IntakeItem.Rejected", {"reason": "unclear"}))
    b.append(("IntakeItem.Purged", {"purged_at": "2026-12-31T00:00:00Z"}))
    tables = (TEMPLATE_TABLE, SUBMISSION_TABLE, INTAKE_CODE_TABLE, INTAKE_ITEM_TABLE)
    before = [_all(db, t) for t in (*tables, "cur_core_record")]
    assert [len(x) for x in before[:4]] == [1, 3, 1, 2]
    rebuild_projections(db)
    assert before == [_all(db, t) for t in (*tables, "cur_core_record")]
