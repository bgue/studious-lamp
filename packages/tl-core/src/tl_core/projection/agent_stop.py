"""AgentStopProjector: ``Agent.Stopped`` and ``Agent.Resumed`` into ``cur_agent_stop`` (P2-X2).

One row per agent that was ever stopped; a resume clears the flag and keeps the row. Every value
comes from the event, so a rebuild equals the live table. The events sit on the agent's account
stream (``account:<account_id>``); ``AccountProjector`` also handles them, to keep the account
row's ``version`` at the stream head, so each projector rebuilds alone (``--only accounts`` or
``--only agent_stop``) without leaving the version wrong. This projector writes only its table.
"""

from __future__ import annotations

from sqlalchemy import Connection, text
from tl_schema.ddl_loader import statements

from tl_core.auth._time import iso_z
from tl_core.ledger import Event

AGENT_STOPPED = "Agent.Stopped"
AGENT_RESUMED = "Agent.Resumed"
AGENT_STOP_EVENT_TYPES = frozenset({AGENT_STOPPED, AGENT_RESUMED})
_ACCOUNT_PREFIX = "account:"

_STOP = text(
    "INSERT INTO cur_agent_stop (agent, account_id, stopped, stopped_at, stopped_by, reason, "
    "last_seq) VALUES (:agent, :account_id, 1, :stamp, :by, :reason, :seq)"
)
_RESTOP = text(
    "UPDATE cur_agent_stop SET stopped = 1, stopped_at = :stamp, stopped_by = :by, "
    "reason = :reason, last_seq = :seq WHERE agent = :agent"
)
_RESUME = text(
    "UPDATE cur_agent_stop SET stopped = 0, resumed_at = :stamp, resumed_by = :by, "
    "last_seq = :seq WHERE agent = :agent"
)


class AgentStopProjector:
    name = "agent_stop"
    handles = AGENT_STOP_EVENT_TYPES

    def ddl(self, dialect: str) -> list[str]:
        if dialect == "sqlite" or dialect == "postgres":
            return statements("cur_agent_stop", dialect)
        raise ValueError(f"unsupported dialect: {dialect}")

    def reset(self, conn: Connection) -> None:
        conn.execute(text("DELETE FROM cur_agent_stop"))

    def apply(self, conn: Connection, event: Event) -> None:
        if event.event_type not in AGENT_STOP_EVENT_TYPES:
            raise ValueError(f"AgentStopProjector cannot apply: {event.event_type}")
        if not event.stream_id.startswith(_ACCOUNT_PREFIX):
            raise ValueError(f"{event.event_type} is on stream {event.stream_id}, not an account")
        account_id = event.stream_id[len(_ACCOUNT_PREFIX) :]
        agent = str(event.payload["agent"])
        params = {
            "agent": agent,
            "account_id": account_id,
            "stamp": iso_z(event.recorded_at),
            "by": event.actor,
            "reason": event.payload.get("reason"),
            "seq": event.seq,
        }
        if event.event_type == AGENT_STOPPED:
            known = conn.execute(
                text("SELECT 1 FROM cur_agent_stop WHERE agent = :agent"), {"agent": agent}
            ).first()
            conn.execute(_RESTOP if known else _STOP, params)
        else:
            if conn.execute(_RESUME, params).rowcount == 0:
                raise LookupError(f"no stop row for stream {event.stream_id}")
