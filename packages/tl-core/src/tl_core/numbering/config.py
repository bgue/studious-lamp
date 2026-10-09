"""Numbering pattern configuration: which pattern numbers which record type in which scope.

A ``NumberingPattern`` binds a template (``{project}-{type}-{seq:4}``, see ``pattern.py``) to a
record type and a scope selector, and says how it is allocated:

* ``gap_free`` (default true): a number is only ever allocated inside the transaction that creates
  the record it names, so a failed create leaves no hole and no number is spent without a record.
  Standalone allocation is refused. A pattern with ``gap_free: false`` may also be allocated
  without a record (bulk or offline use, brief 8), which can leave gaps.
* ``reserved``: inclusive ranges of sequence numbers the allocator skips, set aside for offline or
  bulk use. This is the stub of "reserved ranges" (brief 8); nothing hands the ranges out yet.

Patterns come from ``<schema dir>/numbering/patterns.yaml`` (``TL_SCHEMA_DIR`` or
``schema/fixtures``). Until numbering becomes a ledgered project setting (about:config, P0-I8) the
file is the configuration.
"""

from __future__ import annotations

import re
from collections.abc import Generator, Iterable
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Self, cast

import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator, model_validator
from tl_schema.registry import default_schema_dir

from tl_core.numbering.pattern import FIELD_VALUE, Pattern, PatternError, parse_pattern

_SCOPE_SELECTOR = re.compile(r"\*|project:\*|company|project:[A-Za-z0-9_.-]+")


class NumberingConfigError(ValueError):
    """A numbering file or pattern set that cannot be used. The message names the source."""


class NumberingPattern(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    id: str = Field(min_length=1)
    record_type: str = Field(min_length=1)
    template: str
    type_code: str  # the value of the {type} segment, letters and digits
    scope: str = "*"  # "*" any scope, "project:*" any project, or one exact scope
    gap_free: bool = True
    reserved: list[tuple[int, int]] = []

    @field_validator("template")
    @classmethod
    def _template_parses(cls, value: str) -> str:
        try:
            parse_pattern(value)
        except PatternError as exc:
            raise ValueError(str(exc)) from exc
        return value

    @field_validator("type_code")
    @classmethod
    def _type_code_is_a_field_value(cls, value: str) -> str:
        if FIELD_VALUE.fullmatch(value) is None:
            raise ValueError("type_code must be letters and digits")
        return value

    @field_validator("scope")
    @classmethod
    def _scope_selector(cls, value: str) -> str:
        if _SCOPE_SELECTOR.fullmatch(value) is None:
            raise ValueError("scope must be '*', 'project:*', 'company' or 'project:<id>'")
        return value

    @model_validator(mode="after")
    def _ranges_are_sound(self) -> Self:
        for start, end in self.reserved:
            if start < 1 or end < start:
                raise ValueError(f"reserved range [{start}, {end}] must satisfy 1 <= start <= end")
        return self

    def compiled(self) -> Pattern:
        """The parsed template."""
        return parse_pattern(self.template)

    def matches_scope(self, scope: str) -> int:
        """0 when the pattern does not apply to ``scope``; else how specific it is (1 to 3)."""
        if self.scope == scope:
            return 3
        if self.scope == "project:*" and scope.startswith("project:"):
            return 2
        if self.scope == "*":
            return 1
        return 0

    def skip_reserved(self, sequence: int) -> int:
        """The first sequence number at or after ``sequence`` that lies in no reserved range."""
        moved = True
        while moved:
            moved = False
            for start, end in self.reserved:
                if start <= sequence <= end:
                    sequence = end + 1
                    moved = True
        return sequence


class NumberingRegistry:
    """Patterns in registration order; ids are unique."""

    def __init__(self, patterns: Iterable[NumberingPattern] = ()) -> None:
        self._patterns: list[NumberingPattern] = []
        for pattern in patterns:
            self.add(pattern)

    def add(self, pattern: NumberingPattern) -> None:
        if any(p.id == pattern.id for p in self._patterns):
            raise NumberingConfigError(f"numbering pattern {pattern.id!r} is already registered")
        self._patterns.append(pattern)

    def all(self) -> list[NumberingPattern]:
        return list(self._patterns)

    def get(self, pattern_id: str) -> NumberingPattern | None:
        return next((p for p in self._patterns if p.id == pattern_id), None)

    def find(self, scope: str, record_type: str) -> NumberingPattern | None:
        """The most specific pattern for this scope and record type (first registered on a tie)."""
        best: NumberingPattern | None = None
        best_rank = 0
        for pattern in self._patterns:
            if pattern.record_type != record_type:
                continue
            rank = pattern.matches_scope(scope)
            if rank > best_rank:
                best, best_rank = pattern, rank
        return best

    def for_scope(self, scope: str) -> list[NumberingPattern]:
        """Every pattern that applies to ``scope`` (used to recognise keys in text)."""
        return [p for p in self._patterns if p.matches_scope(scope) > 0]


def parse_numbering(text: str, *, source: str = "<string>") -> NumberingRegistry:
    """Parse a ``patterns:`` YAML document. Raises ``NumberingConfigError`` naming ``source``."""
    try:
        data: Any = yaml.safe_load(text)
    except yaml.YAMLError as exc:
        raise NumberingConfigError(f"{source}: invalid YAML: {exc}") from exc
    mapping: dict[str, Any] = cast(dict[str, Any], data) if isinstance(data, dict) else {}
    entries: Any = mapping.get("patterns")
    if set(mapping) != {"patterns"} or not isinstance(entries, list):
        raise NumberingConfigError(
            f"{source}: expected a mapping with one key, 'patterns' (a list)"
        )
    registry = NumberingRegistry()
    for index, entry in enumerate(cast(list[Any], entries)):
        try:
            registry.add(NumberingPattern.model_validate(entry))
        except ValidationError as exc:
            lines = [
                f"{source}: patterns[{index}].{'.'.join(str(p) for p in e['loc'])}: {e['msg']}"
                for e in exc.errors()
            ]
            raise NumberingConfigError("\n".join(lines)) from exc
        except NumberingConfigError as exc:
            raise NumberingConfigError(f"{source}: {exc}") from exc
    return registry


def load_numbering(path: Path) -> NumberingRegistry:
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        raise NumberingConfigError(f"{path.name}: cannot read file: {exc}") from exc
    return parse_numbering(text, source=path.name)


_override: NumberingRegistry | None = None


def get_numbering() -> NumberingRegistry:
    """The patterns in force: the installed override, else ``<schema dir>/numbering/patterns.yaml``.

    A missing file gives an empty registry, so creating a record without a key then fails with
    ``NoNumberingPatternError``.
    """
    if _override is not None:
        return _override
    path = default_schema_dir() / "numbering" / "patterns.yaml"
    return load_numbering(path) if path.is_file() else NumberingRegistry()


@contextmanager
def use_numbering(registry: NumberingRegistry) -> Generator[None]:
    """Install ``registry`` for the duration of the block (tests and embedders)."""
    global _override
    previous, _override = _override, registry
    try:
        yield
    finally:
        _override = previous
