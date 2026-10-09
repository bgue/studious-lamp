"""Psets tab: values grouped by layer with enforcement markers (brief 6.3, sketch 2).

Reads only ``ClientInterface.form_metadata`` and ``ClientInterface.conformance``. The text is
built by ``psets_text`` (a pure function, tested on its own); ``PsetsTab`` shows it.
"""

from __future__ import annotations

from typing import Any, ClassVar

from textual.app import ComposeResult
from textual.containers import VerticalScroll
from textual.widgets import Static
from tl_schema.forms import ConformanceReport, FieldMeta, FormMetadata

from tl_tui.client import ClientInterface
from tl_tui.errors import CLIENT_ERRORS, describe_error
from tl_tui.messages import StatusMessage
from tl_tui.paths import pset_value
from tl_tui.text import EMPTY, conformance_mark, format_value, short_hash, unit_label

HEADER = f"{'Property':<28}{'Value':<24}{'Layer':<12}Rule"
LEGEND = (
    "● required  ○ advisory  ■ locked  ! warning  ✗ nonconformant  ✓ ok  x. project custom section"
)


def rule_text(field: FieldMeta) -> str:
    """The enforcement rule with its symbol, for example ``● required@Design/Installed``."""
    if field.enforcement == "locked":
        text = "■ locked"
    elif field.enforcement == "required":
        text = "● required"
    elif field.enforcement == "advisory":
        text = "○ advisory"
    else:
        text = "optional"
    if field.required_in_states:
        text += "@" + "/".join(field.required_in_states)
    if field.readonly:
        text += " (read-only)"
    return text


def value_text(field: FieldMeta, psets: dict[str, Any]) -> str:
    """The stored value with its unit label, or ``—`` when the value is missing or empty."""
    value = pset_value(psets, field.path)
    if value is None or value == "":
        return EMPTY
    text = format_value(value)
    unit = unit_label(field.unit)
    if unit:
        text = f"{text} {unit}"
    return text


def psets_text(meta: FormMetadata, record: dict[str, Any], report: ConformanceReport) -> str:
    """The whole tab: one block per pset group, then the legend and the conformance line."""
    warned = {issue.path for issue in report.issues if issue.level == "warning"}
    failed = {issue.path for issue in report.issues if issue.level == "nonconformant"}
    lines = [HEADER]
    for group in meta.psets:
        enforcement = group.enforcement or "optional"
        lines.append(f"▾ {group.name}   {group.package} {group.version} · {enforcement}")
        for field in group.fields:
            value = value_text(field, record["psets"])
            rule = rule_text(field)
            line = f"  {field.label:<26}{value:<24}{field.layer:<12}{rule}"
            if field.path in warned:
                mark = "!"
            elif field.path in failed:
                mark = "✗"
            elif value != EMPTY:
                mark = "✓"
            else:
                mark = ""
            if mark:
                line += f"  {mark}"
            lines.append(line)
    lines.append("")
    lines.append(LEGEND)
    lines.append(
        f"Conformance: {conformance_mark(report.status)}   "
        f"Effective schema {short_hash(report.effective_schema_hash)}"
    )
    return "\n".join(lines)


class PsetsTab(VerticalScroll, can_focus=True):
    """Rendered inside the record view's Psets tab. ``show_record`` (re)loads it for a record."""

    DEFAULT_CSS = """
    PsetsTab { overflow-x: auto; padding: 0 1; }
    PsetsTab > #psets-body { width: auto; }
    """
    KEY_HINTS: ClassVar[str] = "↑↓ scroll  Esc back"

    def __init__(
        self,
        client: ClientInterface,
        scope: str,
        *,
        id: str | None = None,  # noqa: A002
    ) -> None:
        super().__init__(id=id)
        self.client = client
        self.scope = scope
        self.record: dict[str, Any] | None = None
        self.text: str = ""

    def compose(self) -> ComposeResult:
        yield Static("", id="psets-body", markup=False)

    def show_record(self, record: dict[str, Any]) -> None:
        """Load the form metadata and conformance for ``record`` and render the tab."""
        self.record = record
        try:
            meta = self.client.form_metadata(self.scope, record["type"])
            report = self.client.conformance(record["id"])
        except NotImplementedError:
            text = "Psets unavailable: the pset services are not installed yet"
        except CLIENT_ERRORS as exc:
            text = f"Psets unavailable: {describe_error(exc)}"
            self.post_message(StatusMessage(describe_error(exc), "error"))
        else:
            text = psets_text(meta, record, report)
        self.text = text
        self.query_one("#psets-body", Static).update(text)
