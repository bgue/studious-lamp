"""Conformance of a record's pset values against an effective schema (brief 6.3, 27.5).

``evaluate`` is the one place that turns schema rules into ``ok`` / ``warning`` / ``nonconformant``
/ ``waived``. It is pure: the caller supplies the record's type, state and psets and the date.

Rules
-----
Value issues come from ``validate_psets`` (``tl_schema.validation``) and map to rules:

=====================  ===============================================================
JSON Schema keyword    conformance ``rule``
=====================  ===============================================================
``type``               ``type``
``minimum``/``maximum``  ``range``
``pattern``            ``pattern`` (``type`` for date and datetime properties)
``enum``               ``value_list`` (a value outside the property's list, whatever the policy)
``additionalProperties``  ``locked`` for a custom section in a pset that forbids it, else ``type``
=====================  ===============================================================

Missing values: a pset is *engaged* for a record when it applies to the record type and the record
has any value in it, or when it is ``mandatory`` and has no ``class_filter``. For every property of
an engaged pset with no value, a ``required_in_state`` issue arises when the property's
``required_in_states`` contains ``"*"`` or the record's state.

Level: an issue on a property takes the property's enforcement (``advisory`` gives ``warning``;
``required`` and ``locked`` give ``nonconformant``); an issue with no property takes its pset's
enforcement. Project mode then adjusts: ``lenient`` (until ``lenient_until``, if set) relaxes
required-ness only, so a missing value for a ``required`` or ``locked`` property is a ``warning``;
type, range, pattern, value-list and locked-extension issues keep their level in every mode (they
are data or governance errors, and waivers are the tool for them); ``strict_with_waivers`` drops
issues on the exact path of a waiver that has not expired. If waivers dropped issues and none
remain the status is ``waived``. (A waiver that drops an issue while others remain is not shown:
``ConformanceReport`` has no waived list.)

Crosswalks do not change conformance: a project-added code is in the property's list and so valid;
the crosswalk is for cross-project reporting.
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import date
from typing import Any, Literal, cast

from tl_schema.effective import (
    ALWAYS,
    EffectivePset,
    EffectiveSchema,
    required_in,
    resolve_path,
)
from tl_schema.forms import ConformanceIssue, ConformanceReport
from tl_schema.validation import ValueIssue, validate_psets

Level = Literal["warning", "nonconformant"]

_RULE_FOR_KEYWORD: dict[str, str] = {
    "type": "type",
    "minimum": "range",
    "maximum": "range",
    "exclusiveMinimum": "range",
    "exclusiveMaximum": "range",
    "pattern": "pattern",
    "enum": "value_list",
}


def _strip_none(value: Any) -> Any:
    """Copy of ``value`` without ``None`` leaves: an explicit null means "no value"."""
    if isinstance(value, dict):
        node = cast(dict[str, Any], value)
        return {k: _strip_none(v) for k, v in node.items() if v is not None}
    return value


def _walk(psets: Mapping[str, Any], segments: list[str]) -> Any:
    """The value at ``segments`` below ``psets``, or ``None`` when the path does not exist."""
    node: Any = psets
    for segment in segments:
        if not isinstance(node, dict):
            return None
        node = cast(dict[str, Any], node).get(segment)
    return node


def _lookup(psets: Mapping[str, Any], pset: str, key: str) -> Any:
    return _walk(psets, [*pset.split("."), *key.split(".")])


def _has_values(psets: Mapping[str, Any], pset: EffectivePset) -> bool:
    node = _walk(psets, pset.name.split("."))
    return isinstance(node, dict) and len(cast(dict[str, Any], node)) > 0


def _engaged(psets: Mapping[str, Any], pset: EffectivePset) -> bool:
    if _has_values(psets, pset):
        return True
    return pset.adoption == "mandatory" and pset.class_filter is None


def _level(enforcement: str) -> Level:
    return "warning" if enforcement == "advisory" else "nonconformant"


def _value_issue(schema: EffectiveSchema, issue: ValueIssue) -> tuple[str, str, str]:
    """``(rule, enforcement, message)`` for one validator issue."""
    found = resolve_path(schema, issue.path)
    if found is not None:
        pset, key = found
        prop = pset.find(key)
        assert prop is not None
        rule = _RULE_FOR_KEYWORD.get(issue.keyword, "type")
        if rule == "pattern" and prop.kind in ("date", "datetime"):
            rule = "type"
        return rule, prop.enforcement, f"{prop.label}: {issue.message}"
    rest = issue.path[len("psets.") :]
    for name in sorted(schema.psets, key=len, reverse=True):
        pset = schema.psets[name]
        if rest == name or rest.startswith(name + "."):
            if rest == f"{name}.x" and not pset.custom_allowed:
                return "locked", pset.enforcement, f"{name} does not allow a custom section"
            return "type", pset.enforcement, issue.message
    return "type", "advisory", issue.message


def _missing_issues(
    schema: EffectiveSchema, record_type: str, psets: Mapping[str, Any], state: str | None
) -> list[tuple[str, str, str, str]]:
    """``(path, rule, enforcement, message)`` for each required property without a value."""
    found: list[tuple[str, str, str, str]] = []
    for pset in schema.for_record_type(record_type):
        if not _engaged(psets, pset):
            continue
        for prop in pset.all_properties():
            if _lookup(psets, pset.name, prop.relative_key()) is not None:
                continue
            if not required_in(prop.required_in_states, state):
                continue
            where = "" if ALWAYS in prop.required_in_states else f" in state {state}"
            found.append(
                (
                    f"psets.{pset.name}.{prop.relative_key()}",
                    "required_in_state",
                    prop.enforcement,
                    f"{prop.label} is required{where}",
                )
            )
    return found


def evaluate(
    schema: EffectiveSchema,
    record_type: str,
    psets: Mapping[str, Any],
    *,
    state: str | None = None,
    on: date,
) -> ConformanceReport:
    """Conformance of ``psets`` (the record's ``psets`` object) in ``state`` on date ``on``."""
    settings = schema.conformance
    lenient = settings.mode == "lenient" and (
        settings.lenient_until is None or on <= settings.lenient_until
    )
    waived_paths = (
        {w.path for w in settings.waivers if w.expires is None or on <= w.expires}
        if settings.mode == "strict_with_waivers"
        else set[str]()
    )

    clean = _strip_none(dict(psets))
    raw: list[tuple[str, str, str, str]] = []
    for issue in validate_psets(schema, record_type, clean):
        rule, enforcement, message = _value_issue(schema, issue)
        raw.append((issue.path, rule, enforcement, message))
    raw.extend(_missing_issues(schema, record_type, clean, state))

    issues: list[ConformanceIssue] = []
    suppressed = 0
    for path, rule, enforcement, message in sorted(raw):
        if path in waived_paths:
            suppressed += 1
            continue
        relaxed = lenient and rule == "required_in_state"
        level: Level = "warning" if relaxed else _level(enforcement)
        issues.append(ConformanceIssue(path=path, level=level, rule=rule, message=message))

    status: Literal["ok", "warning", "nonconformant", "waived"]
    if any(i.level == "nonconformant" for i in issues):
        status = "nonconformant"
    elif issues:
        status = "warning"
    elif suppressed:
        status = "waived"
    else:
        status = "ok"
    return ConformanceReport(status=status, issues=issues, effective_schema_hash=schema.hash)
