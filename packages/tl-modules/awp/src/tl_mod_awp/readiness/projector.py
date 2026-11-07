"""ReadinessProjector: ``IWP.ReadinessEvaluated`` into ``cur_awp_readiness`` and its check rows.

The event carries the whole evaluation, so the projector replaces the IWP's rows (last evaluation
only; history is the events). Deterministic: a rebuild never calls a check. ``IWP.Ready`` writes no
row; it only moves the envelope version of its stream.
"""

from __future__ import annotations

import json
from typing import Any

from sqlalchemy import Connection, text
from tl_core.ledger import Event
from tl_core.projection.types import Projector

from tl_mod_awp.names import (
    IWP_READINESS_EVALUATED,
    IWP_READY_EVENT,
    READINESS_CHECK_TABLE,
    READINESS_TABLE,
)
from tl_mod_awp.projectors._common import ddl_for, touch_record

_CLEAR_CHECKS = text(f"DELETE FROM {READINESS_CHECK_TABLE} WHERE iwp_id = :id")
_CLEAR_HEAD = text(f"DELETE FROM {READINESS_TABLE} WHERE iwp_id = :id")
_HEAD = text(
    f"INSERT INTO {READINESS_TABLE} (iwp_id, scope, evaluated_at, today, ready, facts_hash, "
    "as_of_seq) VALUES (:id, :scope, :evaluated_at, :today, :ready, :facts_hash, :seq)"
)
_CHECK = text(
    f"INSERT INTO {READINESS_CHECK_TABLE} (row_id, scope, iwp_id, name, version, state, detail, "
    "count_ok, count_total, resolve_via_json, as_of_seq) VALUES (:row_id, :scope, :id, :name, "
    ":version, :state, :detail, :count_ok, :count_total, :resolve_via, :seq)"
)


class ReadinessProjector:
    name = "awp_readiness"
    handles = frozenset({IWP_READINESS_EVALUATED, IWP_READY_EVENT})

    def ddl(self, dialect: str) -> list[str]:
        return [
            *ddl_for(READINESS_TABLE, dialect),
            *ddl_for(READINESS_CHECK_TABLE, dialect),
        ]

    def apply(self, conn: Connection, event: Event) -> None:
        if event.event_type == IWP_READY_EVENT:
            touch_record(conn, event)
            return
        if event.event_type != IWP_READINESS_EVALUATED:
            raise ValueError(f"ReadinessProjector cannot apply event type: {event.event_type}")
        payload: dict[str, Any] = event.payload
        iwp = event.stream_id
        conn.execute(_CLEAR_CHECKS, {"id": iwp})
        conn.execute(_CLEAR_HEAD, {"id": iwp})
        conn.execute(
            _HEAD,
            {
                "id": iwp,
                "scope": event.scope,
                "evaluated_at": payload["evaluated_at"],
                "today": payload["today"],
                "ready": bool(payload["ready"]),
                "facts_hash": payload["facts_hash"],
                "seq": event.seq,
            },
        )
        for entry in payload["checks"]:
            conn.execute(
                _CHECK,
                {
                    "row_id": f"{iwp}:{entry['name']}",
                    "scope": event.scope,
                    "id": iwp,
                    "name": entry["name"],
                    "version": entry["version"],
                    "state": entry["state"],
                    "detail": entry.get("detail"),
                    "count_ok": entry.get("count_ok"),
                    "count_total": entry.get("count_total"),
                    "resolve_via": json.dumps(entry.get("resolve_via") or [], sort_keys=True),
                    "seq": event.seq,
                },
            )
        touch_record(conn, event)

    def reset(self, conn: Connection) -> None:
        conn.execute(text(f"DELETE FROM {READINESS_CHECK_TABLE}"))
        conn.execute(text(f"DELETE FROM {READINESS_TABLE}"))


def readiness_projectors() -> list[Projector]:
    """Fresh projectors of the readiness tables."""
    return [ReadinessProjector()]
