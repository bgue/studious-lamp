"""Numbering patterns: parse `{project}-{type}-{seq:4}`, render keys, read them back (brief 8).

A pattern is a template made of literal text, named fields (``{project}``) and exactly one
sequence segment (``{seq:4}``, zero-padded to 4 digits; ``{seq}`` means no padding). Field values
are letters and digits only. A sequence longer than the declared width is written in full
(``{seq:4}`` renders 10000 as ``10000``); such keys sort lexically before ``9999``, so sort by
the parsed sequence, or choose a width that will not overflow. Two non-literal segments may not
touch, because a key could then not be read back unambiguously: ``{project}{type}`` and
``{type}{seq:4}`` are refused.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Literal

FIELD_VALUE = re.compile(r"[A-Za-z0-9]+")
_TOKEN = re.compile(r"\{([^{}]*)\}")
_FIELD_NAME = re.compile(r"[a-z][a-z0-9_]*")
_SEQ_TOKEN = re.compile(r"seq(?::([1-9]))?")


class PatternError(ValueError):
    """A template is malformed, or a value does not fit a pattern."""


@dataclass(frozen=True)
class Segment:
    kind: Literal["literal", "field", "seq"]
    text: str = ""  # literal text, or the field name; empty for seq
    width: int = 0  # seq only: zero-padding width (0 means none)


@dataclass(frozen=True)
class ParsedKey:
    fields: dict[str, str]
    sequence: int


@dataclass(frozen=True)
class Pattern:
    template: str
    segments: tuple[Segment, ...]

    @property
    def fields(self) -> tuple[str, ...]:
        """Field names in template order (the sequence segment is not a field)."""
        return tuple(s.text for s in self.segments if s.kind == "field")

    @property
    def seq_width(self) -> int:
        return next(s.width for s in self.segments if s.kind == "seq")

    def render(self, values: Mapping[str, str], sequence: int) -> str:
        """The key for ``values`` and ``sequence``.

        A sequence longer than the width is written in full (``{seq:2}`` renders 123 as ``123``).
        Raises ``PatternError`` for a missing field, a value that is not letters and digits, or a
        sequence below 1. Extra entries in ``values`` are ignored.
        """
        if sequence < 1:
            raise PatternError(f"sequence must be at least 1, got {sequence}")
        return self._build(values, f"{sequence:0{self.seq_width}d}")

    def prefix(self, values: Mapping[str, str]) -> str:
        """The key without its sequence digits (``P123-REC-``): what one counter is keyed by."""
        return self._build(values, "")

    def regex(self) -> re.Pattern[str]:
        """Compiled regex for a whole key. Groups are named after the fields, plus ``seq``."""
        return re.compile(self._regex_source())

    def search_regex(self) -> re.Pattern[str]:
        """Like ``regex`` but for finding keys inside text: not glued to other letters or digits."""
        return re.compile(rf"(?<![A-Za-z0-9_-]){self._regex_source()}(?![A-Za-z0-9_])")

    def parse(self, key: str) -> ParsedKey | None:
        """The field values and sequence number of ``key``, or ``None`` if it does not fit.

        Strict: the sequence must be spelled exactly as ``render`` writes it, so zero-padding
        matches the declared width and a sequence longer than the width has no leading zero.
        """
        match = self.regex().fullmatch(key)
        if match is None:
            return None
        sequence = int(match.group("seq"))
        if sequence < 1 or match.group("seq") != f"{sequence:0{self.seq_width}d}":
            return None  # only the canonical spelling: P1-REC-00012 is not P1-REC-0012
        return ParsedKey(
            fields={name: match.group(name) for name in self.fields}, sequence=sequence
        )

    def _build(self, values: Mapping[str, str], seq_text: str) -> str:
        parts: list[str] = []
        for segment in self.segments:
            if segment.kind == "literal":
                parts.append(segment.text)
            elif segment.kind == "seq":
                parts.append(seq_text)
            else:
                value = values.get(segment.text)
                if value is None:
                    raise PatternError(f"no value for field {segment.text!r}")
                if FIELD_VALUE.fullmatch(value) is None:
                    raise PatternError(
                        f"value {value!r} for field {segment.text!r} must be letters and digits"
                    )
                parts.append(value)
        return "".join(parts)

    def _regex_source(self) -> str:
        parts: list[str] = []
        for segment in self.segments:
            if segment.kind == "literal":
                parts.append(re.escape(segment.text))
            elif segment.kind == "seq":
                parts.append(rf"(?P<seq>\d{{{max(segment.width, 1)},}})")
            else:
                parts.append(rf"(?P<{segment.text}>[A-Za-z0-9]+)")
        return "".join(parts)


def parse_pattern(template: str) -> Pattern:
    """Parse a template. Raises ``PatternError`` with a message naming the problem."""
    if not template:
        raise PatternError("pattern is empty")
    segments: list[Segment] = []
    position = 0
    for token in _TOKEN.finditer(template):
        _add_literal(segments, template[position : token.start()])
        segments.append(_segment_for(token.group(1)))
        position = token.end()
    _add_literal(segments, template[position:])

    seq_count = sum(1 for s in segments if s.kind == "seq")
    if seq_count != 1:
        raise PatternError(f"pattern needs exactly one {{seq:N}} segment, found {seq_count}")
    names = [s.text for s in segments if s.kind == "field"]
    if len(names) != len(set(names)):
        raise PatternError("a field name may appear only once")
    for left, right in zip(segments, segments[1:], strict=False):
        if left.kind != "literal" and right.kind != "literal":
            raise PatternError("separate fields and the sequence with literal text")
    return Pattern(template=template, segments=tuple(segments))


def _add_literal(segments: list[Segment], text: str) -> None:
    if not text:
        return
    if "{" in text or "}" in text:
        raise PatternError(f"unbalanced brace in literal text {text!r}")
    segments.append(Segment("literal", text))


def _segment_for(body: str) -> Segment:
    seq = _SEQ_TOKEN.fullmatch(body)
    if seq is not None:
        return Segment("seq", "", int(seq.group(1) or 0))
    if _FIELD_NAME.fullmatch(body) is None:
        raise PatternError(f"invalid segment {{{body}}}")
    return Segment("field", body)
