"""Read the CSV of a cost snapshot into rows (P1-I4-T02a).

A cost export is a stranger's text, so the reader is strict and bounded: the size, the number of
columns and rows, the length of a line, the characters that may appear and the shape of every
number are checked as the file is read, and a file over a bound is refused, never cut. It is a pure
function of the bytes: no file, no clock, no global state.

The header names the columns, in any order and in any case. ``code`` is required; ``description``,
``parent`` (or ``parent_code``) and ``uom`` are optional; the fifteen figures are ``hours_budget``
... ``amount_eac`` (the swapped spelling ``budget_hours`` and the words ``qty`` and ``cost`` are
accepted). A column the reader does not know is ignored and listed in ``ignored_columns``.
"""

from __future__ import annotations

import csv
import io
import re
from collections.abc import Iterator

from pydantic import ValidationError

from tl_mod_cost.errors import CostFileError
from tl_mod_cost.imports.model import CostFile, CostRow
from tl_mod_cost.limits import MAX_IMPORT_BYTES, MAX_ROWS
from tl_mod_cost.names import MEASURE_COLUMNS, MEASURES

MAX_COLUMNS = 60
MAX_LINE_CHARS = 20_000
MAX_IGNORED = 50
DELIMITERS = (",", ";", "\t")
#: Control characters (other than tab, CR and LF), line and paragraph separators and text-direction
#: marks have no place in a cost export.
_FORBIDDEN = re.compile("[\x00-\x08\x0b\x0c\x0e-\x1f\x7f-\x9f؜‎‏  ‪-‮⁦-⁩﻿]")
_NUMBER = re.compile(r"-?(?:[0-9]{1,15}|[0-9]{1,3}(?:,[0-9]{3}){1,4})(?:\.[0-9]{1,6})?")
_UNIT_WORDS = {"hours": "hours", "hrs": "hours", "quantity": "quantity", "qty": "quantity",
               "amount": "amount", "cost": "amount"}  # fmt: skip
_TEXT_COLUMNS = {
    "code": ("code", "cost_code", "costcode"),
    "description": ("description", "desc", "name", "title"),
    "parent_code": ("parent", "parent_code", "parentcode"),
    "uom": ("uom", "unit", "unit_of_measure"),
}


def _aliases() -> dict[str, str]:
    """Normalised header text to the canonical column name."""
    found: dict[str, str] = {}
    for canonical, names in _TEXT_COLUMNS.items():
        for name in names:
            found[name] = canonical
    for word, unit in _UNIT_WORDS.items():
        for measure in MEASURES:
            found[f"{word}_{measure}"] = f"{unit}_{measure}"
            found[f"{measure}_{word}"] = f"{unit}_{measure}"
    return found


ALIASES = _aliases()


def normalise(header: str) -> str:
    """A header cell as the alias table spells it: lower case, words joined by an underscore."""
    return re.sub(r"[\s\-]+", "_", header.strip().lower())


def decode(data: bytes) -> str:
    """The text of the file: UTF-8 (a byte-order mark is dropped), else Windows-1252.

    Raises ``CostFileError("not_text")`` for a byte neither encoding allows.
    """
    try:
        return data.decode("utf-8-sig")
    except UnicodeDecodeError:
        pass
    try:
        return data.decode("cp1252")
    except UnicodeDecodeError as error:
        raise CostFileError(
            "not_text", "the file is neither UTF-8 nor Windows-1252 text"
        ) from error


def _lines(text: str) -> Iterator[str]:
    for line in io.StringIO(text, newline=""):
        if len(line) > MAX_LINE_CHARS:
            raise CostFileError(
                "line_too_long", "a line of the file is far longer than a row can be"
            )
        yield line


def _delimiter(text: str) -> str:
    """The delimiter that splits the first line into the most cells (a comma on a tie)."""
    first = text.split("\n", 1)[0][:MAX_LINE_CHARS]
    best = ","
    count = first.count(",")
    for candidate in DELIMITERS[1:]:
        if first.count(candidate) > count:
            best = candidate
            count = first.count(candidate)
    return best


def figure(text: str) -> float:
    """A figure written as a plain decimal, with an optional sign and thousands commas."""
    if _NUMBER.fullmatch(text) is None:
        raise ValueError("not a number")
    return float(text.replace(",", ""))


def read_cost_csv(data: bytes) -> CostFile:
    """The rows of a cost snapshot CSV. Raises ``CostFileError`` (and nothing else) for a bad file.

    Codes: ``too_large``, ``not_text``, ``control_character``, ``line_too_long``,
    ``malformed_csv``, ``empty_file``, ``missing_code_column``, ``duplicate_column``,
    ``too_many_columns``, ``too_many_rows``, ``too_many_cells``, ``missing_code``, ``bad_number``
    and ``bad_row``.
    """
    if len(data) > MAX_IMPORT_BYTES:
        raise CostFileError("too_large", f"the file is larger than {MAX_IMPORT_BYTES} bytes")
    text = decode(data)
    if _FORBIDDEN.search(text) is not None:
        raise CostFileError("control_character", "the file holds a control character")
    if not text.strip():
        raise CostFileError("empty_file", "the file is empty")
    reader = csv.reader(_lines(text), delimiter=_delimiter(text), strict=True)
    try:
        header = next(reader)
    except csv.Error as error:
        raise CostFileError("malformed_csv", "the header is not valid CSV") from error
    while header and not header[-1].strip():
        header.pop()
    if len(header) > MAX_COLUMNS:
        raise CostFileError("too_many_columns", f"the file has more than {MAX_COLUMNS} columns")
    columns: dict[str, int] = {}
    ignored: list[str] = []
    for position, cell in enumerate(header):
        canonical = ALIASES.get(normalise(cell))
        if canonical is None:
            if cell.strip() and len(ignored) < MAX_IGNORED:
                ignored.append(cell.strip()[:64])
            continue
        if canonical in columns:
            raise CostFileError("duplicate_column", f"the column {canonical} appears twice")
        columns[canonical] = position
    if "code" not in columns:
        raise CostFileError("missing_code_column", "the file has no code column")
    rows: list[CostRow] = []
    row_number = 0
    while True:
        try:
            record = next(reader)
        except StopIteration:
            break
        except csv.Error as error:
            raise CostFileError(
                "malformed_csv", f"the file is not valid CSV near line {reader.line_num}"
            ) from error
        if not any(cell.strip() for cell in record):
            continue
        row_number += 1
        if row_number > MAX_ROWS:
            raise CostFileError("too_many_rows", f"the file has more than {MAX_ROWS} rows")
        if len(record) > MAX_COLUMNS * 2:
            raise CostFileError(
                "too_many_cells", "a row has far more cells than the header", row_number
            )
        rows.append(_row(record, columns, row_number))
    return CostFile(rows=tuple(rows), ignored_columns=tuple(ignored))


def _cell(record: list[str], columns: dict[str, int], name: str) -> str | None:
    position = columns.get(name)
    if position is None or position >= len(record):
        return None
    return record[position].strip() or None


def _row(record: list[str], columns: dict[str, int], row_number: int) -> CostRow:
    code = _cell(record, columns, "code")
    if code is None:
        raise CostFileError("missing_code", f"row {row_number} has no cost code", row_number)
    figures: dict[str, float] = {}
    for name in MEASURE_COLUMNS:
        text = _cell(record, columns, name)
        if text is None:
            continue
        try:
            figures[name] = figure(text)
        except ValueError:
            raise CostFileError(
                "bad_number", f"row {row_number}: {name} is not a plain number", row_number
            ) from None
    try:
        return CostRow(
            code=code,
            description=_cell(record, columns, "description"),
            parent_code=_cell(record, columns, "parent_code"),
            uom=_cell(record, columns, "uom"),
            figures=figures,
        )
    except ValidationError as exc:
        fields = ", ".join(sorted({".".join(str(p) for p in e["loc"]) for e in exc.errors()}))
        raise CostFileError(
            "bad_row", f"row {row_number}: {fields} is not usable", row_number
        ) from None
