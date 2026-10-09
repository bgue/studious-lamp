"""Lint rules over package documents (brief 27.6).

The rule table (L001 to L007) is the specification. Rules that look at one document or one
property are plain loops; the cross-package rules (L003 orphan code lists, L005 similar names)
see the whole document set at once.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass
from difflib import SequenceMatcher
from typing import Literal

from tl_schema.packages import CodeList, PackageDoc, PropertyDef

#: Two normalised property names at or above this difflib ratio are similar (L005).
SIMILARITY_THRESHOLD = 0.85
#: Minimum length of a description after stripping whitespace (L001).
MIN_DESCRIPTION_LENGTH = 10
#: Minimum number of values in a code list (L006).
MIN_CODE_VALUES = 2
#: A record type in ``applies_to``: ``<module>.<Class>``, e.g. ``core.Record`` (L007).
APPLIES_TO_PATTERN = re.compile(r"[a-z][a-z0-9_]*\.[A-Z][A-Za-z0-9]*")
_SHORT_DESCRIPTION = f"description is shorter than {MIN_DESCRIPTION_LENGTH} characters"


@dataclass(frozen=True)
class LintIssue:
    severity: Literal["error", "warning"]
    rule: str  # "L001" ... "L007"
    package: str  # "name@version"
    path: str  # "psets.valve_data.properties.size_in", "code_lists.MaterialCode"
    message: str


@dataclass(frozen=True)
class _Property:
    """One property of the set: a pset property, or a custom property of an extension."""

    package: str  # "name@version" of the document that declares it
    path: str
    name: str
    definition: PropertyDef


def lint_documents(docs: Sequence[PackageDoc]) -> list[LintIssue]:
    """Apply every lint rule to ``docs`` (the whole set at once, so cross-package rules work).

    Sorted by ``(package, path, rule)``. The rule table is in the ticket.
    """
    properties = _properties(docs)
    issues: list[LintIssue] = []
    for doc in docs:
        issues.extend(_pset_issues(doc))
        for list_name, code_list in doc.code_lists.items():
            issues.extend(_code_list_issues(doc.key(), list_name, code_list))
    issues.extend(_property_issues(properties))
    issues.extend(_orphan_code_list_issues(docs, properties))
    issues.extend(_similar_name_issues(properties))
    return sorted(issues, key=lambda issue: (issue.package, issue.path, issue.rule))


def _issue(
    rule: str,
    package: str,
    path: str,
    message: str,
    severity: Literal["error", "warning"] = "warning",
) -> LintIssue:
    return LintIssue(severity=severity, rule=rule, package=package, path=path, message=message)


def _too_short(text: str) -> bool:
    return len(text.strip()) < MIN_DESCRIPTION_LENGTH


def _properties(docs: Sequence[PackageDoc]) -> list[_Property]:
    """Every property of the set: pset properties, then extension custom properties."""
    found: list[_Property] = []
    for doc in docs:
        for pset_name, pset in doc.psets.items():
            for prop_name, definition in pset.properties.items():
                path = f"psets.{pset_name}.properties.{prop_name}"
                found.append(_Property(doc.key(), path, prop_name, definition))
        for entry in doc.extends:
            pset_name = entry.target()[2]
            for prop_name, definition in entry.custom.items():
                path = f"extends.{pset_name}.custom.{prop_name}"
                found.append(_Property(doc.key(), path, prop_name, definition))
    return found


def _pset_issues(doc: PackageDoc) -> list[LintIssue]:
    issues: list[LintIssue] = []
    for pset_name, pset in doc.psets.items():
        path = f"psets.{pset_name}"
        if _too_short(pset.description):
            issues.append(_issue("L001", doc.key(), path, _SHORT_DESCRIPTION))
        for record_type in pset.applies_to:
            if APPLIES_TO_PATTERN.fullmatch(record_type) is None:
                message = f"applies_to {record_type!r} is not <module>.<Class>"
                issues.append(_issue("L007", doc.key(), path, message, severity="error"))
    return issues


def _code_list_issues(package: str, list_name: str, code_list: CodeList) -> list[LintIssue]:
    path = f"code_lists.{list_name}"
    issues: list[LintIssue] = []
    if _too_short(code_list.description):
        issues.append(_issue("L001", package, path, _SHORT_DESCRIPTION))
    if len(code_list.values) < MIN_CODE_VALUES:
        message = f"code list {list_name} has fewer than {MIN_CODE_VALUES} values"
        issues.append(_issue("L006", package, path, message))
    return issues


def _property_issues(properties: Sequence[_Property]) -> list[LintIssue]:
    issues: list[LintIssue] = []
    for prop in properties:
        definition = prop.definition
        if _too_short(definition.description):
            issues.append(_issue("L001", prop.package, prop.path, _SHORT_DESCRIPTION))
        if definition.range == "decimal" and definition.unit is None:
            issues.append(_issue("L002", prop.package, prop.path, "decimal property has no unit"))
        if definition.materialize and not definition.exact_mappings:
            message = "promoted property has no exact_mappings"
            issues.append(_issue("L004", prop.package, prop.path, message))
    return issues


def _orphan_code_list_issues(
    docs: Sequence[PackageDoc], properties: Sequence[_Property]
) -> list[LintIssue]:
    used_ranges = {prop.definition.range for prop in properties}
    issues: list[LintIssue] = []
    for doc in docs:
        for list_name in doc.code_lists:
            if list_name not in used_ranges:
                message = f"code list {list_name} is not used by any property"
                issues.append(_issue("L003", doc.key(), f"code_lists.{list_name}", message))
    return issues


def _normal(name: str) -> str:
    return name.replace("_", "").lower()


def _resembles(first: str, second: str) -> bool:
    """Equal once normalised, or similar enough by difflib ratio (L005)."""
    normal_first, normal_second = _normal(first), _normal(second)
    if normal_first == normal_second:
        return True
    ratio = SequenceMatcher(None, normal_first, normal_second).ratio()
    return ratio >= SIMILARITY_THRESHOLD


def _similar_name_issues(properties: Sequence[_Property]) -> list[LintIssue]:
    """Report each property against every earlier one in (package, path) order (L005).

    The issue sits on the later property and names the earlier one. Equal names never pair:
    the same name in two psets is a deliberate consistency choice.
    """
    ordered = sorted(properties, key=lambda prop: (prop.package, prop.path))
    issues: list[LintIssue] = []
    for index, later in enumerate(ordered):
        for earlier in ordered[:index]:
            if earlier.name == later.name or not _resembles(earlier.name, later.name):
                continue
            message = f"{later.name} resembles {earlier.name} ({earlier.package} {earlier.path})"
            issues.append(_issue("L005", later.package, later.path, message))
    return issues
