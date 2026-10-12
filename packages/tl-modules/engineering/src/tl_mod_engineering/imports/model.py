"""The values the tag-list import passes between its steps (brief 9 M2, bulk import).

``mapping.read_rows`` turns a file into ``ImportRow`` values; ``diff.plan_import`` compares them
with the tags the project already has (``ExistingTag``) and returns an ``ImportPlan``: what would
be created, changed or left out, and which rows cannot be imported. Nothing here touches the
ledger; applying a plan is ``tl_mod_engineering.imports.apply``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class ImportRow:
    """One data row of the file, after the mapping."""

    line: int  # row number of the file; the header is row 1, so the first data row is 2
    number: str  # the tag number as written (stripped); empty when the cell was blank
    class_code: str | None  # the mapped class code; None when the cell was blank
    service: str | None  # the service description (becomes the tag's title); None when blank
    psets: dict[str, dict[str, Any]]  # {"valve_data": {"size_in": 4.0}}; blank cells are absent
    problems: list[str] = field(default_factory=lambda: [])  # why the row cannot be used
    raw: dict[str, str] = field(default_factory=lambda: {})  # the row by column header


@dataclass(frozen=True)
class ExistingTag:
    """A tag the project already holds, as far as the import compares it."""

    id: str
    number: str
    class_code: str | None
    service: str  # the record title
    psets: dict[str, Any]  # the record's psets object
    version: int


@dataclass(frozen=True)
class FieldChange:
    field: str  # "class", "service" or "psets.<pset>.<property>"
    old: Any
    new: Any


@dataclass(frozen=True)
class RowChange:
    line: int
    number: str
    tag_id: str
    changes: list[FieldChange]


@dataclass
class ImportPlan:
    new: list[ImportRow] = field(default_factory=lambda: [])
    changed: list[RowChange] = field(default_factory=lambda: [])
    unchanged: list[str] = field(default_factory=lambda: [])  # tag numbers
    removed: list[ExistingTag] = field(default_factory=lambda: [])  # not in the file
    invalid: list[ImportRow] = field(default_factory=lambda: [])  # rows that cannot be imported

    def counts(self) -> dict[str, int]:
        """``{"new": 3, "changed": 1, "unchanged": 10, "removed": 0, "invalid": 2}``."""
        return {
            "new": len(self.new),
            "changed": len(self.changed),
            "unchanged": len(self.unchanged),
            "removed": len(self.removed),
            "invalid": len(self.invalid),
        }
