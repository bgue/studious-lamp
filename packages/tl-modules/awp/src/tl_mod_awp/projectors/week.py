"""Projector of the weekly plan: ``cur_awp_weekly_plan`` and ``cur_awp_week_commitment``.

``WeeklyPlan.Opened`` inserts the plan row; ``WeeklyPlan.IwpCommitted`` inserts the commitment
(one per plan and IWP; a second commit of the same IWP replaces it);
``WeeklyPlan.OutcomeRecorded`` sets the outcome and the miss reason; ``WeeklyPlan.Closed`` sets
the PPC and the closing time. No handler yet: the commands come in P2-I5 S4. Deterministic: the
rows depend only on the events. Register after ``RecordProjector``.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import Connection, text
from tl_core.ledger import Event, iso_utc

from tl_mod_awp.names import (
    WEEK_CLOSED,
    WEEK_COMMITMENT_TABLE,
    WEEK_IWP_COMMITTED,
    WEEK_OPENED,
    WEEK_OUTCOME_RECORDED,
    WEEKLY_PLAN_TABLE,
    WEEKLY_PLAN_VIEW,
)
from tl_mod_awp.projectors._common import ddl_for, touch_record

_OPEN_SQL = text(
    f"INSERT INTO {WEEKLY_PLAN_TABLE} (id, scope, week, week_start, last_seq) "
    "VALUES (:id, :scope, :week, :week_start, :last_seq)"
)
_CLOSE_SQL = text(
    f"UPDATE {WEEKLY_PLAN_TABLE} SET ppc = :ppc, closed_at = :closed_at, last_seq = :last_seq "
    "WHERE id = :id"
)
_BUMP_SQL = text(f"UPDATE {WEEKLY_PLAN_TABLE} SET last_seq = :last_seq WHERE id = :id")
_DROP_SQL = text(
    f"DELETE FROM {WEEK_COMMITMENT_TABLE} WHERE plan_id = :plan_id AND iwp_id = :iwp_id"
)
_COMMIT_SQL = text(
    f"INSERT INTO {WEEK_COMMITMENT_TABLE} (row_id, scope, plan_id, iwp_id, foreman, "
    "committed_hours, last_seq) VALUES (:row_id, :scope, :plan_id, :iwp_id, :foreman, "
    ":committed_hours, :last_seq)"
)
_OUTCOME_SQL = text(
    f"UPDATE {WEEK_COMMITMENT_TABLE} SET outcome = :outcome, miss_reason = :miss_reason, "
    "last_seq = :last_seq WHERE plan_id = :plan_id AND iwp_id = :iwp_id"
)


def commitment_id(plan_id: str, iwp_id: str) -> str:
    """``<plan id>:<iwp id>``, the key of a commitment row."""
    return f"{plan_id}:{iwp_id}"


class WeekProjector:
    name = "awp_week"
    handles = frozenset({WEEK_OPENED, WEEK_IWP_COMMITTED, WEEK_OUTCOME_RECORDED, WEEK_CLOSED})

    def ddl(self, dialect: str) -> list[str]:
        return (
            ddl_for(WEEKLY_PLAN_TABLE, dialect)
            + ddl_for(WEEKLY_PLAN_VIEW, dialect)
            + ddl_for(WEEK_COMMITMENT_TABLE, dialect)
        )

    def apply(self, conn: Connection, event: Event) -> None:
        payload: dict[str, Any] = event.payload
        kind = event.event_type
        plan_id = event.stream_id
        if kind == WEEK_OPENED:
            conn.execute(
                _OPEN_SQL,
                {
                    "id": plan_id,
                    "scope": event.scope,
                    "week": payload["week"],
                    "week_start": payload["week_start"],
                    "last_seq": event.seq,
                },
            )
        elif kind == WEEK_IWP_COMMITTED:
            iwp_id = payload["iwp_id"]
            conn.execute(_DROP_SQL, {"plan_id": plan_id, "iwp_id": iwp_id})
            conn.execute(
                _COMMIT_SQL,
                {
                    "row_id": commitment_id(plan_id, iwp_id),
                    "scope": event.scope,
                    "plan_id": plan_id,
                    "iwp_id": iwp_id,
                    "foreman": payload["foreman"],
                    "committed_hours": payload["committed_hours"],
                    "last_seq": event.seq,
                },
            )
            conn.execute(_BUMP_SQL, {"id": plan_id, "last_seq": event.seq})
        elif kind == WEEK_OUTCOME_RECORDED:
            conn.execute(
                _OUTCOME_SQL,
                {
                    "plan_id": plan_id,
                    "iwp_id": payload["iwp_id"],
                    "outcome": payload["outcome"],
                    "miss_reason": payload.get("miss_reason"),
                    "last_seq": event.seq,
                },
            )
            conn.execute(_BUMP_SQL, {"id": plan_id, "last_seq": event.seq})
        elif kind == WEEK_CLOSED:
            conn.execute(
                _CLOSE_SQL,
                {
                    "id": plan_id,
                    "ppc": payload["ppc"],
                    "closed_at": payload.get("at") or iso_utc(event.effective_at),
                    "last_seq": event.seq,
                },
            )
        else:
            raise ValueError(f"WeekProjector cannot apply event type: {kind}")
        touch_record(conn, event)

    def reset(self, conn: Connection) -> None:
        conn.execute(text(f"DELETE FROM {WEEK_COMMITMENT_TABLE}"))
        conn.execute(text(f"DELETE FROM {WEEKLY_PLAN_TABLE}"))


def week_projectors() -> list[WeekProjector]:
    """Fresh projectors of the weekly plan tables."""
    return [WeekProjector()]
