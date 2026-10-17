"""The report of reading an XER file: problems with a code, a place and a fixed message (P1-I4-T04).

Messages are fixed text. The only values that appear in them are ones the reader already vetted:
table and column names (a name pattern), project short names that passed ``clean_text``, activity
ids that passed the id check, and counts. A report keeps at most ``MAX_PROBLEMS`` problems and says
how many there were in all, so a hostile file cannot make a megabyte of report.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from tl_xer import limits

Severity = Literal["error", "warning"]


@dataclass(frozen=True)
class Problem:
    severity: Severity
    code: str
    message: str
    table: str | None = None
    row: int | None = None  # 1-based data row of the table
    field: str | None = None

    def as_dict(self) -> dict[str, str | int | None]:
        return {
            "severity": self.severity,
            "code": self.code,
            "message": self.message,
            "table": self.table,
            "row": self.row,
            "field": self.field,
        }


class Problems:
    """A bounded list of problems and the counts of all of them."""

    def __init__(self) -> None:
        self.kept: list[Problem] = []
        self.errors = 0
        self.warnings = 0

    def add(
        self,
        severity: Severity,
        code: str,
        message: str,
        *,
        table: str | None = None,
        row: int | None = None,
        field: str | None = None,
    ) -> None:
        if severity == "error":
            self.errors += 1
        else:
            self.warnings += 1
        if len(self.kept) < limits.MAX_PROBLEMS:
            self.kept.append(
                Problem(severity, code, message[: limits.MAX_MESSAGE_CHARS], table, row, field)
            )

    def error(
        self,
        code: str,
        message: str,
        *,
        table: str | None = None,
        row: int | None = None,
        field: str | None = None,
    ) -> None:
        self.add("error", code, message, table=table, row=row, field=field)

    def warn(
        self,
        code: str,
        message: str,
        *,
        table: str | None = None,
        row: int | None = None,
        field: str | None = None,
    ) -> None:
        self.add("warning", code, message, table=table, row=row, field=field)

    @property
    def count(self) -> int:
        return self.errors + self.warnings

    @property
    def truncated(self) -> bool:
        return self.count > len(self.kept)
