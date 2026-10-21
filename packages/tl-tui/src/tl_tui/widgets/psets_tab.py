"""Properties tab: values grouped by layer with enforcement markers (brief 6.3, sketch 2).

Reads only ``ClientInterface.form_metadata`` (with the record id, so the sets the record's class
binds are listed) and ``ClientInterface.conformance``. The text is built by ``psets_text`` (a pure
function, tested on its own); ``PsetsTab`` shows it. The schema hash shows in technical mode only.
"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from typing import Any, ClassVar

from textual.app import ComposeResult
from textual.containers import VerticalScroll
from textual.widgets import Static
from tl_schema.forms import ConformanceReport, FieldMeta, FormMetadata

from tl_tui.client import ClientInterface
from tl_tui.display import mode_of, pset_label, rule_phrase
from tl_tui.errors import CLIENT_ERRORS, describe_error
from tl_tui.messages import StatusMessage
from tl_tui.paths import pset_value
from tl_tui.text import EMPTY, conformance_mark, format_value, short_hash, unit_label

HEADER = f"{'Property':<28}{'Value':<24}{'Layer':<12}Rule"
LEGEND = (
    "● required  ○ advisory  ■ locked  ! warning  ✗ nonconformant  ✓ ok  x. project custom section"
)


def rule_text(field: FieldMeta) -> str:
    """The rule in words with its symbol, for example ``● required at Design or Installed``."""
    symbol = {"locked": "■ ", "required": "● ", "advisory": "○ "}.get(field.enforcement or "", "")
    return symbol + rule_phrase(field)


_PLACEHOLDER = re.compile(r"\{(\w+)\}")


def _name_of(field: FieldMeta) -> str:
    return field.path.rsplit(".", 1)[-1]


def _placeholder_value(
    name: str,
    psets: dict[str, Any],
    siblings: Sequence[FieldMeta],
    record: Mapping[str, Any] | None,
) -> str:
    """What a unit placeholder such as ``{currency}`` stands for on this record, else ``""``.

    The value of a field of the same set named ``name`` (``currency`` or ``<x>_currency``), else
    the record's own ``name`` value. The stored code is used: ``USD`` is already a unit.
    """
    for other in siblings:
        other_name = _name_of(other)
        if other_name == name or other_name.endswith("_" + name):
            value = pset_value(psets, other.path)
            if value not in (None, ""):
                return str(value)
    value = (record or {}).get(name)
    return "" if value in (None, "") or isinstance(value, (dict, list)) else str(value)


def unit_text(
    field: FieldMeta,
    psets: dict[str, Any],
    siblings: Sequence[FieldMeta] = (),
    record: Mapping[str, Any] | None = None,
) -> str:
    """The unit as a screen shows it: a UCUM code as its label, a ``{name}`` placeholder as the
    record's value for ``name`` (the currency), or nothing when the record has none. A raw
    ``{...}`` never shows."""
    unit = field.unit or ""
    match = _PLACEHOLDER.fullmatch(unit)
    if match is None:
        return unit_label(unit)
    return _placeholder_value(match.group(1), psets, siblings, record)


def _shown(field: FieldMeta, value: Any, *, technical: bool) -> str:
    """A code-list value as its label (the code when the list has no label); technical: the code."""
    if technical or not field.enum_values or isinstance(value, (dict, list)):
        return format_value(value)
    labels = {v.code: v.label for v in field.enum_values}
    return labels.get(str(value)) or format_value(value)


def value_text(
    field: FieldMeta,
    psets: dict[str, Any],
    *,
    technical: bool = False,
    siblings: Sequence[FieldMeta] = (),
    record: Mapping[str, Any] | None = None,
) -> str:
    """The value with its unit label, or ``—`` when the value is missing or empty.

    A code-list value shows its label unless ``technical`` is on, which shows the stored code.
    """
    value = pset_value(psets, field.path)
    if value is None or value == "":
        return EMPTY
    text = _shown(field, value, technical=technical)
    unit = unit_text(field, psets, siblings, record)
    if unit:
        text = f"{text} {unit}"
    return text


def psets_text(
    meta: FormMetadata,
    record: dict[str, Any],
    report: ConformanceReport,
    *,
    technical: bool = False,
) -> str:
    """The whole tab: one block per set, then the legend and the conformance line.

    The schema hash is added to the last line in technical mode only.
    """
    warned = {issue.path for issue in report.issues if issue.level == "warning"}
    failed = {issue.path for issue in report.issues if issue.level == "nonconformant"}
    lines = [HEADER]
    for group in meta.psets:
        enforcement = group.enforcement or "optional"
        lines.append(f"▾ {pset_label(group)} · {enforcement}")
        for field in group.fields:
            value = value_text(
                field,
                record["psets"],
                technical=technical,
                siblings=group.fields,
                record=record,
            )
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
    last = f"Conformance: {conformance_mark(report.status)}"
    if technical:
        last += f"   Effective schema {short_hash(report.effective_schema_hash)}"
    lines.append(last)
    return "\n".join(lines)


class PsetsTab(VerticalScroll, can_focus=True):
    """Rendered inside the record view's Properties tab. ``show_record`` (re)loads it."""

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
        self._loaded: tuple[FormMetadata, ConformanceReport] | None = None

    def compose(self) -> ComposeResult:
        yield Static("", id="psets-body", markup=False)

    def show_record(self, record: dict[str, Any]) -> None:
        """Load the form metadata and conformance for ``record`` and render the tab."""
        self.record = record
        self._loaded = None
        try:
            meta = self.client.form_metadata(self.scope, record["type"], record["id"])
            report = self.client.conformance(record["id"])
        except NotImplementedError:
            text = "Properties unavailable: the property services are not installed yet"
        except CLIENT_ERRORS as exc:
            text = f"Properties unavailable: {describe_error(exc)}"
            self.post_message(StatusMessage(describe_error(exc), "error"))
        else:
            self._loaded = (meta, report)
            text = psets_text(meta, record, report, technical=mode_of(self.app).technical)
        self._show(text)

    def refresh_for_display_mode(self) -> None:
        """Draw the same tab again with the current display mode; no client call."""
        if self.record is not None and self._loaded is not None:
            meta, report = self._loaded
            self._show(psets_text(meta, self.record, report, technical=mode_of(self.app).technical))

    def _show(self, text: str) -> None:
        self.text = text
        self.query_one("#psets-body", Static).update(text)
