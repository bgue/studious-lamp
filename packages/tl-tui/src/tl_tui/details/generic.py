"""The envelope rows every record has: the Details of a type without a renderer of its own."""

from __future__ import annotations

from typing import Any

from tl_tui.details import TECHNICAL_SECTION, DetailRow, record_rows
from tl_tui.display import Labels, type_label
from tl_tui.text import EMPTY, conformance_mark, short_hash


def _or_empty(value: Any) -> str:
    return EMPTY if value is None or value == "" else str(value)


def technical_rows(record: dict[str, Any]) -> list[DetailRow]:
    """Key, version, scope and schema hash: for the technical mode only."""
    return [
        DetailRow("Key", _or_empty(record.get("key")), True, TECHNICAL_SECTION, False),
        DetailRow("Version", _or_empty(record.get("version")), True, TECHNICAL_SECTION, False),
        DetailRow("Scope", _or_empty(record.get("scope")), True, TECHNICAL_SECTION, False),
        DetailRow(
            "Schema hash",
            short_hash(record.get("effective_schema_hash")),
            True,
            TECHNICAL_SECTION,
            False,
        ),
    ]


def generic_rows(record: dict[str, Any], labels: Labels) -> list[DetailRow]:
    """The envelope rows in sections: the description, a summary, the dates (the title is in the
    record screen's header)."""
    rows: list[DetailRow] = []
    if record.get("description"):
        rows.append(DetailRow("", str(record["description"]), section="Description"))
    rows += [
        DetailRow("Type", type_label(labels, str(record.get("type") or "")), section="Summary"),
        DetailRow("Status", _or_empty(record.get("status")), section="Summary"),
        DetailRow("Conformance", conformance_mark(record.get("conformance")), section="Summary"),
    ]
    return rows + record_rows(record) + technical_rows(record)
