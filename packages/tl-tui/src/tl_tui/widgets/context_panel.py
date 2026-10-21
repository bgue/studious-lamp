"""Context panel (right panel): follows the grid cursor and summarises the record (sketch 1)."""

from __future__ import annotations

from typing import Any

from textual.containers import VerticalScroll
from textual.widgets import Static

from tl_tui.display import Labels, humanize, mode_of, type_label
from tl_tui.errors import CLIENT_ERRORS
from tl_tui.labels_load import load_labels
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


def _plain_context(record: dict[str, Any], labels: Labels) -> str:
    """The panel in plain words: no version, no schema hash, the type by its label."""
    properties = [
        f"{humanize(path.rsplit('.', 1)[-1])}  {format_value(value)}"
        for path, value in flatten_psets(record.get("psets") or {})
    ]
    lines = [
        record["key"],
        format_value(record.get("title")),
        f"{record.get('status') or EMPTY} · {type_label(labels, record['type'])}",
        conformance_mark(record.get("conformance")),
        "── Properties ──",
        *(properties or ["(none)"]),
    ]
    return "\n".join(lines)


def context_text(
    record: dict[str, Any] | None, labels: Labels | None = None, *, technical: bool = True
) -> str:
    """The plain-text summary shown in the panel; ``None`` gives the empty-cursor hint.

    ``technical=True`` (the default) is the raw text with the version and schema hash; plain mode
    uses ``labels`` for the type and humanized property names.
    """
    if record is None:
        return "No record under the cursor"
    if not technical:
        return _plain_context(record, labels or Labels())
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
        self._labels: dict[tuple[str, str], Labels] = {}  # (scope, record type) -> labels

    def compose(self):  # noqa: ANN201
        yield Static(self.text, id="context-body", markup=False)

    def _labels_for(self, record: dict[str, Any]) -> Labels:
        """The labels for the record's type, read once per scope and type; empty with no client."""
        app = self.app
        client = getattr(app, "client", None)
        scope = getattr(app, "scope", None)
        if client is None or not isinstance(scope, str):
            return Labels()
        key = (scope, str(record.get("type", "")))
        if key not in self._labels:
            try:
                self._labels[key] = load_labels(client, scope, ("core.Record", key[1]))
            except CLIENT_ERRORS:
                self._labels[key] = Labels()
        return self._labels[key]

    def show_record(self, record: dict[str, Any] | None) -> None:
        self.record = record
        technical = mode_of(self.app).technical
        labels = None if record is None else self._labels_for(record)
        self.text = context_text(record, labels, technical=technical)
        self.query_one("#context-body", Static).update(self.text)

    def refresh_for_display_mode(self) -> None:
        """Draw the shown record again with the current display mode."""
        self.show_record(self.record)
