"""Context panel (right panel): follows the grid cursor and summarises the record (sketch 1)."""

from __future__ import annotations

from typing import Any

from textual.containers import VerticalScroll
from textual.widgets import Static

from tl_tui.text import EMPTY, conformance_mark, format_value, short_hash


def flatten_psets(psets: dict[str, Any], prefix: str = "") -> list[tuple[str, Any]]:
    """Dotted ``(path, value)`` pairs, depth-first in sorted key order; empty dicts add nothing."""
    pairs: list[tuple[str, Any]] = []
    for key in sorted(psets):
        value = psets[key]
        path = f"{prefix}{key}"
        if isinstance(value, dict):
            pairs.extend(flatten_psets(value, path + "."))
        else:
            pairs.append((path, value))
    return pairs


def context_text(record: dict[str, Any] | None) -> str:
    """The plain-text summary shown in the panel; ``None`` gives the empty-cursor hint."""
    if record is None:
        return "No record under the cursor"
    psets = [
        f"{path}  {format_value(value)}" for path, value in flatten_psets(record.get("psets") or {})
    ]
    lines = [
        f"{record['key']}  v{record['version']}",
        format_value(record.get("title")),
        f"{record.get('status') or EMPTY} · {record['type']}",
        conformance_mark(record.get("conformance")),
        "── Psets ──",
        *(psets or ["(none)"]),
        "── Schema ──",
        short_hash(record.get("effective_schema_hash")),
    ]
    return "\n".join(lines)


class ContextPanel(VerticalScroll, can_focus=True):
    """Shows the record passed to `show_record`, or an empty hint when it is ``None``."""

    def __init__(self, *, id: str | None = None) -> None:  # noqa: A002
        super().__init__(id=id)
        self.record: dict[str, Any] | None = None
        self.text: str = context_text(None)

    def compose(self):  # noqa: ANN201
        yield Static(self.text, id="context-body", markup=False)

    def show_record(self, record: dict[str, Any] | None) -> None:
        self.record = record
        self.text = context_text(record)
        self.query_one("#context-body", Static).update(self.text)
