# ruff: noqa: F401, F841
"""ClauseProjector: the ``ContractClause.*`` events into ``cur_correspondence_contract_clause``.

``Defined`` inserts the clause; ``Retired`` clears ``is_active``. Deterministic. Register it after
``RecordProjector``.

STUB (P1-I5-T03c): the functions with a STEPS comment are for you to write. When they are
written, delete this paragraph, the STEPS comments and the `ruff: noqa` line at the top.
"""

from __future__ import annotations

from typing import Any

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
        # STEPS
        # 1. CLAUSE_DEFINED: INSERT into CLAUSE_TABLE: id (`event.stream_id`), scope
        #    (`event.scope`), contract, clause_number (required keys), time_bar_days,
        #    time_bar_day_type, notice_requirements, service_method, contract_document_id (all
        #    `p.get`), `required_recipients_json` = `json_text(p.get("required_recipients") or [])`,
        #    `domains_json` = `json_text(p.get("domains") or [])`, is_active True (a Python bool),
        #    last_seq.
        # 2. CLAUSE_RETIRED: UPDATE is_active = False (a Python bool) and last_seq WHERE id = :id; a
        #    row count of 0 raises `LookupError(f"no {CLAUSE_TABLE} row for stream
        #    {event.stream_id}")`.
        # 3. Any other event type: `raise ValueError(f"ClauseProjector cannot apply event type:
        #    {event.event_type}")`. After the branches call `touch_record(conn, event)`.
        raise NotImplementedError

    def reset(self, conn: Connection) -> None:
        # STEPS
        # 1. `DELETE FROM` the CLAUSE_TABLE.
        raise NotImplementedError
