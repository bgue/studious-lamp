"""CommercialProjector: the ``Commercial.*`` events into ``cur_correspondence_commercial_item``.

``Defined`` inserts the domain row of an early warning, change notice, claim and the like (the item
row is written by ``CorrespondenceProjector`` from the ``Correspondence.Defined`` event of the same
append); ``Updated`` changes the notice before it is issued; ``Assessed`` records the other party's
assessment. Deterministic: a row depends only on the events of its stream. Register it after
``RecordProjector``.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import Connection, text
from tl_core.ledger import Event

from tl_mod_correspondence.names import (
    COMM_ASSESSED,
    COMM_DEFINED,
    COMM_UPDATED,
    COMMERCIAL_TABLE,
    COMMERCIAL_VIEW,
)
from tl_mod_correspondence.projectors._common import ddl_for, json_text, touch_record

#: Fields a ``Commercial.Updated`` may change. The name is both the payload key and the column;
#: ``cost_code_impacts`` is stored in the JSON column ``cost_code_impacts_json``.
_UPDATABLE = (
    "contract_clause_id",
    "aware_on",
    "currency",
    "estimated_value",
    "estimated_hours",
    "cost_code_impacts",
    "schedule_impact_days",
    "schedule_impact_note",
    "entitlement_basis",
)


class CommercialProjector:
    name = "correspondence_commercial"
    handles = frozenset({COMM_DEFINED, COMM_UPDATED, COMM_ASSESSED})

    def ddl(self, dialect: str) -> list[str]:
        return ddl_for(COMMERCIAL_TABLE, dialect) + ddl_for(COMMERCIAL_VIEW, dialect)

    def apply(self, conn: Connection, event: Event) -> None:
        p = event.payload
        et = event.event_type
        if et == COMM_DEFINED:
            conn.execute(
                text(
                    f"INSERT INTO {COMMERCIAL_TABLE} (id, scope, contract_clause_id, aware_on, "
                    "derived_from_id, currency, estimated_value, estimated_hours, "
                    "cost_code_impacts_json, schedule_impact_days, schedule_impact_note, "
                    "entitlement_basis, last_seq) VALUES (:id, :scope, :contract_clause_id, "
                    ":aware_on, :derived_from_id, :currency, :estimated_value, :estimated_hours, "
                    ":impacts, :schedule_impact_days, :schedule_impact_note, :entitlement_basis, "
                    ":last_seq)"
                ),
                {
                    "id": event.stream_id,
                    "scope": event.scope,
                    "contract_clause_id": p.get("contract_clause_id"),
                    "aware_on": p.get("aware_on"),
                    "derived_from_id": p.get("derived_from_id"),
                    "currency": p.get("currency"),
                    "estimated_value": p.get("estimated_value"),
                    "estimated_hours": p.get("estimated_hours"),
                    "impacts": json_text(p.get("cost_code_impacts") or []),
                    "schedule_impact_days": p.get("schedule_impact_days"),
                    "schedule_impact_note": p.get("schedule_impact_note"),
                    "entitlement_basis": p.get("entitlement_basis"),
                    "last_seq": event.seq,
                },
            )
        elif et == COMM_UPDATED:
            changes: dict[str, Any] = p.get("changes") or {}
            assignments: list[str] = []
            values: dict[str, Any] = {}
            for name in _UPDATABLE:
                if name not in changes:
                    continue
                value = changes[name][1]
                if name == "cost_code_impacts":
                    assignments.append("cost_code_impacts_json = :cost_code_impacts_json")
                    values["cost_code_impacts_json"] = json_text(value or [])
                else:
                    assignments.append(f"{name} = :{name}")
                    values[name] = value
            self._update(conn, event, assignments, values)
        elif et == COMM_ASSESSED:
            self._update(
                conn,
                event,
                [
                    "assessment_status = :status",
                    "assessed_value = :assessed_value",
                    "assessed_on = :assessed_on",
                    "assessment_note = :note",
                ],
                {
                    "status": p["status"],
                    "assessed_value": p.get("assessed_value"),
                    "assessed_on": p["assessed_on"],
                    "note": p.get("note"),
                },
            )
        else:
            raise ValueError(f"CommercialProjector cannot apply event type: {et}")
        touch_record(conn, event)

    @staticmethod
    def _update(
        conn: Connection, event: Event, assignments: list[str], values: dict[str, Any]
    ) -> None:
        # The assignments name columns of this module only; values are bound parameters.
        sets = ", ".join([*assignments, "last_seq = :last_seq"])
        result = conn.execute(
            text(f"UPDATE {COMMERCIAL_TABLE} SET {sets} WHERE id = :id"),
            {"id": event.stream_id, "last_seq": event.seq, **values},
        )
        if result.rowcount == 0:
            raise LookupError(f"no {COMMERCIAL_TABLE} row for stream {event.stream_id}")

    def reset(self, conn: Connection) -> None:
        conn.execute(text(f"DELETE FROM {COMMERCIAL_TABLE}"))
