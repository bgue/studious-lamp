"""ChecklistProjector: ``Checklist.Created`` and the events after it.

``Record.Created`` makes the envelope row (``RecordProjector``); ``Checklist.Created`` follows in
the same append and makes this module's row. The workflow state is the envelope ``status``.
``question_count`` is set from the payload (the length of the list when an event omits it).
"""

from __future__ import annotations

import json
from typing import Any

from sqlalchemy import Connection, text
from tl_core.ledger import Event

from tl_mod_quality.names import (
    CHECKLIST_CREATED,
    CHECKLIST_EDITED,
    CHECKLIST_EVENTS,
    CHECKLIST_PUBLISHED,
    CHECKLIST_RETIRED,
    CHECKLIST_TABLE,
    CHECKLIST_VIEW,
)
from tl_mod_quality.projectors._common import ddl_for, require_row, touch_record

#: The columns an ``Edited`` event may change (the title lives on the envelope).
EDITABLE = ("discipline", "questions", "question_count", "supersedes_id")

_INSERT = text(
    f"INSERT INTO {CHECKLIST_TABLE} (id, scope, discipline, checklist_version, questions_json, "
    "question_count, supersedes_id, last_seq) VALUES (:id, :scope, :discipline, "
    ":checklist_version, :questions_json, :question_count, :supersedes_id, :last_seq)"
)
_PUBLISH = text(
    f"UPDATE {CHECKLIST_TABLE} SET published_by = :by, published_on = :on, last_seq = :last_seq "
    "WHERE id = :id"
)
_RETIRE = text(
    f"UPDATE {CHECKLIST_TABLE} SET retired_on = :on, last_seq = :last_seq WHERE id = :id"
)


def dump_json(value: Any) -> str:
    """The text of a JSON column cell: canonical, so a rebuild writes the same bytes."""
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


class ChecklistProjector:
    name = "quality_checklist"
    handles = CHECKLIST_EVENTS

    def ddl(self, dialect: str) -> list[str]:
        return ddl_for(CHECKLIST_TABLE, dialect) + ddl_for(CHECKLIST_VIEW, dialect)

    def apply(self, conn: Connection, event: Event) -> None:
        payload: dict[str, Any] = event.payload
        kind = event.event_type
        if kind == CHECKLIST_CREATED:
            questions = payload.get("questions") or []
            count = payload.get("question_count")
            conn.execute(
                _INSERT,
                {
                    "id": event.stream_id,
                    "scope": event.scope,
                    "discipline": payload.get("discipline"),
                    "checklist_version": payload.get("version") or 1,
                    "questions_json": dump_json(questions),
                    "question_count": len(questions) if count is None else count,
                    "supersedes_id": payload.get("supersedes_id"),
                    "last_seq": event.seq,
                },
            )
        else:
            done = self._update(conn, event, kind, payload)
            require_row(done, CHECKLIST_TABLE, event)
        touch_record(conn, event)

    @staticmethod
    def _update(conn: Connection, event: Event, kind: str, payload: dict[str, Any]) -> int:
        base: dict[str, Any] = {"id": event.stream_id, "last_seq": event.seq}
        if kind == CHECKLIST_EDITED:
            changes: dict[str, Any] = payload["changes"]
            params: dict[str, Any] = {}
            for column in EDITABLE:
                if column in changes:
                    params[column] = changes[column][1]
            sets: dict[str, str] = {c: c for c in params if c != "questions"}
            if "questions" in params:
                questions = params.pop("questions") or []
                params["questions_json"] = dump_json(questions)
                sets["questions"] = "questions_json"
                if "question_count" not in params:
                    params["question_count"] = len(questions)
                    sets["question_count"] = "question_count"
            clause = "".join(f"{column} = :{column}, " for column in sets.values())
            stmt = text(f"UPDATE {CHECKLIST_TABLE} SET {clause}last_seq = :last_seq WHERE id = :id")
            return conn.execute(stmt, {**base, **params}).rowcount
        if kind == CHECKLIST_PUBLISHED:
            params = {"by": event.actor, "on": payload["published_on"]}
            return conn.execute(_PUBLISH, {**base, **params}).rowcount
        if kind == CHECKLIST_RETIRED:
            return conn.execute(_RETIRE, {**base, "on": payload["retired_on"]}).rowcount
        raise ValueError(f"ChecklistProjector cannot apply event type: {kind}")

    def reset(self, conn: Connection) -> None:
        conn.execute(text(f"DELETE FROM {CHECKLIST_TABLE}"))
