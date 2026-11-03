"""PathProjector: ``PathOfConstruction.*`` events into ``cur_awp_path`` and ``cur_awp_path_step``.

``Defined`` inserts the path at version 1 with its steps; ``Resequenced`` moves ``current_version``
to the new version and adds that version's steps. Every version stays as rows, so a reader can
compare two. The step rows carry the event's actor and time. Deterministic. Register it after
``RecordProjector``.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import Connection, text
from tl_core.ledger import Event, iso_utc

from tl_mod_awp.names import (
    PATH_DEFINED,
    PATH_RESEQUENCED,
    PATH_STEP_TABLE,
    PATH_TABLE,
    PATH_VIEW,
)
from tl_mod_awp.projectors._common import ddl_for, touch_record

_INSERT_SQL = text(
    f"INSERT INTO {PATH_TABLE} (id, scope, current_version, last_seq) "
    "VALUES (:id, :scope, :current_version, :last_seq)"
)
_VERSION_SQL = text(
    f"UPDATE {PATH_TABLE} SET current_version = :current_version, last_seq = :last_seq "
    "WHERE id = :id"
)
_STEP_SQL = text(
    f"INSERT INTO {PATH_STEP_TABLE} (row_id, scope, path_id, version, position, cwa_id, "
    "reason_code, actor, recorded_at, last_seq) VALUES (:row_id, :scope, :path_id, :version, "
    ":position, :cwa_id, :reason_code, :actor, :recorded_at, :last_seq)"
)


def step_row_id(path_id: str, version: int, position: int) -> str:
    """``<path id>:<version>:<position>``, the key of a step row."""
    return f"{path_id}:{version}:{position}"


class PathProjector:
    name = "awp_path"
    handles = frozenset({PATH_DEFINED, PATH_RESEQUENCED})

    def ddl(self, dialect: str) -> list[str]:
        return (
            ddl_for(PATH_TABLE, dialect)
            + ddl_for(PATH_STEP_TABLE, dialect)
            + ddl_for(PATH_VIEW, dialect)
        )

    def apply(self, conn: Connection, event: Event) -> None:
        payload: dict[str, Any] = event.payload
        kind = event.event_type
        if kind not in self.handles:
            raise ValueError(f"PathProjector cannot apply event type: {kind}")
        version = int(payload["version"])
        if kind == PATH_DEFINED:
            conn.execute(
                _INSERT_SQL,
                {
                    "id": event.stream_id,
                    "scope": event.scope,
                    "current_version": version,
                    "last_seq": event.seq,
                },
            )
        else:
            conn.execute(
                _VERSION_SQL,
                {"id": event.stream_id, "current_version": version, "last_seq": event.seq},
            )
        stamp = iso_utc(event.recorded_at)
        for position, step in enumerate(payload["steps"], start=1):
            conn.execute(
                _STEP_SQL,
                {
                    "row_id": step_row_id(event.stream_id, version, position),
                    "scope": event.scope,
                    "path_id": event.stream_id,
                    "version": version,
                    "position": position,
                    "cwa_id": step["cwa_id"],
                    "reason_code": step.get("reason_code"),
                    "actor": event.actor,
                    "recorded_at": stamp,
                    "last_seq": event.seq,
                },
            )
        touch_record(conn, event)

    def reset(self, conn: Connection) -> None:
        conn.execute(text(f"DELETE FROM {PATH_STEP_TABLE}"))
        conn.execute(text(f"DELETE FROM {PATH_TABLE}"))
