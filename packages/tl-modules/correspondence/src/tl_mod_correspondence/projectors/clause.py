"""ClauseProjector: the ``ContractClause.*`` events into ``cur_correspondence_contract_clause``.

``Defined`` inserts the clause; ``Retired`` clears ``is_active``. Deterministic. Register it after
``RecordProjector``.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import Connection, text
from tl_core.ledger import Event

from tl_mod_correspondence.names import CLAUSE_DEFINED, CLAUSE_RETIRED, CLAUSE_TABLE, CLAUSE_VIEW
from tl_mod_correspondence.projectors._common import ddl_for, json_text, touch_record

_INSERT_SQL = text(
    f"INSERT INTO {CLAUSE_TABLE} (id, scope, contract, clause_number, time_bar_days, "
    "time_bar_day_type, notice_requirements, required_recipients_json, service_method, "
    "contract_document_id, domains_json, is_active, last_seq) VALUES (:id, :scope, :contract, "
    ":clause_number, :time_bar_days, :time_bar_day_type, :notice_requirements, :recipients_json, "
    ":service_method, :contract_document_id, :domains_json, :active, :last_seq)"
)
_RETIRE_SQL = text(
    f"UPDATE {CLAUSE_TABLE} SET is_active = :active, last_seq = :last_seq WHERE id = :id"
)


class ClauseProjector:
    name = "correspondence_clause"
    handles = frozenset({CLAUSE_DEFINED, CLAUSE_RETIRED})

    def ddl(self, dialect: str) -> list[str]:
        return ddl_for(CLAUSE_TABLE, dialect) + ddl_for(CLAUSE_VIEW, dialect)

    def apply(self, conn: Connection, event: Event) -> None:
        p: dict[str, Any] = event.payload
        if event.event_type == CLAUSE_DEFINED:
            conn.execute(
                _INSERT_SQL,
                {
                    "id": event.stream_id,
                    "scope": event.scope,
                    "contract": p["contract"],
                    "clause_number": p["clause_number"],
                    "time_bar_days": p.get("time_bar_days"),
                    "time_bar_day_type": p.get("time_bar_day_type"),
                    "notice_requirements": p.get("notice_requirements"),
                    "recipients_json": json_text(p.get("required_recipients") or []),
                    "service_method": p.get("service_method"),
                    "contract_document_id": p.get("contract_document_id"),
                    "domains_json": json_text(p.get("domains") or []),
                    "active": True,
                    "last_seq": event.seq,
                },
            )
        elif event.event_type == CLAUSE_RETIRED:
            found = conn.execute(
                _RETIRE_SQL, {"id": event.stream_id, "active": False, "last_seq": event.seq}
            ).rowcount
            if found == 0:
                raise LookupError(f"no {CLAUSE_TABLE} row for stream {event.stream_id}")
        else:
            raise ValueError(f"ClauseProjector cannot apply event type: {event.event_type}")
        touch_record(conn, event)

    def reset(self, conn: Connection) -> None:
        conn.execute(text(f"DELETE FROM {CLAUSE_TABLE}"))
