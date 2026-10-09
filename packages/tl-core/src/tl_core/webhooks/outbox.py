"""The outbox projector: every committed event becomes one ``outbox_events`` row (brief 18.4).

It is registered in ``default_registry`` **last** and sets ``handles_all``, so any unit of work that
runs the registry inline (SQLite, Postgres) writes the row in the same transaction as the event,
with
no adapter-specific outbox code. Delivery then reads the table, never the ledger.

Deterministic, like every projector: a row depends only on the event and on rows the earlier
projectors wrote for the same event (``cur_core_record``, ``cur_links``, ``cur_files``), so a
rebuild reproduces it. It must therefore run after ``RecordProjector``, ``LinkProjector`` and
``FileProjector``.

**Subject.** The ordering key of delivery is the record an event is about, not the stream it was
appended to. Link events belong to the link's stream but are about the record at the link's ``from``
end; file events are about the file's record; a numbering allocation is about the record it
numbered.
Everything else is about its own stream.

**Confidentiality.** Restricted confidentiality is not modelled yet (Phase 1). The hook is
``tl_core.webhooks.envelope.ConfidentialityPolicy``: it can force ``thin`` per row at delivery
preparation. The outbox stores the full ``data`` regardless; the policy decides what leaves.
"""

from __future__ import annotations

import json
from typing import Any

from sqlalchemy import Connection, text
from tl_schema.ddl_loader import statements

from tl_core.ledger import Event, iso_utc
from tl_core.webhooks.rows import as_list, as_object, load_json

LINK_PREFIX = "Link."
FILE_PREFIX = "File."

_INSERT_SQL = text(
    "INSERT INTO outbox_events (seq, event_id, scope, event_type, schema_version, stream_id, "
    "stream_type, stream_version, subject_id, subject_type, subject_key, subject_version, actor, "
    "source, recorded_at, correlation_id, changed_fields_json, from_state, to_state, "
    "related_ids_json, link_relations_json, file_slot, hashtags_json, data_json) VALUES "
    "(:seq, :event_id, :scope, :event_type, :schema_version, :stream_id, :stream_type, "
    ":stream_version, :subject_id, :subject_type, :subject_key, :subject_version, :actor, "
    ":source, :recorded_at, :correlation_id, :changed_fields, :from_state, :to_state, "
    ":related_ids, :link_relations, :file_slot, :hashtags, :data)"
)
_RECORD_SQL = text("SELECT type, key, version FROM cur_core_record WHERE id = :id")
_LINK_SQL = text("SELECT from_id, to_id, relation FROM cur_links WHERE link_id = :id")
_FILE_SQL = text("SELECT record_id, slot FROM cur_files WHERE file_id = :id")


def _json(value: Any) -> str:
    """Canonical JSON text, the same form the ledger hashes."""
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def leaf_paths(prefix: str, value: Any) -> dict[str, Any]:
    """Flatten nested objects to dotted paths: ``{"a": {"b": 1}}`` under ``x`` gives ``{"x.a.b":
    1}``.

    A value that is not an object (including a list) is a leaf. An empty object is a leaf too, so a
    cleared section still shows up as a change.
    """
    if isinstance(value, dict) and value:
        obj = as_object(value)
        found: dict[str, Any] = {}
        for key in sorted(obj):
            found.update(leaf_paths(f"{prefix}.{key}" if prefix else key, obj[key]))
        return found
    return {prefix: value}


def _diff_leaves(prefix: str, old: Any, new: Any) -> dict[str, list[Any]]:
    before, after = leaf_paths(prefix, old or {}), leaf_paths(prefix, new or {})
    return {
        path: [before.get(path), after.get(path)]
        for path in sorted(set(before) | set(after))
        if before.get(path) != after.get(path)
    }


def event_changes(event: Event) -> dict[str, list[Any]]:
    """The ``data.changes`` of an event: field path to ``[old, new]``.

    ``old`` is null when the event does not carry it (``Pset.ValuesSet`` records only the new
    values;
    a created record has no old values). Property-set values are flattened to
    ``psets.<pset>.<path>``.
    """
    payload = event.payload
    kind = event.event_type
    if kind == "Record.Created":
        changes: dict[str, list[Any]] = {}
        for name in ("title", "description", "key"):
            if payload.get(name) is not None:
                changes[name] = [None, payload[name]]
        for path, value in leaf_paths("psets", payload.get("psets") or {}).items():
            if path != "psets":
                changes[path] = [None, value]
        return changes
    if kind in ("Record.Updated", "Record.Corrected"):
        changes = {}
        raw_changes = as_object(payload.get("changes"))
        for name in sorted(raw_changes):
            pair = as_list(raw_changes[name])
            if name == "psets" and len(pair) == 2:
                changes.update(_diff_leaves("psets", pair[0], pair[1]))
            else:
                changes[name] = pair
        return changes
    if kind == "Pset.ValuesSet":
        pset = str(payload.get("pset", ""))
        return {
            path: [None, value]
            for path, value in leaf_paths(f"psets.{pset}", payload.get("values") or {}).items()
        }
    if kind == "Workflow.Transitioned":
        return {"status": [payload.get("from_state"), payload.get("to_state")]}
    return {}


class OutboxProjector:
    """One row per event. ``lookups=False`` skips the reads of other projections (tests that
    register the outbox without them); subjects then come from the event alone."""

    name = "outbox"
    handles: frozenset[str] = frozenset()
    handles_all = True

    def __init__(self, *, lookups: bool = True) -> None:
        self._lookups = lookups

    def ddl(self, dialect: str) -> list[str]:
        if dialect == "sqlite" or dialect == "postgres":
            return statements("outbox_events", dialect)
        raise ValueError(f"unsupported dialect: {dialect}")

    def reset(self, conn: Connection) -> None:
        conn.execute(text("DELETE FROM outbox_events"))

    def apply(self, conn: Connection, event: Event) -> None:
        payload = event.payload
        subject_id = event.stream_id
        related: list[str] = []
        relations: list[str] = []
        file_slot: str | None = None
        links: list[dict[str, Any]] = []

        if event.event_type.startswith(LINK_PREFIX):
            from_id, to_id, relation = payload.get("from_ref"), payload.get("to_ref"), None
            relation = payload.get("relation")
            if (from_id is None or to_id is None or relation is None) and self._lookups:
                row = conn.execute(_LINK_SQL, {"id": event.stream_id}).first()
                if row is not None:
                    from_id = from_id or row.from_id
                    to_id = to_id or row.to_id
                    relation = relation or row.relation
            if isinstance(from_id, str):
                subject_id = from_id
            if isinstance(to_id, str):
                related.append(to_id)
            if isinstance(relation, str):
                relations.append(relation)
                links.append({"rel": relation, "id": to_id if isinstance(to_id, str) else None})
        elif event.event_type.startswith(FILE_PREFIX):
            record_id, file_slot = payload.get("record_id"), payload.get("slot")
            if record_id is None and self._lookups:
                row = conn.execute(_FILE_SQL, {"id": event.stream_id}).first()
                if row is not None:
                    record_id, file_slot = row.record_id, file_slot or row.slot
            if isinstance(record_id, str):
                subject_id = record_id
        elif event.event_type == "Numbering.Allocated" and isinstance(
            payload.get("record_id"), str
        ):
            subject_id = payload["record_id"]

        subject_type: str | None = None
        subject_key: str | None = None
        subject_version: int | None = (
            event.stream_version if subject_id == event.stream_id else None
        )
        if self._lookups:
            row = conn.execute(_RECORD_SQL, {"id": subject_id}).first()
            if row is not None:
                subject_type, subject_key = row.type, row.key
                if subject_id != event.stream_id:
                    # Only for a subject other than the stream: the stream's own version is exact
                    # and deterministic, the record's current version is not (a partial rebuild
                    # would read a later one).
                    subject_version = int(row.version)
        if subject_type is None and event.event_type == "Record.Created":
            subject_type, subject_key = payload.get("record_type"), payload.get("key")

        changes = event_changes(event)
        from_state = to_state = None
        if event.event_type == "Workflow.Transitioned":
            from_state, to_state = payload.get("from_state"), payload.get("to_state")
        hashtags = [str(tag).lstrip("#") for tag in as_list(payload.get("hashtags"))]
        data: dict[str, Any] = {
            "origin": {
                "id": subject_id,
                "key": subject_key,
                "type": subject_type,
                "version": subject_version,
            },
            "changes": changes,
            "links": links,
            "detail": payload,
        }
        conn.execute(
            _INSERT_SQL,
            {
                "seq": event.seq,
                "event_id": event.event_id,
                "scope": event.scope,
                "event_type": event.event_type,
                "schema_version": event.schema_version,
                "stream_id": event.stream_id,
                "stream_type": event.stream_type,
                "stream_version": event.stream_version,
                "subject_id": subject_id,
                "subject_type": subject_type,
                "subject_key": subject_key,
                "subject_version": subject_version,
                "actor": event.actor,
                "source": event.source,
                "recorded_at": iso_utc(event.recorded_at),
                "correlation_id": event.correlation_id,
                "changed_fields": _json(sorted(changes)),
                "from_state": from_state,
                "to_state": to_state,
                "related_ids": _json(related),
                "link_relations": _json(relations),
                "file_slot": file_slot,
                "hashtags": _json(hashtags),
                "data": _json(data),
            },
        )


__all__ = ["OutboxProjector", "event_changes", "leaf_paths", "load_json"]
