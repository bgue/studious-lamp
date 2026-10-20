"""SchemaPackageProjector: the package events into ``cur_schemareg_schema_package``.

Deterministic: every column comes from an event. ``SchemaPackage.Published`` is a core catalog
event; this projector handles it only on a stream of this module's record type, so a raw event of
that name on another stream (a webhook scenario, a test) is left alone.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import Connection, text
from tl_core.ledger import Event, iso_utc

from tl_mod_schemareg.names import (
    PACKAGE_ANALYSED,
    PACKAGE_APPROVED,
    PACKAGE_CHANGES_REQUESTED,
    PACKAGE_DEPRECATED,
    PACKAGE_DRAFTED,
    PACKAGE_PUBLISHED,
    PACKAGE_RETIRED,
    PACKAGE_REVISED,
    PACKAGE_SUBMITTED,
    PACKAGE_TABLE,
    PACKAGE_VIEW,
    SCHEMA_PACKAGE,
)
from tl_mod_schemareg.projectors._common import ddl_for, json_text, touch_record

_INSERT_SQL = text(
    f"INSERT INTO {PACKAGE_TABLE} (id, scope, package, semver, kind, project, package_title, "
    "content, content_sha256, changelog, drafted_by, last_seq) "
    "VALUES (:id, :scope, :package, :semver, :kind, :project, :package_title, :content, "
    ":content_sha256, :changelog, :drafted_by, :last_seq)"
)
_REVISE_SQL = text(
    f"UPDATE {PACKAGE_TABLE} SET content = :content, content_sha256 = :content_sha256, "
    "package_title = :package_title, changelog = :changelog, base_ref = NULL, "
    "classification = NULL, classification_digest = NULL, worst_class = NULL, impact = NULL, "
    "impact_sha256 = NULL, analysed_sha256 = NULL, last_seq = :last_seq WHERE id = :id"
)
_ANALYSE_SQL = text(
    f"UPDATE {PACKAGE_TABLE} SET base_ref = :base_ref, classification = :classification, "
    "classification_digest = :classification_digest, worst_class = :worst_class, "
    "impact = :impact, impact_sha256 = :impact_sha256, analysed_sha256 = :analysed_sha256, "
    "last_seq = :last_seq WHERE id = :id"
)


def _update(assignments: str) -> Any:
    return text(f"UPDATE {PACKAGE_TABLE} SET {assignments}, last_seq = :last_seq WHERE id = :id")


#: The events that move one or two columns: event type, statement, payload fields it binds.
_SIMPLE: dict[str, tuple[Any, tuple[tuple[str, str], ...]]] = {
    PACKAGE_SUBMITTED: (
        _update("submitted_by = :submitted_by"),
        (("submitted_by", "submitted_by"),),
    ),
    PACKAGE_CHANGES_REQUESTED: (_update("approved_by = NULL, approved_digest = NULL"), ()),
    PACKAGE_APPROVED: (
        _update("approved_by = :approved_by, approved_digest = :approved_digest"),
        (("approved_by", "approver"), ("approved_digest", "classification_digest")),
    ),
}
_STAMPED: dict[str, Any] = {
    PACKAGE_PUBLISHED: _update("published_at = :stamp"),
    PACKAGE_DEPRECATED: _update("deprecated_at = :stamp"),
    PACKAGE_RETIRED: _update("retired_at = :stamp"),
}
HANDLED = frozenset(
    {
        PACKAGE_DRAFTED,
        PACKAGE_REVISED,
        PACKAGE_ANALYSED,
        PACKAGE_SUBMITTED,
        PACKAGE_CHANGES_REQUESTED,
        PACKAGE_APPROVED,
        PACKAGE_PUBLISHED,
        PACKAGE_DEPRECATED,
        PACKAGE_RETIRED,
    }
)


class SchemaPackageProjector:
    name = "schemareg_schema_package"
    handles = HANDLED

    def ddl(self, dialect: str) -> list[str]:
        return ddl_for(PACKAGE_TABLE, dialect) + ddl_for(PACKAGE_VIEW, dialect)

    def apply(self, conn: Connection, event: Event) -> None:
        kind = event.event_type
        if kind not in HANDLED:
            raise ValueError(f"SchemaPackageProjector cannot apply event type: {kind}")
        if kind == PACKAGE_PUBLISHED and event.stream_type != SCHEMA_PACKAGE:
            return  # a core event of that name on some other stream: not ours
        payload: dict[str, Any] = event.payload
        stamp = iso_utc(event.recorded_at)
        if kind == PACKAGE_DRAFTED:
            conn.execute(
                _INSERT_SQL,
                {
                    "id": event.stream_id,
                    "scope": event.scope,
                    "package": payload["package"],
                    "semver": payload["version"],
                    "kind": payload["kind"],
                    "project": payload.get("project"),
                    "package_title": payload.get("package_title"),
                    "content": payload["content"],
                    "content_sha256": payload["content_sha256"],
                    "changelog": payload.get("changelog"),
                    "drafted_by": payload["drafted_by"],
                    "last_seq": event.seq,
                },
            )
        elif kind == PACKAGE_REVISED:
            conn.execute(
                _REVISE_SQL,
                {
                    "id": event.stream_id,
                    "content": payload["content"],
                    "content_sha256": payload["content_sha256"],
                    "package_title": payload.get("package_title"),
                    "changelog": payload.get("changelog"),
                    "last_seq": event.seq,
                },
            )
        elif kind == PACKAGE_ANALYSED:
            conn.execute(
                _ANALYSE_SQL,
                {
                    "id": event.stream_id,
                    "base_ref": payload.get("base_ref"),
                    "classification": json_text(payload["classification"]),
                    "classification_digest": payload["classification_digest"],
                    "worst_class": payload["worst_class"],
                    "impact": json_text(payload["impact"]),
                    "impact_sha256": payload["impact_sha256"],
                    "analysed_sha256": payload["content_sha256"],
                    "last_seq": event.seq,
                },
            )
        elif kind in _SIMPLE:
            statement, binds = _SIMPLE[kind]
            params: dict[str, Any] = {"id": event.stream_id, "last_seq": event.seq}
            params.update({column: payload[field] for column, field in binds})
            conn.execute(statement, params)
        else:
            conn.execute(
                _STAMPED[kind], {"id": event.stream_id, "last_seq": event.seq, "stamp": stamp}
            )
        touch_record(conn, event)

    def reset(self, conn: Connection) -> None:
        conn.execute(text(f"DELETE FROM {PACKAGE_TABLE}"))
