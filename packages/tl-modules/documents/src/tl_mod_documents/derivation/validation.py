"""Checking extracted rows against a document schema, with a row- and field-level report.

A ``DocumentSchema`` holds a JSON Schema (draft 2020-12) for one row: an object whose properties
are the columns. Extractors give cells as text (``tl_core.derivation.types``), so this module first
reads each cell with the type its property declares and then lets JSON Schema judge the row.

Reading a cell (``read_cell``): the cell is trimmed; an empty cell is absent (the property is not
set, so ``required`` fails and nothing else does). The declared type decides the reading:

* ``string`` (and no type): the text as it is; ``format`` and ``pattern`` are JSON Schema's.
* ``integer``: optional sign and digits only (``12``, ``-3``); ``1.0`` and ``1,000`` are refused.
* ``number``: a decimal number (``4``, ``4.5``, ``-0.25``, ``1e3``); not NaN or infinity.
* ``boolean``: ``yes/no``, ``true/false``, ``y/n``, ``t/f``, ``1/0`` in any case.
* a list of types (``["integer", "null"]``): the first type that is not ``null``.
* ``array`` and ``object`` cannot be read from a cell: one file-level error for the property.

A cell that cannot be read is an error of that row and field (``not_an_integer`` ...) and the field
is left out of the JSON Schema check, so one bad cell is one issue. The report counts every issue
exactly and lists the first ``MAX_ISSUES``.

File-level checks: a required property with no column (``missing_column``), a column the schema
does not know (``unknown_column``, a warning; the column is not checked), no rows at all
(``no_rows``), a repeated value in the key column (``duplicate_key``, on the later row), and every
problem the extractor reported while reading (as an error with its own code).
"""

from __future__ import annotations

import math
import re
from collections.abc import Iterable, Mapping, Sequence
from decimal import Decimal, InvalidOperation
from typing import Any, Literal

from jsonschema import Draft202012Validator, FormatChecker
from pydantic import BaseModel
from tl_core.derivation.types import Cell, ExtractionProblem

#: The report lists at most this many issues; the counts are always exact.
MAX_ISSUES = 1000
#: A cell value shown in an issue, and a message, are cut to these lengths.
MAX_SHOWN_VALUE = 80
MAX_MESSAGE = 300

Level = Literal["error", "warning"]
_INTEGER = re.compile(r"[+-]?[0-9]+")
_TRUE = frozenset({"yes", "y", "true", "t", "1"})
_FALSE = frozenset({"no", "n", "false", "f", "0"})
_FORMATS = FormatChecker()


class Issue(BaseModel):
    """One problem. ``row`` is the 1-based data row (header excluded); ``None`` for the file."""

    level: Level
    code: str
    message: str
    row: int | None = None
    column: str | None = None
    #: The offending cell, cut to ``MAX_SHOWN_VALUE`` characters.
    value: str | None = None


class ValidationReport(BaseModel):
    schema_code: str
    schema_version: str
    status: Literal["valid", "invalid"]
    rows_checked: int
    rows_with_errors: int
    error_count: int
    warning_count: int
    #: The first ``MAX_ISSUES`` issues in the order found (file-level first, then by row).
    issues: list[Issue]
    truncated: bool


def _short(text: str, limit: int) -> str:
    return text if len(text) <= limit else text[: limit - 1] + "…"


def _declared_type(prop: Mapping[str, Any]) -> str | None:
    declared = prop.get("type")
    if isinstance(declared, list):
        names = [t for t in declared if isinstance(t, str) and t != "null"]  # pyright: ignore[reportUnknownVariableType]
        return names[0] if names else None
    return declared if isinstance(declared, str) else None


def read_cell(prop: Mapping[str, Any], cell: Cell) -> tuple[Any, str | None, str | None]:
    """``(value, code, message)`` for one cell read as the property declares.

    An empty cell is ``(None, None, None)``: absent. A cell that cannot be read is
    ``(None, code, message)``; otherwise ``(value, None, None)``.
    """
    if cell is None or cell.strip() == "":
        return None, None, None
    text = cell.strip()
    kind = _declared_type(prop)
    if kind in (None, "string", "null"):
        return text, None, None
    if kind == "integer":
        if _INTEGER.fullmatch(text) is None:
            return None, "not_an_integer", "is not a whole number"
        return int(text), None, None
    if kind == "number":
        try:
            value = Decimal(text)
        except InvalidOperation:
            return None, "not_a_number", "is not a number"
        if not value.is_finite():
            return None, "not_a_number", "is not a finite number"
        number = float(value)
        if math.isinf(number):
            return None, "not_a_number", "is too large for a number"
        return number, None, None
    if kind == "boolean":
        lowered = text.lower()
        if lowered in _TRUE:
            return True, None, None
        if lowered in _FALSE:
            return False, None, None
        return None, "not_a_boolean", "is not yes or no"
    return None, "unsupported_type", f"a {kind} cannot be read from a cell"


class _Counter:
    """Collects issues, keeping exact counts and the first ``MAX_ISSUES``."""

    def __init__(self) -> None:
        self.issues: list[Issue] = []
        self.errors = 0
        self.warnings = 0
        self.rows_with_errors: set[int] = set()

    def add(self, issue: Issue) -> None:
        if issue.level == "error":
            self.errors += 1
            if issue.row is not None:
                self.rows_with_errors.add(issue.row)
        else:
            self.warnings += 1
        if len(self.issues) < MAX_ISSUES:
            self.issues.append(issue)


def _error_issues(row: int, obj: dict[str, Any], error: Any) -> Iterable[Issue]:
    code = str(error.validator)
    if code == "required":
        # jsonschema reports one error per missing property, each holding the whole list
        for name in error.validator_value:
            if name not in obj and str(error.message).startswith(f"{name!r} "):
                yield Issue(
                    level="error",
                    code="required",
                    message="a value is required",
                    row=row,
                    column=name,
                )
        return
    path = list(error.absolute_path)
    column = str(path[0]) if path else None
    shown = obj.get(column) if column is not None else None
    yield Issue(
        level="error",
        code=code,
        message=_short(str(error.message), MAX_MESSAGE),
        row=row,
        column=column,
        value=None if shown is None else _short(str(shown), MAX_SHOWN_VALUE),
    )


def validate_result(
    json_schema: Mapping[str, Any],
    columns: Sequence[str],
    rows: Sequence[Mapping[str, Cell]],
    *,
    schema_code: str,
    schema_version: str,
    key_column: str | None = None,
    problems: Sequence[ExtractionProblem] = (),
) -> ValidationReport:
    """Validate ``rows`` (cells as text) against ``json_schema`` and report row by row."""
    properties: dict[str, Mapping[str, Any]] = {
        name: prop
        for name, prop in dict(json_schema.get("properties", {})).items()
        if isinstance(prop, Mapping)
    }
    required = [str(n) for n in json_schema.get("required", [])]
    counter = _Counter()

    for problem in problems:
        counter.add(
            Issue(
                level="error",
                code=problem.code,
                message=_short(problem.message, MAX_MESSAGE),
                row=problem.row,
            )
        )
    for name in required:
        if name not in columns:
            counter.add(
                Issue(
                    level="error",
                    code="missing_column",
                    message="the file has no such column",
                    column=name,
                )
            )
    for name, prop in properties.items():
        if name in columns and _declared_type(prop) in ("array", "object"):
            counter.add(
                Issue(
                    level="error",
                    code="unsupported_type",
                    message=f"a {_declared_type(prop)} cannot be read from a cell",
                    column=name,
                )
            )
    for name in columns:
        if name not in properties:
            counter.add(
                Issue(
                    level="warning",
                    code="unknown_column",
                    message="the schema does not describe this column; it is not checked",
                    column=name,
                )
            )
    if not rows:
        counter.add(Issue(level="error", code="no_rows", message="the file has no data rows"))

    validator = Draft202012Validator(dict(json_schema), format_checker=_FORMATS)
    first_row_of_key: dict[str, int] = {}
    for number, row in enumerate(rows, start=1):
        obj: dict[str, Any] = {}
        unreadable: set[str] = set()
        for name, prop in properties.items():
            if name not in row or _declared_type(prop) in ("array", "object"):
                continue
            value, code, message = read_cell(prop, row[name])
            if code is not None:
                unreadable.add(name)
                counter.add(
                    Issue(
                        level="error",
                        code=code,
                        message=message or code,
                        row=number,
                        column=name,
                        value=_short(str(row[name]).strip(), MAX_SHOWN_VALUE),
                    )
                )
            elif value is not None:
                obj[name] = value
        for error in sorted(validator.iter_errors(obj), key=lambda e: list(map(str, e.path))):
            for issue in _error_issues(number, obj, error):
                if issue.column in unreadable and issue.code == "required":
                    continue  # the cell was there and unreadable: that is the one issue
                counter.add(issue)
        if key_column is not None and key_column in row:
            key = (row[key_column] or "").strip()
            if key:
                if key in first_row_of_key:
                    counter.add(
                        Issue(
                            level="error",
                            code="duplicate_key",
                            message=f"repeats row {first_row_of_key[key]}",
                            row=number,
                            column=key_column,
                            value=_short(key, MAX_SHOWN_VALUE),
                        )
                    )
                else:
                    first_row_of_key[key] = number
    return ValidationReport(
        schema_code=schema_code,
        schema_version=schema_version,
        status="valid" if counter.errors == 0 else "invalid",
        rows_checked=len(rows),
        rows_with_errors=len(counter.rows_with_errors),
        error_count=counter.errors,
        warning_count=counter.warnings,
        issues=counter.issues,
        truncated=counter.errors + counter.warnings > len(counter.issues),
    )
