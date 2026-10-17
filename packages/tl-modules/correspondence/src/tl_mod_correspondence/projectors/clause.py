"""ClauseProjector: the ``ContractClause.*`` events into ``cur_correspondence_contract_clause``.

``Defined`` inserts the clause; ``Retired`` clears ``is_active``. Deterministic. Register it after
``RecordProjector``.
"""

from __future__ import annotations

from sqlalchemy import Connection, text
from tl_core.ledger import Event

from tl_mod_correspondence.names import CLAUSE_DEFINED, CLAUSE_RETIRED, CLAUSE_TABLE, CLAUSE_VIEW
from tl_mod_correspondence.projectors._common import ddl_for, json_text, touch_record


class ClauseProjector:
    name = "correspondence_clause"
    handles = frozenset({CLAUSE_DEFINED, CLAUSE_RETIRED})

    def ddl(self, dialect: str) -> list[str]:
        return ddl_for(CLAUSE_TABLE, dialect) + ddl_for(CLAUSE_VIEW, dialect)

    def apply(self, conn: Connection, event: Event) -> None:
        p = event.payload
        if event.event_type == CLAUSE_DEFINED:
            conn.execute(
                text(
                    f"INSERT INTO {CLAUSE_TABLE} (id, scope, contract, clause_number, "
                    "time_bar_days, time_bar_day_type, notice_requirements, service_method, "
                    "contract_document_id, required_recipients_json, domains_json, is_active, "
                    "last_seq) VALUES (:id, :scope, :contract, :clause_number, :time_bar_days, "
                    ":time_bar_day_type, :notice_requirements, :service_method, "
                    ":contract_document_id, :required_recipients_json, :domains_json, :is_active, "
                    ":last_seq)"
                ),
                {
                    "id": event.stream_id,
                    "scope": event.scope,
                    "contract": p["contract"],
                    "clause_number": p["clause_number"],
                    "time_bar_days": p.get("time_bar_days"),
                    "time_bar_day_type": p.get("time_bar_day_type"),
                    "notice_requirements": p.get("notice_requirements"),
                    "service_method": p.get("service_method"),
                    "contract_document_id": p.get("contract_document_id"),
                    "required_recipients_json": json_text(p.get("required_recipients") or []),
                    "domains_json": json_text(p.get("domains") or []),
                    "is_active": True,
                    "last_seq": event.seq,
                },
            )
        elif event.event_type == CLAUSE_RETIRED:
            result = conn.execute(
                text(
                    f"UPDATE {CLAUSE_TABLE} SET is_active = :is_active, last_seq = :last_seq "
                    "WHERE id = :id"
                ),
                {"is_active": False, "last_seq": event.seq, "id": event.stream_id},
            )
            if result.rowcount == 0:
                raise LookupError(f"no {CLAUSE_TABLE} row for stream {event.stream_id}")
        else:
            raise ValueError(f"ClauseProjector cannot apply event type: {event.event_type}")
        touch_record(conn, event)

    def reset(self, conn: Connection) -> None:
        conn.execute(text(f"DELETE FROM {CLAUSE_TABLE}"))
