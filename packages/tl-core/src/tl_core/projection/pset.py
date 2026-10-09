"""PsetProjector: ``Pset.ValuesSet`` and pset-carrying record events into pset projections.

Owns ``cur_pset_values`` (the long-form index of brief 5.4) and keeps these ``cur_core_record``
columns in step: ``psets_json`` (values merged by path), ``effective_schema_hash``,
``conformance``, and the promoted ``pset__<pset>__<property>`` columns that exist in the table.

Deterministic: output depends only on the event and on the rows already in the database. The
event payload carries everything schema-derived (``conformance`` after the write, ``units``);
this projector never consults a schema registry. It must be registered after ``RecordProjector``
so a ``Record.Created`` row exists when pset values are synced.

``cur_pset_values`` is always a function of ``psets_json``: after any event that changes the psets
of a record, the record's rows are rebuilt from the new JSON, keeping units already recorded for
unchanged paths. A rebuild of this projector alone replays the pset events over whatever
``cur_core_record`` holds, so rebuild both projectors together.
"""

from __future__ import annotations

import json
from typing import Any, cast

from sqlalchemy import Connection, inspect, text
from tl_schema.ddl_loader import statements
from tl_schema.generators.promoted import TABLE, split_column

from tl_core.ledger import Event, canonical_json, iso_utc

VALUES_SET = "Pset.ValuesSet"
_HANDLED = frozenset({VALUES_SET, "Record.Created", "Record.Updated", "Record.Corrected"})

_LOAD_SQL = text("SELECT psets_json FROM cur_core_record WHERE id = :id")
_VALUES_SET_SQL = text(
    "UPDATE cur_core_record SET psets_json = :psets_json, version = :version, "
    "last_seq = :last_seq, updated_at = :updated_at, effective_schema_hash = :hash, "
    "conformance = :conformance WHERE id = :id"
)
_UNITS_SQL = text(
    "SELECT path, unit FROM cur_pset_values WHERE record_id = :id AND unit IS NOT NULL"
)
_DELETE_SQL = text("DELETE FROM cur_pset_values WHERE record_id = :id")
_INSERT_SQL = text(
    "INSERT INTO cur_pset_values (record_id, scope, path, pset, property_name, layer, value_type, "
    "value_text, value_num, value_bool, value_json, unit, last_seq, updated_at) VALUES "
    "(:record_id, :scope, :path, :pset, :property_name, :layer, :value_type, "
    ":value_text, :value_num, :value_bool, :value_json, :unit, :last_seq, :updated_at)"
)


def set_nested(root: dict[str, Any], segments: list[str], value: Any) -> None:
    """Set ``root[s0][s1]...[sn] = value``, replacing any non-dict on the way."""
    node: dict[str, Any] = root
    for segment in segments[:-1]:
        child: Any = node.get(segment)
        if not isinstance(child, dict):
            child = {}
            node[segment] = child
        node = cast(dict[str, Any], child)
    node[segments[-1]] = value


def unset_nested(root: dict[str, Any], segments: list[str]) -> bool:
    """Remove the value at ``segments`` and any section left empty. ``True`` if it existed."""
    trail: list[tuple[dict[str, Any], str]] = []
    node: dict[str, Any] = root
    for segment in segments[:-1]:
        child: Any = node.get(segment)
        if not isinstance(child, dict):
            return False
        trail.append((node, segment))
        node = cast(dict[str, Any], child)
    if segments[-1] not in node:
        return False
    del node[segments[-1]]
    while trail and not node:
        node, segment = trail.pop()
        del node[segment]
    return True


def apply_values(root: dict[str, Any], pset: str, values: dict[str, Any]) -> None:
    """Merge a ``Pset.ValuesSet`` into ``root``: ``None`` unsets a key, anything else sets it."""
    base = pset.split(".")
    for key, value in values.items():
        segments = [*base, *key.split(".")]
        if value is None:
            unset_nested(root, segments)
        else:
            set_nested(root, segments, value)


def is_property_path(path: list[str]) -> bool:
    """Whether the value at ``path`` (segments below ``psets``) is one property's value.

    A property value is stored whole, whatever its shape: a ``json`` property may hold a dict, and
    an empty dict still leaves a row. Depth by layer: ``<pset>.<property>``,
    ``<pset>.x.<property>``, ``prj.<pset>.<property>``, ``enrich.<app>.<property>`` and
    ``src.<system>.<pset>.<property>``.
    """
    head = path[0]
    if head in ("prj", "enrich"):
        return len(path) == 3
    if head == "src":
        return len(path) == 4
    if len(path) >= 2 and path[1] == "x":
        return len(path) == 3
    return len(path) == 2


def flatten(psets: dict[str, Any]) -> list[tuple[list[str], Any]]:
    """Property values of a nested pset object as ``(segments, value)``, sorted by path.

    Dicts are descended until a property path (``is_property_path``) is reached; a value found
    above that depth that is not a dict (for example a loose scalar) is also a leaf. An empty dict
    above property depth has no leaves.
    """
    leaves: list[tuple[list[str], Any]] = []

    def walk(node: dict[str, Any], prefix: list[str]) -> None:
        for key, value in node.items():
            path = [*prefix, key]
            if isinstance(value, dict) and not is_property_path(path):
                walk(cast(dict[str, Any], value), path)
            else:
                leaves.append((path, cast(Any, value)))

    walk(psets, [])
    return sorted(leaves, key=lambda leaf: leaf[0])


def classify(segments: list[str]) -> tuple[str, str, str]:
    """``(pset, property, layer)`` for the path segments below ``psets`` (brief 6.3 layers)."""
    head = segments[0]
    if head == "prj" and len(segments) >= 3:
        return f"prj.{segments[1]}", ".".join(segments[2:]), "project"
    if head == "enrich" and len(segments) >= 3:
        return f"enrich.{segments[1]}", ".".join(segments[2:]), "enrichment"
    if head == "src" and len(segments) >= 4:
        return ".".join(segments[:3]), ".".join(segments[3:]), "source"
    if len(segments) == 1:
        return head, head, "standard"
    rest = segments[1:]
    layer = "custom" if rest[0] == "x" and len(rest) >= 2 else "standard"
    return head, ".".join(rest), layer


def typed_columns(value: Any) -> dict[str, Any]:
    """The ``value_*`` columns for one leaf value."""
    columns: dict[str, Any] = {
        "value_type": "json",
        "value_text": None,
        "value_num": None,
        "value_bool": None,
        "value_json": None,
    }
    if isinstance(value, bool):
        columns.update(value_type="boolean", value_bool=value)
    elif isinstance(value, (int, float)):
        columns.update(value_type="number", value_num=float(value))
    elif isinstance(value, str):
        columns.update(value_type="string", value_text=value)
    else:
        columns.update(value_json=canonical_json(value))
    return columns


class PsetProjector:
    name = "pset_values"
    handles = _HANDLED

    def ddl(self, dialect: str) -> list[str]:
        if dialect == "sqlite":
            return statements("cur_pset_values", "sqlite")
        if dialect == "postgres":
            return statements("cur_pset_values", "postgres")
        raise ValueError(f"unsupported dialect: {dialect}")

    def apply(self, conn: Connection, event: Event) -> None:
        if event.event_type == VALUES_SET:
            self._values_set(conn, event)
            return
        if event.event_type == "Record.Created":
            touched = "psets" in event.payload
        else:
            touched = "psets" in event.payload.get("changes", {})
        if touched:
            self._sync(conn, event, {})

    def reset(self, conn: Connection) -> None:
        conn.execute(text("DELETE FROM cur_pset_values"))

    def _load(self, conn: Connection, event: Event) -> dict[str, Any]:
        row = conn.execute(_LOAD_SQL, {"id": event.stream_id}).first()
        if row is None:
            raise LookupError(f"no cur_core_record row for stream {event.stream_id}")
        loaded: dict[str, Any] = json.loads(row.psets_json)
        return loaded

    def _values_set(self, conn: Connection, event: Event) -> None:
        payload = event.payload
        psets = self._load(conn, event)
        units: dict[str, str] = {}
        apply_values(psets, str(payload["pset"]), payload["values"])
        declared: dict[str, str] = payload.get("units") or {}
        for key, unit in declared.items():
            units[f"psets.{payload['pset']}.{key}"] = unit
        conn.execute(
            _VALUES_SET_SQL,
            {
                "id": event.stream_id,
                "psets_json": canonical_json(psets),
                "version": event.stream_version,
                "last_seq": event.seq,
                "updated_at": iso_utc(event.recorded_at),
                "hash": payload.get("effective_schema_hash"),
                "conformance": payload.get("conformance", "ok"),
            },
        )
        self._sync(conn, event, units, psets)

    def _sync(
        self,
        conn: Connection,
        event: Event,
        new_units: dict[str, str],
        psets: dict[str, Any] | None = None,
    ) -> None:
        """Rebuild this record's ``cur_pset_values`` rows and promoted columns from its psets."""
        if psets is None:
            psets = self._load(conn, event)
        kept = {r.path: r.unit for r in conn.execute(_UNITS_SQL, {"id": event.stream_id})}
        conn.execute(_DELETE_SQL, {"id": event.stream_id})
        stamp = iso_utc(event.recorded_at)
        for segments, value in flatten(psets):
            path = "psets." + ".".join(segments)
            pset, prop, layer = classify(segments)
            conn.execute(
                _INSERT_SQL,
                {
                    "record_id": event.stream_id,
                    "scope": event.scope,
                    "path": path,
                    "pset": pset,
                    "property_name": prop,
                    "layer": layer,
                    "unit": new_units.get(path, kept.get(path)),
                    "last_seq": event.seq,
                    "updated_at": stamp,
                    **typed_columns(value),
                },
            )
        self._update_promoted(conn, event.stream_id, psets)

    @staticmethod
    def _update_promoted(conn: Connection, record_id: str, psets: dict[str, Any]) -> None:
        assignments: list[str] = []
        params: dict[str, Any] = {"id": record_id}
        for column in inspect(conn).get_columns(TABLE):
            split = split_column(column["name"])
            if split is None:
                continue
            pset, prop = split
            section: Any = psets.get(pset)
            value: Any = (
                cast(dict[str, Any], section).get(prop) if isinstance(section, dict) else None
            )
            param = f"p{len(assignments)}"
            assignments.append(f"{column['name']} = :{param}")
            params[param] = None if isinstance(value, (dict, list)) else value
        if assignments:
            conn.execute(
                text(f"UPDATE {TABLE} SET {', '.join(assignments)} WHERE id = :id"), params
            )
