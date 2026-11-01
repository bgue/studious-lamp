"""The Properties tab's text, apart from Textual (P2-WEB1-S6; moved from ``widgets/psets_tab``).

``psets_text`` builds the whole tab from the form metadata, the record and the conformance report;
the terminal's ``PsetsTab`` and the web record page both show it. No ``textual`` or ``rich`` here.
"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from typing import Any, cast

from tl_schema.forms import ConformanceReport, FieldMeta, FormMetadata, PsetGroupMeta

from tl_tui.display import pset_label, rule_phrase
from tl_tui.paths import pset_value
from tl_tui.text import EMPTY, conformance_mark, format_value, short_hash, unit_label

HEADER = f"{'Property':<28}{'Value':<24}{'Layer':<12}Rule"
CUSTOM_RULE = "custom field"  # the rule column of a field the schema does not declare
ADD_LINE = "[+] Add property"  # the key is `plus` on the record screen
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


def adhoc_lines(group: PsetGroupMeta, psets: dict[str, Any]) -> list[str]:
    """The custom fields the record holds in ``group`` that its schema does not declare (P1-UX3
    round 4), one line each, in the set's custom section, with the layer ``custom``."""
    held = pset_value(psets, f"psets.{group.name}.x") if group.custom_allowed else None
    if not isinstance(held, dict):
        return []
    declared = {field.path for field in group.fields}
    lines: list[str] = []
    for name in sorted(cast(dict[str, Any], held)):
        if f"psets.{group.name}.x.{name}" in declared:
            continue
        value = format_value(cast(dict[str, Any], held)[name])
        label = name.replace("_", " ").capitalize()
        lines.append(f"  {label:<26}{value:<24}{'custom':<12}{CUSTOM_RULE}  ✓")
    return lines


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
        lines.extend(adhoc_lines(group, record["psets"]))
    lines.append("")
    lines.append(LEGEND)
    last = f"Conformance: {conformance_mark(report.status)}"
    if technical:
        last += f"   Effective schema {short_hash(report.effective_schema_hash)}"
    lines.append(last)
    return "\n".join(lines)
