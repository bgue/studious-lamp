"""``OutboxRow``: one ``outbox_events`` row as delivery code sees it, and JSON helpers."""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any, cast


def as_object(value: Any) -> dict[str, Any]:
    """``value`` as a JSON object, or ``{}`` when it is anything else (typed for pyright strict)."""
    return cast("dict[str, Any]", value) if isinstance(value, dict) else {}


def as_list(value: Any) -> list[Any]:
    """``value`` as a JSON array, or ``[]`` when it is anything else."""
    return cast("list[Any]", value) if isinstance(value, list) else []


def load_json(value: Any) -> Any:
    """A JSON column value as Python: SQLite returns text, Postgres JSONB returns parsed values."""
    if isinstance(value, (str, bytes, bytearray)):
        return json.loads(value)
    return value


@dataclass(frozen=True)
class OutboxRow:
    """What the outbox knows about one committed event (see ``schema/core/outbox.yaml``)."""

    seq: int
    event_id: str
    scope: str
    event_type: str
    stream_id: str
    stream_type: str
    stream_version: int
    subject_id: str
    actor: str
    recorded_at: str
    correlation_id: str
    schema_version: int = 1
    source: str = ""
    subject_type: str | None = None
    subject_key: str | None = None
    subject_version: int | None = None
    changed_fields: tuple[str, ...] = ()
    from_state: str | None = None
    to_state: str | None = None
    related_ids: tuple[str, ...] = ()
    link_relations: tuple[str, ...] = ()
    file_slot: str | None = None
    hashtags: tuple[str, ...] = ()
    data: Mapping[str, Any] = field(default_factory=dict[str, Any])

    @staticmethod
    def from_mapping(row: Mapping[Any, Any]) -> OutboxRow:
        """Build from a SQLAlchemy ``.mappings()`` row of ``outbox_events``."""

        def items(name: str) -> tuple[str, ...]:
            return tuple(str(item) for item in load_json(row[name]))

        return OutboxRow(
            seq=int(row["seq"]),
            event_id=row["event_id"],
            scope=row["scope"],
            event_type=row["event_type"],
            schema_version=int(row["schema_version"]),
            stream_id=row["stream_id"],
            stream_type=row["stream_type"],
            stream_version=int(row["stream_version"]),
            subject_id=row["subject_id"],
            subject_type=row["subject_type"],
            subject_key=row["subject_key"],
            subject_version=None if row["subject_version"] is None else int(row["subject_version"]),
            actor=row["actor"],
            source=row["source"],
            recorded_at=row["recorded_at"],
            correlation_id=row["correlation_id"],
            changed_fields=items("changed_fields_json"),
            from_state=row["from_state"],
            to_state=row["to_state"],
            related_ids=items("related_ids_json"),
            link_relations=items("link_relations_json"),
            file_slot=row["file_slot"],
            hashtags=items("hashtags_json"),
            data=load_json(row["data_json"]),
        )


OUTBOX_COLUMNS = (
    "seq, event_id, scope, event_type, schema_version, stream_id, stream_type, stream_version, "
    "subject_id, subject_type, subject_key, subject_version, actor, source, recorded_at, "
    "correlation_id, changed_fields_json, from_state, to_state, related_ids_json, "
    "link_relations_json, file_slot, hashtags_json, data_json"
)
