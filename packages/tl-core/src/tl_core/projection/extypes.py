"""Projectors of the extension type registry (P0-I8 workstream B; brief 31).

* ``TypeRegistrationProjector``: ``TypeRegistration.*`` events into ``cur_core_type_registration``,
  one row per registered type version.
* ``RecordBodyProjector``: ``Record.BodyStored`` into ``cur_core_record_body``, the pointer to the
  current body of an object-backed record.
* ``BodyQuarantineTable``: creates ``tl_body_quarantine``, operational state that no event produces
  (a rebuild must never clear a quarantine), like the ``wh_*`` tables.

Deterministic: every value comes from the event and from rows already there.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import Connection, text
from tl_schema.ddl_loader import statements

from tl_core.extypes.names import LayoutError, parse_type_ref, pset_name
from tl_core.extypes.types import (
    RECORD_BODY_STORED,
    TYPE_DEPRECATED,
    TYPE_QUARANTINED,
    TYPE_REGISTERED,
)
from tl_core.ledger import Event, canonical_json, iso_utc

_TYPE_EVENTS = frozenset({TYPE_REGISTERED, TYPE_QUARANTINED, TYPE_DEPRECATED})

_FIND = text("SELECT status FROM cur_core_type_registration WHERE type_ref = :type_ref")
_INSERT = text(
    "INSERT INTO cur_core_type_registration (type_ref, type_name, namespace, name, version, pset, "
    "location_uri, content_hash, owner, status, storage_mode, index_fields_json, schema_hash, "
    "report_json, conflict_hash, reason, first_seq, last_seq, version_n, updated_at) VALUES "
    "(:type_ref, :type_name, :namespace, :name, :version, :pset, :location_uri, :content_hash, "
    ":owner, :status, :storage_mode, :index_fields_json, :schema_hash, :report_json, "
    ":conflict_hash, :reason, :seq, :seq, :version_n, :updated_at)"
)
_REGISTER = text(
    "UPDATE cur_core_type_registration SET type_name = :type_name, namespace = :namespace, "
    "name = :name, version = :version, pset = :pset, location_uri = :location_uri, "
    "content_hash = :content_hash, owner = :owner, "
    "status = CASE WHEN status = 'deprecated' THEN 'deprecated' ELSE 'active' END, "
    "storage_mode = :storage_mode, "
    "index_fields_json = :index_fields_json, schema_hash = :schema_hash, report_json = NULL, "
    "conflict_hash = NULL, reason = CASE WHEN status = 'deprecated' THEN reason ELSE NULL END, "
    "last_seq = :seq, version_n = :version_n, "
    "updated_at = :updated_at WHERE type_ref = :type_ref"
)
_QUARANTINE_AGAIN = text(
    "UPDATE cur_core_type_registration SET location_uri = :location_uri, "
    "content_hash = :content_hash, report_json = :report_json, last_seq = :seq, "
    "version_n = :version_n, updated_at = :updated_at WHERE type_ref = :type_ref"
)
_CONFLICT = text(
    "UPDATE cur_core_type_registration SET conflict_hash = :content_hash, "
    "report_json = :report_json, last_seq = :seq, version_n = :version_n, "
    "updated_at = :updated_at WHERE type_ref = :type_ref"
)
_DEPRECATE = text(
    "UPDATE cur_core_type_registration SET status = 'deprecated', reason = :reason, "
    "last_seq = :seq, version_n = :version_n, updated_at = :updated_at "
    "WHERE type_ref = :type_ref"
)


class TypeRegistrationProjector:
    name = "type_registrations"
    handles = _TYPE_EVENTS

    def ddl(self, dialect: str) -> list[str]:
        if dialect == "sqlite" or dialect == "postgres":
            return statements("cur_core_type_registration", dialect)
        raise ValueError(f"unsupported dialect: {dialect}")

    def reset(self, conn: Connection) -> None:
        conn.execute(text("DELETE FROM cur_core_type_registration"))

    def apply(self, conn: Connection, event: Event) -> None:
        payload = event.payload
        type_ref: str = payload["type_ref"]
        found = conn.execute(_FIND, {"type_ref": type_ref}).first()
        status: str | None = None if found is None else str(found.status)
        common: dict[str, Any] = {
            "type_ref": type_ref,
            "seq": event.seq,
            "version_n": event.stream_version,
            "updated_at": iso_utc(event.recorded_at),
        }
        if event.event_type == TYPE_REGISTERED:
            self._registered(conn, payload, common, exists=status is not None)
        elif event.event_type == TYPE_QUARANTINED:
            self._quarantined(conn, payload, common, status)
        else:
            if status is None:
                raise LookupError(f"no registration row for {type_ref}")
            conn.execute(_DEPRECATE, {**common, "reason": payload["reason"]})

    @staticmethod
    def _registered(
        conn: Connection, payload: dict[str, Any], common: dict[str, Any], *, exists: bool
    ) -> None:
        values: dict[str, Any] = {
            **common,
            "type_name": f"{payload['namespace']}.{payload['name']}",
            "namespace": payload["namespace"],
            "name": payload["name"],
            "version": payload["version"],
            "pset": pset_name(payload["namespace"], payload["name"]),
            "location_uri": payload["location_uri"],
            "content_hash": payload["content_hash"],
            "owner": payload["owner"],
            "storage_mode": payload["storage_mode"],
            "index_fields_json": canonical_json(payload["index_fields"]),
            "schema_hash": payload["schema_hash"],
        }
        if exists:
            conn.execute(_REGISTER, values)
        else:
            conn.execute(
                _INSERT,
                {
                    **values,
                    "status": "active",
                    "report_json": None,
                    "conflict_hash": None,
                    "reason": None,
                },
            )

    @staticmethod
    def _quarantined(
        conn: Connection, payload: dict[str, Any], common: dict[str, Any], status: str | None
    ) -> None:
        report = canonical_json(payload["report"])
        if status is None:
            try:
                coords = parse_type_ref(common["type_ref"])
                parts: dict[str, Any] = {
                    "type_name": coords.type_name,
                    "namespace": coords.namespace,
                    "name": coords.name,
                    "version": coords.version,
                    "pset": pset_name(coords.namespace, coords.name),
                }
            except LayoutError:
                parts = {
                    "type_name": common["type_ref"],
                    "namespace": "",
                    "name": "",
                    "version": "",
                    "pset": None,
                }
            conn.execute(
                _INSERT,
                {
                    **common,
                    **parts,
                    "location_uri": payload["location_uri"],
                    "content_hash": payload["content_hash"],
                    "owner": None,
                    "status": "quarantined",
                    "storage_mode": None,
                    "index_fields_json": None,
                    "schema_hash": None,
                    "report_json": report,
                    "conflict_hash": None,
                    "reason": None,
                },
            )
        elif status == "quarantined":
            conn.execute(
                _QUARANTINE_AGAIN,
                {
                    **common,
                    "location_uri": payload["location_uri"],
                    "content_hash": payload["content_hash"],
                    "report_json": report,
                },
            )
        else:  # a registered version whose files changed: keep it, note the conflict
            conn.execute(
                _CONFLICT,
                {**common, "content_hash": payload["content_hash"], "report_json": report},
            )


_BODY_FIND = text("SELECT body_versions FROM cur_core_record_body WHERE record_id = :record_id")
_BODY_TYPE = text("SELECT type FROM cur_core_record WHERE id = :record_id")
_BODY_INSERT = text(
    "INSERT INTO cur_core_record_body (record_id, scope, type_name, uri, hash, body_size, "
    "schema_hash, body_versions, last_seq, updated_at) VALUES (:record_id, :scope, :type_name, "
    ":uri, :hash, :body_size, :schema_hash, 1, :seq, :updated_at)"
)
_BODY_UPDATE = text(
    "UPDATE cur_core_record_body SET uri = :uri, hash = :hash, body_size = :body_size, "
    "schema_hash = :schema_hash, body_versions = body_versions + 1, last_seq = :seq, "
    "updated_at = :updated_at WHERE record_id = :record_id"
)


class RecordBodyProjector:
    name = "record_bodies"
    handles = frozenset({RECORD_BODY_STORED})

    def ddl(self, dialect: str) -> list[str]:
        if dialect == "sqlite" or dialect == "postgres":
            return statements("cur_core_record_body", dialect)
        raise ValueError(f"unsupported dialect: {dialect}")

    def reset(self, conn: Connection) -> None:
        conn.execute(text("DELETE FROM cur_core_record_body"))

    def apply(self, conn: Connection, event: Event) -> None:
        pointer: dict[str, Any] = event.payload["pointer"]
        values: dict[str, Any] = {
            "record_id": event.stream_id,
            "scope": event.scope,
            "uri": pointer["uri"],
            "hash": pointer["hash"],
            "body_size": pointer["size"],
            "schema_hash": pointer["schema_hash"],
            "seq": event.seq,
            "updated_at": iso_utc(event.recorded_at),
        }
        if conn.execute(_BODY_FIND, {"record_id": event.stream_id}).first() is not None:
            conn.execute(_BODY_UPDATE, values)
            return
        row = conn.execute(_BODY_TYPE, {"record_id": event.stream_id}).first()
        conn.execute(_BODY_INSERT, {**values, "type_name": "" if row is None else str(row.type)})


class BodyQuarantineTable:
    """Creates ``tl_body_quarantine``; handles no event, and a rebuild leaves its rows alone."""

    name = "body_quarantine"
    handles: frozenset[str] = frozenset()

    def ddl(self, dialect: str) -> list[str]:
        if dialect == "sqlite" or dialect == "postgres":
            return statements("tl_body_quarantine", dialect)
        raise ValueError(f"unsupported dialect: {dialect}")

    def apply(self, conn: Connection, event: Event) -> None:
        raise ValueError(f"{self.name} handles no events, got {event.event_type}")

    def reset(self, conn: Connection) -> None:
        """Deliberately empty: a quarantine is operational state, not derived from the ledger."""
