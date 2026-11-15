"""TemplateProjector: ``Template.Created`` and the events after it.

``Record.Created`` makes the envelope row (``RecordProjector``); ``Template.Created`` follows in the
same append and makes this module's row. The workflow state is the envelope ``status``.
``field_count`` is set from the payload (the length of the list when an event omits it).
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import Connection, text
from tl_core.ledger import Event

from tl_mod_forms.names import (
    TEMPLATE_CREATED,
    TEMPLATE_EDITED,
    TEMPLATE_EVENTS,
    TEMPLATE_PUBLISHED,
    TEMPLATE_RETIRED,
    TEMPLATE_TABLE,
    TEMPLATE_VIEW,
)
from tl_mod_forms.projectors._common import ddl_for, dump_json, require_row, touch_record

#: The fields an ``Edited`` event may change, and the column each is written to.
EDITABLE: dict[str, str] = {
    "format_version": "format_version",
    "form_fields": "form_fields_json",
    "field_count": "field_count",
    "bound_record_type": "bound_record_type",
    "answer_class": "answer_class",
    "intake": "intake",
    "purpose": "purpose",
    "accepts_as": "accepts_as_json",
    "supersedes_id": "supersedes_id",
}
_JSON = frozenset({"form_fields", "accepts_as"})

_INSERT = text(
    f"INSERT INTO {TEMPLATE_TABLE} (id, scope, template_version, format_version, form_fields_json, "
    "field_count, supersedes_id, bound_record_type, answer_class, intake, purpose, "
    "accepts_as_json, last_seq) VALUES (:id, :scope, :template_version, :format_version, "
    ":form_fields_json, :field_count, :supersedes_id, :bound_record_type, :answer_class, "
    ":intake, :purpose, :accepts_as_json, :last_seq)"
)
_PUBLISH = text(
    f"UPDATE {TEMPLATE_TABLE} SET published_on = :on, content_hash = :content_hash, "
    "last_seq = :last_seq WHERE id = :id"
)
_RETIRE = text(f"UPDATE {TEMPLATE_TABLE} SET retired_on = :on, last_seq = :last_seq WHERE id = :id")


class TemplateProjector:
    name = "forms_template"
    handles = TEMPLATE_EVENTS

    def ddl(self, dialect: str) -> list[str]:
        return ddl_for(TEMPLATE_TABLE, dialect) + ddl_for(TEMPLATE_VIEW, dialect)

    def apply(self, conn: Connection, event: Event) -> None:
        payload: dict[str, Any] = event.payload
        kind = event.event_type
        if kind == TEMPLATE_CREATED:
            fields = payload.get("form_fields") or []
            count = payload.get("field_count")
            conn.execute(
                _INSERT,
                {
                    "id": event.stream_id,
                    "scope": event.scope,
                    "template_version": payload.get("version") or 1,
                    "format_version": payload.get("format_version") or 1,
                    "form_fields_json": dump_json(fields),
                    "field_count": len(fields) if count is None else count,
                    "supersedes_id": payload.get("supersedes_id"),
                    "bound_record_type": payload.get("bound_record_type"),
                    "answer_class": payload.get("answer_class"),
                    "intake": payload.get("intake"),
                    "purpose": payload.get("purpose"),
                    "accepts_as_json": dump_json(payload.get("accepts_as")),
                    "last_seq": event.seq,
                },
            )
        else:
            done = self._update(conn, event, kind, payload)
            require_row(done, TEMPLATE_TABLE, event)
        touch_record(conn, event)

    @staticmethod
    def _update(conn: Connection, event: Event, kind: str, payload: dict[str, Any]) -> int:
        base: dict[str, Any] = {"id": event.stream_id, "last_seq": event.seq}
        if kind == TEMPLATE_EDITED:
            changes: dict[str, Any] = payload["changes"]
            params: dict[str, Any] = {}
            for field, column in EDITABLE.items():
                if field in changes:
                    value = changes[field][1]
                    params[column] = dump_json(value) if field in _JSON else value
            if "form_fields" in changes and "field_count" not in changes:
                params["field_count"] = len(changes["form_fields"][1] or [])
            clause = "".join(f"{column} = :{column}, " for column in params)
            stmt = text(f"UPDATE {TEMPLATE_TABLE} SET {clause}last_seq = :last_seq WHERE id = :id")
            return conn.execute(stmt, {**base, **params}).rowcount
        if kind == TEMPLATE_PUBLISHED:
            params = {"on": payload["published_on"], "content_hash": payload["content_hash"]}
            return conn.execute(_PUBLISH, {**base, **params}).rowcount
        if kind == TEMPLATE_RETIRED:
            return conn.execute(_RETIRE, {**base, "on": payload["retired_on"]}).rowcount
        raise ValueError(f"TemplateProjector cannot apply event type: {kind}")

    def reset(self, conn: Connection) -> None:
        conn.execute(text(f"DELETE FROM {TEMPLATE_TABLE}"))
