"""The envelope rows every record has: the Details of a type without a renderer of its own."""

from __future__ import annotations

from typing import Any

from tl_tui.details import DetailRow
from tl_tui.display import Labels, type_label
from tl_tui.text import EMPTY, conformance_mark, short_hash, timestamp


def _or_empty(value: Any) -> str:
    return EMPTY if value is None or value == "" else str(value)


def technical_rows(record: dict[str, Any]) -> list[DetailRow]:
    """Key, version, scope and schema hash: for the technical mode only."""
    return [
        DetailRow("Key", _or_empty(record.get("key")), technical=True),
        DetailRow("Version", _or_empty(record.get("version")), technical=True),
        DetailRow("Scope", _or_empty(record.get("scope")), technical=True),
        DetailRow("Schema hash", short_hash(record.get("effective_schema_hash")), technical=True),
    ]


def generic_rows(record: dict[str, Any], labels: Labels) -> list[DetailRow]:
    rows = [
        DetailRow("Type", type_label(labels, str(record.get("type") or ""))),
        DetailRow("Title", _or_empty(record.get("title"))),
    ]
    if record.get("description"):
        rows.append(DetailRow("Description", str(record["description"])))
    rows += [
        DetailRow("Status", _or_empty(record.get("status"))),
        DetailRow("Created", timestamp(record.get("created_at"))),
        DetailRow("Updated", timestamp(record.get("updated_at"))),
        DetailRow("Conformance", conformance_mark(record.get("conformance"))),
    ]
    return rows + technical_rows(record)
