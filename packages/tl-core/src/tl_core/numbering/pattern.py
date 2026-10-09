"""Numbering patterns: parse `{project}-{type}-{seq:4}`, render keys, read them back (brief 8).

A pattern is a template made of literal text, named fields (``{project}``) and exactly one
sequence segment (``{seq:4}``, zero-padded to 4 digits; ``{seq}`` means no padding). Field values
are letters and digits only. Two non-literal segments may not touch, because a key could then not
be read back unambiguously: ``{project}{type}`` and ``{type}{seq:4}`` are refused.

STUB (P0-I3-T05): the types and signatures are final; the bodies marked
``raise NotImplementedError`` are the ticket. Remove this paragraph when done.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Literal

FIELD_VALUE = re.compile(r"[A-Za-z0-9]+")


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
        raise NotImplementedError

    def prefix(self, values: Mapping[str, str]) -> str:
        """The key without its sequence digits (``P123-REC-``): what one counter is keyed by."""
        raise NotImplementedError

    def regex(self) -> re.Pattern[str]:
        """Compiled regex for a whole key. Groups are named after the fields, plus ``seq``."""
        raise NotImplementedError

    def search_regex(self) -> re.Pattern[str]:
        """Like ``regex`` but for finding keys inside text: not glued to other letters or digits."""
        raise NotImplementedError

    def parse(self, key: str) -> ParsedKey | None:
        """The field values and sequence number of ``key``, or ``None`` if it does not fit."""
        raise NotImplementedError


def parse_pattern(template: str) -> Pattern:
    """Parse a template. Raises ``PatternError`` with a message naming the problem."""
    raise NotImplementedError
