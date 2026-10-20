"""TechnicalProjector: the ``Technical.*`` events into ``cur_correspondence_technical_item``.

``Defined`` inserts the domain row of an RFI, a technical query or a deviation request (the item row
is written by ``CorrespondenceProjector`` from the ``Correspondence.Defined`` event of the same
append); ``Updated`` changes the raiser's fields; ``Answered`` records the answer; ``Reviewed``
records the raiser's judgement of it; ``Reissued`` clears the answer and the judgement of the round
before (the events keep them). Deterministic: a row depends only on the events of its stream.
Register it after ``RecordProjector``.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import Connection, text
from tl_core.ledger import Event

from tl_mod_correspondence.names import (
    TECH_ANSWERED,
    TECH_DEFINED,
    TECH_REISSUED,
    TECH_REVIEWED,
    TECH_UPDATED,
    TECHNICAL_TABLE,
    TECHNICAL_VIEW,
)
from tl_mod_correspondence.projectors._common import ddl_for, touch_record

#: Fields a ``Technical.Updated`` may change. The name is both the payload key and the column.
_UPDATABLE = (
    "question",
    "proposed_solution",
    "discipline",
    "required_by",
    "potential_cost_impact",
    "potential_schedule_impact",
)


class TechnicalProjector:
    name = "correspondence_technical"
    handles = frozenset({TECH_DEFINED, TECH_UPDATED, TECH_ANSWERED, TECH_REVIEWED, TECH_REISSUED})

    def ddl(self, dialect: str) -> list[str]:
        return ddl_for(TECHNICAL_TABLE, dialect) + ddl_for(TECHNICAL_VIEW, dialect)

    def apply(self, conn: Connection, event: Event) -> None:
        p = event.payload
        et = event.event_type
        if et == TECH_DEFINED:
            conn.execute(
                text(
                    f"INSERT INTO {TECHNICAL_TABLE} (id, scope, question, proposed_solution, "
                    "discipline, required_by, potential_cost_impact, potential_schedule_impact, "
                    "last_seq) VALUES (:id, :scope, :question, :proposed_solution, :discipline, "
                    ":required_by, :potential_cost_impact, :potential_schedule_impact, :last_seq)"
                ),
                {
                    "id": event.stream_id,
                    "scope": event.scope,
                    "question": p["question"],
                    "proposed_solution": p.get("proposed_solution"),
                    "discipline": p.get("discipline"),
                    "required_by": p.get("required_by"),
                    "potential_cost_impact": p["potential_cost_impact"],
                    "potential_schedule_impact": p["potential_schedule_impact"],
                    "last_seq": event.seq,
                },
            )
        elif et == TECH_UPDATED:
            changes: dict[str, Any] = p.get("changes") or {}
            columns = [name for name in _UPDATABLE if name in changes]
            self._update(
                conn, event, [f"{c} = :{c}" for c in columns], {c: changes[c][1] for c in columns}
            )
        elif et == TECH_ANSWERED:
            self._update(
                conn,
                event,
                [
                    "answer = :answer",
                    "answered_on = :answered_on",
                    "answer_cost_impact = :cost",
                    "answer_schedule_impact = :schedule",
                    "answer_item_id = :answer_item_id",
                    "answering_revision_id = :answering_revision_id",
                ],
                {
                    "answer": p["answer"],
                    "answered_on": p["answered_on"],
                    "cost": p["cost_impact"],
                    "schedule": p["schedule_impact"],
                    "answer_item_id": p.get("answer_item_id"),
                    "answering_revision_id": p.get("answering_revision_id"),
                },
            )
        elif et == TECH_REVIEWED:
            self._update(
                conn,
                event,
                [
                    "review_decision = :decision",
                    "reviewed_on = :reviewed_on",
                    "review_note = :note",
                ],
                {
                    "decision": p["decision"],
                    "reviewed_on": p["reviewed_on"],
                    "note": p.get("note"),
                },
            )
        elif et == TECH_REISSUED:
            self._update(
                conn,
                event,
                [
                    "answer = NULL",
                    "answered_on = NULL",
                    "answer_cost_impact = NULL",
                    "answer_schedule_impact = NULL",
                    "answer_item_id = NULL",
                    "answering_revision_id = NULL",
                    "review_decision = NULL",
                    "reviewed_on = NULL",
                    "review_note = NULL",
                ],
                {},
            )
        else:
            raise ValueError(f"TechnicalProjector cannot apply event type: {et}")
        touch_record(conn, event)

    @staticmethod
    def _update(
        conn: Connection, event: Event, assignments: list[str], values: dict[str, Any]
    ) -> None:
        # The assignments name columns of this module only; values are bound parameters.
        sets = ", ".join([*assignments, "last_seq = :last_seq"])
        result = conn.execute(
            text(f"UPDATE {TECHNICAL_TABLE} SET {sets} WHERE id = :id"),
            {"id": event.stream_id, "last_seq": event.seq, **values},
        )
        if result.rowcount == 0:
            raise LookupError(f"no {TECHNICAL_TABLE} row for stream {event.stream_id}")

    def reset(self, conn: Connection) -> None:
        conn.execute(text(f"DELETE FROM {TECHNICAL_TABLE}"))
