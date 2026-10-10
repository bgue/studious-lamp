"""ProposalProjector: ``Proposal.*`` events into ``cur_proposals`` (the review queue; brief 11.3).

One row per proposal. Deterministic: every value comes from the event. ``created_day`` is the UTC
day of the ``effective_at`` of ``Proposal.Created``, so a simulated day (FANOUT D5) counts against
the agent's budget for that day and not for the day the test happened to run.
"""

from __future__ import annotations

import json
from datetime import UTC
from typing import Any

from sqlalchemy import Connection, text
from tl_schema.ddl_loader import statements

from tl_core.ledger import Event, iso_utc
from tl_core.proposals.types import (
    PROPOSAL_ACCEPTED,
    PROPOSAL_CREATED,
    PROPOSAL_FAILED,
    PROPOSAL_REJECTED,
)

PROPOSAL_STREAM_TYPE = "core.Proposal"
PROPOSAL_EVENT_TYPES = frozenset(
    {PROPOSAL_CREATED, PROPOSAL_ACCEPTED, PROPOSAL_REJECTED, PROPOSAL_FAILED}
)

_INSERT_SQL = text(
    "INSERT INTO cur_proposals (proposal_id, scope, tool, agent, command_type, command_json, "
    "summary, status, created_day, created_at, created_event_id, seq, version) VALUES "
    "(:proposal_id, :scope, :tool, :agent, :command_type, :command_json, :summary, 'pending', "
    ":created_day, :created_at, :created_event_id, :seq, :version)"
)
_DECIDE_SQL = text(
    "UPDATE cur_proposals SET status = :status, decided_by = :decided_by, "
    "decided_at = :decided_at, reason = :reason, result_stream_id = :result_stream_id, "
    "version = :version WHERE proposal_id = :proposal_id AND status = 'pending'"
)


def utc_day(event: Event) -> str:
    """``YYYY-MM-DD`` (UTC) of the event's ``effective_at``."""
    return event.effective_at.astimezone(UTC).date().isoformat()


class ProposalProjector:
    name = "proposals"
    handles = PROPOSAL_EVENT_TYPES

    def ddl(self, dialect: str) -> list[str]:
        if dialect == "sqlite" or dialect == "postgres":
            return statements("cur_proposals", dialect)
        raise ValueError(f"unsupported dialect: {dialect}")

    def reset(self, conn: Connection) -> None:
        conn.execute(text("DELETE FROM cur_proposals"))

    def apply(self, conn: Connection, event: Event) -> None:
        if event.event_type == PROPOSAL_CREATED:
            self._create(conn, event)
        elif event.event_type in PROPOSAL_EVENT_TYPES:
            self._decide(conn, event)
        else:
            raise ValueError(f"ProposalProjector cannot apply: {event.event_type}")

    @staticmethod
    def _create(conn: Connection, event: Event) -> None:
        payload = event.payload
        conn.execute(
            _INSERT_SQL,
            {
                "proposal_id": event.stream_id,
                "scope": event.scope,
                "tool": payload["tool"],
                "agent": payload["agent"],
                "command_type": payload["command_type"],
                "command_json": json.dumps(
                    payload["command"], sort_keys=True, separators=(",", ":"), ensure_ascii=False
                ),
                "summary": payload["summary"],
                "created_day": utc_day(event),
                "created_at": iso_utc(event.recorded_at),
                "created_event_id": event.event_id,
                "seq": event.seq,
                "version": event.stream_version,
            },
        )

    @staticmethod
    def _decide(conn: Connection, event: Event) -> None:
        payload = event.payload
        status = {
            PROPOSAL_ACCEPTED: "accepted",
            PROPOSAL_REJECTED: "rejected",
            PROPOSAL_FAILED: "failed",
        }[event.event_type]
        reason: Any = None
        if event.event_type == PROPOSAL_REJECTED:
            reason = payload["reason"]
        elif event.event_type == PROPOSAL_FAILED:
            reason = payload["error"]
        done = conn.execute(
            _DECIDE_SQL,
            {
                "proposal_id": event.stream_id,
                "status": status,
                "decided_by": payload["by"],
                "decided_at": iso_utc(event.recorded_at),
                "reason": reason,
                "result_stream_id": payload.get("result_stream_id"),
                "version": event.stream_version,
            },
        )
        if done.rowcount == 0:
            raise LookupError(f"no pending proposal row for stream {event.stream_id}")
