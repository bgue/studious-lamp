"""RollupProjector: ``WBSNode.BudgetRolledUp`` into ``cur_awp_rollup`` (spec m3-wbs-cwp section 4).

The event carries the whole figure of one node (total and the by-cost-code lines), so the
projector replaces that node's rows. Deterministic: the rows depend only on the events, so a
rebuild gives the table the runs made and never calls the job.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import Connection, text
from tl_core.ledger import Event
from tl_core.projection.types import Projector

from tl_mod_awp.projectors._common import ddl_for, touch_record
from tl_mod_awp.rollup import (
    BUDGET_ROLLED_UP,
    LINE_COST_CODE,
    LINE_TOTAL,
    LINE_UNALLOCATED,
    MEASURE,
    ROLLUP_TABLE,
    SUBJECT_KIND,
)

_CLEAR_SQL = text(
    f"DELETE FROM {ROLLUP_TABLE} WHERE subject_kind = :kind AND subject_id = :subject_id "
    "AND measure = :measure"
)
_INSERT_SQL = text(
    f"INSERT INTO {ROLLUP_TABLE} (row_id, scope, subject_kind, subject_id, line, cost_code_id, "
    "measure, value, as_of_seq, run_id, last_seq) VALUES (:row_id, :scope, :kind, :subject_id, "
    ":line, :cost_code_id, :measure, :value, :as_of_seq, :run_id, :last_seq)"
)


def row_id(subject_id: str, line: str, cost_code_id: str | None) -> str:
    """``<subject id>:<measure>:<line>:<cost code id or ->``, the key of a figure."""
    return f"{subject_id}:{MEASURE}:{line}:{cost_code_id or '-'}"


class RollupProjector:
    name = "awp_rollup"
    handles = frozenset({BUDGET_ROLLED_UP})

    def ddl(self, dialect: str) -> list[str]:
        return ddl_for(ROLLUP_TABLE, dialect)

    def apply(self, conn: Connection, event: Event) -> None:
        if event.event_type != BUDGET_ROLLED_UP:
            raise ValueError(f"RollupProjector cannot apply event type: {event.event_type}")
        payload: dict[str, Any] = event.payload
        subject = event.stream_id
        common: dict[str, Any] = {
            "scope": event.scope,
            "kind": SUBJECT_KIND,
            "subject_id": subject,
            "measure": MEASURE,
            "as_of_seq": int(payload["as_of_seq"]),
            "run_id": payload["run_id"],
            "last_seq": event.seq,
        }
        conn.execute(_CLEAR_SQL, {"kind": SUBJECT_KIND, "subject_id": subject, "measure": MEASURE})
        lines: list[tuple[str, str | None, str]] = [(LINE_TOTAL, None, payload["total"])]
        for entry in payload["by_cost_code"]:
            code = entry["cost_code_id"]
            lines.append(
                (LINE_UNALLOCATED if code is None else LINE_COST_CODE, code, entry["value"])
            )
        for line, code, value in lines:
            conn.execute(
                _INSERT_SQL,
                {
                    **common,
                    "row_id": row_id(subject, line, code),
                    "line": line,
                    "cost_code_id": code,
                    "value": value,
                },
            )
        touch_record(conn, event)

    def reset(self, conn: Connection) -> None:
        conn.execute(text(f"DELETE FROM {ROLLUP_TABLE}"))


def rollup_projectors() -> list[Projector]:
    """Fresh projectors of the rollup table."""
    return [RollupProjector()]
