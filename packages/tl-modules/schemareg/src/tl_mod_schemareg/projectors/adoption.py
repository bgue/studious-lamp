"""AdoptionProjector: ``Adoption.Pinned`` into ``cur_schemareg_adoption``.

The first pin of a project and package inserts the row (the record was just created by
``Record.Created``); a later pin on the same stream moves it.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import Connection, text
from tl_core.ledger import Event, iso_utc

from tl_mod_schemareg.names import ADOPTION_PINNED, ADOPTION_TABLE, ADOPTION_VIEW
from tl_mod_schemareg.projectors._common import ddl_for, touch_record

_EXISTS_SQL = text(f"SELECT 1 FROM {ADOPTION_TABLE} WHERE id = :id")
_INSERT_SQL = text(
    f"INSERT INTO {ADOPTION_TABLE} (id, scope, project, package, semver, previous_semver, "
    "worst_class, impact_sha256, adopted_by, adopted_at, last_seq) "
    "VALUES (:id, :scope, :project, :package, :semver, :previous_semver, :worst_class, "
    ":impact_sha256, :adopted_by, :adopted_at, :last_seq)"
)
_UPDATE_SQL = text(
    f"UPDATE {ADOPTION_TABLE} SET semver = :semver, previous_semver = :previous_semver, "
    "worst_class = :worst_class, impact_sha256 = :impact_sha256, adopted_by = :adopted_by, "
    "adopted_at = :adopted_at, last_seq = :last_seq WHERE id = :id"
)


class AdoptionProjector:
    name = "schemareg_adoption"
    handles = frozenset({ADOPTION_PINNED})

    def ddl(self, dialect: str) -> list[str]:
        return ddl_for(ADOPTION_TABLE, dialect) + ddl_for(ADOPTION_VIEW, dialect)

    def apply(self, conn: Connection, event: Event) -> None:
        if event.event_type != ADOPTION_PINNED:
            raise ValueError(f"AdoptionProjector cannot apply event type: {event.event_type}")
        payload: dict[str, Any] = event.payload
        params: dict[str, Any] = {
            "id": event.stream_id,
            "scope": event.scope,
            "project": payload["project"],
            "package": payload["package"],
            "semver": payload["version"],
            "previous_semver": payload.get("previous_version"),
            "worst_class": payload.get("worst_class"),
            "impact_sha256": payload.get("impact_sha256"),
            "adopted_by": payload["adopted_by"],
            "adopted_at": iso_utc(event.recorded_at),
            "last_seq": event.seq,
        }
        exists = conn.execute(_EXISTS_SQL, {"id": event.stream_id}).first() is not None
        conn.execute(_UPDATE_SQL if exists else _INSERT_SQL, params)
        touch_record(conn, event)

    def reset(self, conn: Connection) -> None:
        conn.execute(text(f"DELETE FROM {ADOPTION_TABLE}"))
