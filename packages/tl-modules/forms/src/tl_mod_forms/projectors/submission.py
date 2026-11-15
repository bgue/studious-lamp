"""SubmissionProjector: ``DraftSaved`` or ``Submitted`` makes the row; later events change it.

``Record.Created`` makes the envelope row (``RecordProjector``). A submission's own stream starts
with ``Submission.DraftSaved`` (a saved draft) or ``Submission.Submitted`` (a form submitted with no
draft before it), so both insert the row when no row exists. ``draft_saves`` is ``save_no`` of the
last ``DraftSaved``. A review or a void is a system act: the actor and the day it was recorded are
the fact (ADR-0026).
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import Connection, text
from tl_core.ledger import Event

from tl_mod_forms.names import (
    SUBMISSION_ACCEPTED,
    SUBMISSION_DRAFT_DISCARDED,
    SUBMISSION_DRAFT_SAVED,
    SUBMISSION_EVENTS,
    SUBMISSION_RETURNED,
    SUBMISSION_SUBMITTED,
    SUBMISSION_TABLE,
    SUBMISSION_VIEW,
    SUBMISSION_VOIDED,
)
from tl_mod_forms.projectors._common import (
    day_of,
    ddl_for,
    dump_json,
    require_row,
    touch_record,
)

_EXISTS = text(f"SELECT 1 FROM {SUBMISSION_TABLE} WHERE id = :id")
_INSERT = text(
    f"INSERT INTO {SUBMISSION_TABLE} (id, scope, template_id, template_version, template_hash, "
    "subject_id, answers_json, answer_class, draft_saves, author, submitted_on, last_seq) "
    "VALUES (:id, :scope, :template_id, :template_version, :template_hash, :subject_id, "
    ":answers_json, :answer_class, :draft_saves, :author, :submitted_on, :last_seq)"
)
_SAVE = text(
    f"UPDATE {SUBMISSION_TABLE} SET template_id = :template_id, template_version = "
    ":template_version, template_hash = :template_hash, subject_id = :subject_id, "
    "answers_json = :answers_json, answer_class = :answer_class, draft_saves = :draft_saves, "
    "last_seq = :last_seq WHERE id = :id"
)
_SUBMIT = text(
    f"UPDATE {SUBMISSION_TABLE} SET template_id = :template_id, template_version = "
    ":template_version, template_hash = :template_hash, subject_id = :subject_id, "
    "answers_json = :answers_json, answer_class = :answer_class, submitted_on = :submitted_on, "
    "last_seq = :last_seq WHERE id = :id"
)
_REVIEW = text(
    f"UPDATE {SUBMISSION_TABLE} SET reviewed_by = :by, reviewed_on = :on, review_note = :note, "
    "last_seq = :last_seq WHERE id = :id"
)
_VOID = text(
    f"UPDATE {SUBMISSION_TABLE} SET void_reason = :reason, last_seq = :last_seq WHERE id = :id"
)
_TOUCH = text(f"UPDATE {SUBMISSION_TABLE} SET last_seq = :last_seq WHERE id = :id")


def _content(event: Event) -> dict[str, Any]:
    p: dict[str, Any] = event.payload
    return {
        "template_id": p.get("template_id"),
        "template_version": p.get("template_version"),
        "template_hash": p.get("template_hash"),
        "subject_id": p.get("subject_id"),
        "answers_json": dump_json(p.get("answers") or []),
        "answer_class": p.get("answer_class"),
    }


class SubmissionProjector:
    name = "forms_submission"
    handles = SUBMISSION_EVENTS

    def ddl(self, dialect: str) -> list[str]:
        return ddl_for(SUBMISSION_TABLE, dialect) + ddl_for(SUBMISSION_VIEW, dialect)

    def apply(self, conn: Connection, event: Event) -> None:
        kind = event.event_type
        base: dict[str, Any] = {"id": event.stream_id, "last_seq": event.seq}
        payload: dict[str, Any] = event.payload
        if kind in (SUBMISSION_DRAFT_SAVED, SUBMISSION_SUBMITTED):
            exists = conn.execute(_EXISTS, {"id": event.stream_id}).first() is not None
            saved = kind == SUBMISSION_DRAFT_SAVED
            if not exists:
                conn.execute(
                    _INSERT,
                    {
                        **base,
                        **_content(event),
                        "scope": event.scope,
                        "draft_saves": payload["save_no"] if saved else 0,
                        "author": event.actor,
                        "submitted_on": None if saved else payload["submitted_on"],
                    },
                )
            elif saved:
                conn.execute(_SAVE, {**base, **_content(event), "draft_saves": payload["save_no"]})
            else:
                conn.execute(
                    _SUBMIT, {**base, **_content(event), "submitted_on": payload["submitted_on"]}
                )
        else:
            done = self._update(conn, event, kind, base)
            require_row(done, SUBMISSION_TABLE, event)
        touch_record(conn, event)

    @staticmethod
    def _update(conn: Connection, event: Event, kind: str, base: dict[str, Any]) -> int:
        payload: dict[str, Any] = event.payload
        if kind in (SUBMISSION_ACCEPTED, SUBMISSION_RETURNED):
            params = {"by": event.actor, "on": day_of(event), "note": payload.get("note")}
            return conn.execute(_REVIEW, {**base, **params}).rowcount
        if kind == SUBMISSION_VOIDED:
            return conn.execute(_VOID, {**base, "reason": payload["reason"]}).rowcount
        if kind == SUBMISSION_DRAFT_DISCARDED:
            return conn.execute(_TOUCH, base).rowcount
        raise ValueError(f"SubmissionProjector cannot apply event type: {kind}")

    def reset(self, conn: Connection) -> None:
        conn.execute(text(f"DELETE FROM {SUBMISSION_TABLE}"))
