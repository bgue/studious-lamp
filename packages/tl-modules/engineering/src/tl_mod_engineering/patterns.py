"""Numbering patterns held in the registry: check a number, feed the allocator (brief 6.4, 8).

A registry pattern (``engineering.NumberingPattern``) is a template (``{area}-{mnemonic}-{seq:4}``,
the grammar of ``tl_core.numbering.pattern``) plus a rule for each segment: its role (area,
mnemonic, sequence, other) and where its values come from (a code list, or the mnemonic registry).
``parse_number`` reads a number against it and returns the segments and every problem it finds, so
a person is told all that is wrong with ``47-XX-1`` at once, not one thing per attempt.

A pattern with ``allocate`` true also serves the numbering service: ``ledger_numbering_patterns``
turns it into a ``tl_core.numbering.config.NumberingPattern`` (id ``registry:<code>``), which
``numbering_for(conn)`` adds to the file patterns. A pattern with ``allocate`` false (the tag
pattern: engineers take the number from the drawing) is only checked, never allocated.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date
from typing import Any

from sqlalchemy import Connection
from tl_core.numbering.config import NumberingPattern
from tl_core.numbering.pattern import FIELD_VALUE, Pattern, parse_pattern

from tl_mod_engineering import codelists, registry
from tl_mod_engineering.errors import UnknownCodeError, UnknownCodeListError
from tl_mod_engineering.names import COMPANY

ID_PREFIX = "registry:"


@dataclass(frozen=True)
class SegmentRule:
    name: str
    role: str  # area | mnemonic | sequence | other
    list: str | None = None  # the value must be a usable value of this code list
    registry: str | None = None  # "mnemonic": the value must be an active registered mnemonic


@dataclass(frozen=True)
class RegistryPattern:
    code: str
    record_id: str
    record_type: str
    template: str
    pattern: Pattern
    segments: dict[str, SegmentRule]
    allocate: bool
    gap_free: bool
    scope: str
    reserved: list[tuple[int, int]]


@dataclass(frozen=True)
class NumberIssue:
    segment: str | None  # the segment at fault; None for the number as a whole
    rule: str  # pattern | sequence | unknown_code | inactive_code | unknown_list | unknown_mnemonic
    message: str
    level: str = "error"  # error | warning

    def as_dict(self) -> dict[str, Any]:
        return {
            "segment": self.segment,
            "rule": self.rule,
            "level": self.level,
            "message": self.message,
        }


@dataclass(frozen=True)
class ParsedNumber:
    pattern_code: str
    segments: dict[str, str]  # every segment by name, as written (``seq`` included)
    area: str | None
    mnemonic: str | None
    sequence: int | None
    issues: list[NumberIssue]

    @property
    def ok(self) -> bool:
        return not self.issues


def _pattern(row: registry.StandardRow) -> RegistryPattern:
    data = row.data
    segments = {
        name: SegmentRule(name, str(raw["role"]), raw.get("list"), raw.get("registry"))
        for name, raw in data["segments"].items()
    }
    return RegistryPattern(
        code=row.code,
        record_id=row.id,
        record_type=data["record_type"],
        template=data["template"],
        pattern=parse_pattern(data["template"]),
        segments=segments,
        allocate=bool(data.get("allocate", False)),
        gap_free=bool(data.get("gap_free", True)),
        scope=str(data.get("scope", "project:*")),
        reserved=[(int(a), int(b)) for a, b in data.get("reserved", [])],
    )


def patterns(conn: Connection) -> list[RegistryPattern]:
    """Every active registry numbering pattern, by code."""
    rows = registry.find_standards(conn, scope=COMPANY, kind="numbering_pattern", active_only=True)
    return [_pattern(row) for row in rows]


def pattern_for(conn: Connection, record_type: str) -> RegistryPattern | None:
    """The active registry pattern that numbers ``record_type``, or ``None``."""
    for found in patterns(conn):
        if found.record_type == record_type:
            return found
    return None


def _loose(pattern: RegistryPattern) -> re.Pattern[str]:
    """The pattern with every segment ``[A-Za-z0-9]+``: to find what is wrong with a near miss."""
    parts: list[str] = []
    for segment in pattern.pattern.segments:
        if segment.kind == "literal":
            parts.append(re.escape(segment.text))
        elif segment.kind == "seq":
            parts.append(r"(?P<seq>[A-Za-z0-9]+)")
        else:
            parts.append(rf"(?P<{segment.text}>[A-Za-z0-9]+)")
    return re.compile("".join(parts))


def _sequence_issue(pattern: RegistryPattern, text: str) -> NumberIssue | None:
    width = pattern.pattern.seq_width
    if not text.isdigit() or int(text) < 1:
        return NumberIssue("seq", "sequence", f"the sequence {text!r} must be a number from 1")
    if text != f"{int(text):0{width}d}":
        shown = f"{width} digits, like {1:0{width}d}" if width else "no leading zeros"
        return NumberIssue("seq", "sequence", f"the sequence {text!r} must be written with {shown}")
    return None


def _value_issue(
    conn: Connection, scope: str, rule: SegmentRule, value: str, on: date | None
) -> NumberIssue | None:
    if rule.list is not None:
        try:
            found = codelists.resolve(conn, scope, rule.list, value, on=on)
        except UnknownCodeListError:
            return NumberIssue(
                rule.name, "unknown_list", f"the code list {rule.list} is not registered"
            )
        except UnknownCodeError:
            return NumberIssue(
                rule.name, "unknown_code", f"{value!r} is not a value of {rule.list}"
            )
        if not found.usable:
            return NumberIssue(
                rule.name, "inactive_code", f"{value!r} of {rule.list} is no longer in use"
            )
    elif rule.registry == "mnemonic":
        if registry.active_standard(conn, COMPANY, "mnemonic", value) is None:
            return NumberIssue(
                rule.name, "unknown_mnemonic", f"{value!r} is not a registered mnemonic"
            )
    return None


def parse_number(
    conn: Connection, scope: str, pattern: RegistryPattern, number: str, *, on: date | None = None
) -> ParsedNumber:
    """Read ``number`` against ``pattern`` for a record in ``scope``.

    The sequence must be spelled as the pattern renders it (``0001`` for ``{seq:4}``). A number
    that does not even have the shape of the template has one issue and no segments; a near miss
    (right shape, wrong sequence width) has its segments read and every problem listed, in segment
    order: the sequence first if it is the problem of the shape, then the values. ``area``,
    ``mnemonic`` and ``sequence`` are the segments whose rule has that role.
    """
    segments: dict[str, str] = {}
    issues: list[NumberIssue] = []
    strict = pattern.pattern.parse(number)
    if strict is not None:
        segments = {**strict.fields, "seq": f"{strict.sequence:0{pattern.pattern.seq_width}d}"}
    else:
        match = _loose(pattern).fullmatch(number)
        if match is None:
            issue = NumberIssue(
                None, "pattern", f"{number!r} does not fit the pattern {pattern.template}"
            )
            return ParsedNumber(pattern.code, {}, None, None, None, [issue])
        segments = match.groupdict()
        problem = _sequence_issue(pattern, segments["seq"])
        if problem is not None:
            issues.append(problem)
    for name in pattern.pattern.fields:
        rule = pattern.segments.get(name)
        if rule is None or FIELD_VALUE.fullmatch(segments[name]) is None:
            continue
        found = _value_issue(conn, scope, rule, segments[name], on)
        if found is not None:
            issues.append(found)
    by_role = {rule.role: segments.get(name) for name, rule in pattern.segments.items()}
    sequence_text = segments.get("seq", "")
    return ParsedNumber(
        pattern_code=pattern.code,
        segments=segments,
        area=by_role.get("area"),
        mnemonic=by_role.get("mnemonic"),
        sequence=int(sequence_text) if sequence_text.isdigit() else None,
        issues=issues,
    )


def ledger_numbering_patterns(conn: Connection) -> Sequence[NumberingPattern]:
    """The registry patterns that allocate, as numbering-service patterns (``registry:<code>``)."""
    found: list[NumberingPattern] = []
    for item in patterns(conn):
        if not item.allocate:
            continue
        type_code = re.sub(r"[^A-Za-z0-9]", "", item.record_type.split(".")[-1]).upper() or "REC"
        found.append(
            NumberingPattern(
                id=f"{ID_PREFIX}{item.code}",
                record_type=item.record_type,
                template=item.template,
                type_code=type_code,
                scope=item.scope,
                gap_free=item.gap_free,
                reserved=item.reserved,
            )
        )
    return found
