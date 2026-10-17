# ruff: noqa: F401, F841
# pyright: reportUnusedImport=false, reportUnusedFunction=false, reportUnusedVariable=false
"""Read the CSV of a cost snapshot into rows (P1-I4-T02a).

A cost export is a stranger's text, so the reader is strict and bounded: the size, the number of
columns and rows, the length of a line, the characters that may appear and the shape of every
number are checked as the file is read, and a file over a bound is refused, never cut. It is a pure
function of the bytes: no file, no clock, no global state.

The header names the columns, in any order and in any case. ``code`` is required; ``description``,
``parent`` (or ``parent_code``) and ``uom`` are optional; the fifteen figures are ``hours_budget``
... ``amount_eac`` (the swapped spelling ``budget_hours`` and the words ``qty`` and ``cost`` are
accepted). A column the reader does not know is ignored and listed in ``ignored_columns``.

STUB (P1-I4-T02a): the functions with a STEPS comment are for you to write; the signatures, the
docstrings, the constants and the helpers without STEPS are final. When they are written, delete
this paragraph, the STEPS comments and the `ruff: noqa` and `pyright` lines at the top.
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
    # STEPS
    # 1. Try data.decode("utf-8-sig") (it drops a UTF-8 byte-order mark) and return the
    #    text.
    # 2. On UnicodeDecodeError try data.decode("cp1252") and return the text.
    # 3. On UnicodeDecodeError of that raise CostFileError("not_text", "the file is neither
    #    UTF-8 nor Windows-1252 text") from the error.
    raise NotImplementedError


def _lines(text: str) -> Iterator[str]:
    for line in io.StringIO(text, newline=""):
        if len(line) > MAX_LINE_CHARS:
            raise CostFileError(
                "line_too_long", "a line of the file is far longer than a row can be"
            )
        yield line


def _delimiter(text: str) -> str:
    """The delimiter that splits the first line into the most cells (a comma on a tie)."""
    # STEPS
    # 1. first = text.split("\n", 1)[0][:MAX_LINE_CHARS]: the first line, cut so that a file
    #    of one enormous line is not counted whole.
    # 2. best = ","; count = first.count(",").
    # 3. For each candidate of DELIMITERS[1:]: when first.count(candidate) is strictly
    #    larger than count, candidate becomes best and its count becomes count. A tie keeps
    #    the earlier delimiter.
    # 4. Return best.
    raise NotImplementedError


def figure(text: str) -> float:
    """A figure written as a plain decimal, with an optional sign and thousands commas."""
    # STEPS
    # 1. If _NUMBER.fullmatch(text) is None raise ValueError("not a number").
    # 2. Return float(text.replace(",", "")). _NUMBER allows at most 15 integer digits, so
    #    the result is always under MAX_FIGURE.
    raise NotImplementedError


def read_cost_csv(data: bytes) -> CostFile:
    """The rows of a cost snapshot CSV. Raises ``CostFileError`` (and nothing else) for a bad file.

    Codes: ``too_large``, ``not_text``, ``control_character``, ``line_too_long``,
    ``malformed_csv``, ``empty_file``, ``missing_code_column``, ``duplicate_column``,
    ``too_many_columns``, ``too_many_rows``, ``too_many_cells``, ``missing_code``, ``bad_number``
    and ``bad_row``.
    """
    # STEPS
    # 1. If len(data) > MAX_IMPORT_BYTES raise CostFileError("too_large", f"the file is
    #    larger than {MAX_IMPORT_BYTES} bytes"). Then text = decode(data).
    # 2. If _FORBIDDEN.search(text) is not None raise CostFileError("control_character",
    #    "the file holds a control character"). If not text.strip() raise
    #    CostFileError("empty_file", "the file is empty").
    # 3. reader = csv.reader(_lines(text), delimiter=_delimiter(text), strict=True). header
    #    = next(reader) inside try; a csv.Error is CostFileError("malformed_csv", "the
    #    header is not valid CSV") from the error. (A CostFileError raised by _lines passes
    #    through.)
    # 4. Drop trailing blank cells of the header (`while header and not header[-1].strip():
    #    header.pop()`): an export that ends every line with a comma. More than MAX_COLUMNS
    #    cells left: CostFileError("too_many_columns", f"the file has more than
    #    {MAX_COLUMNS} columns").
    # 5. columns = {} (canonical name to position) and ignored = []. For each (position,
    #    cell) of the header: canonical = ALIASES.get(normalise(cell)). When it is None: if
    #    cell.strip() is not empty and len(ignored) < MAX_IGNORED append cell.strip()[:64]
    #    to ignored; continue. When canonical is already in columns raise
    #    CostFileError("duplicate_column", f"the column {canonical} appears twice"). Else
    #    columns[canonical] = position.
    # 6. If "code" is not in columns raise CostFileError("missing_code_column", "the file
    #    has no code column").
    # 7. rows = []; row_number = 0. Loop `while True`: record = next(reader) inside try;
    #    StopIteration breaks; a csv.Error raises CostFileError("malformed_csv", f"the file
    #    is not valid CSV near line {reader.line_num}") from the error.
    # 8. A record whose cells are all blank (`not any(cell.strip() for cell in record)`) is
    #    skipped without being counted. Otherwise row_number += 1. When row_number >
    #    MAX_ROWS raise CostFileError("too_many_rows", f"the file has more than {MAX_ROWS}
    #    rows").
    # 9. When len(record) > MAX_COLUMNS * 2 raise CostFileError("too_many_cells", "a row has
    #    far more cells than the header", row_number). Then rows.append(_row(record,
    #    columns, row_number)).
    # 10. Return CostFile(rows=tuple(rows), ignored_columns=tuple(ignored)).
    raise NotImplementedError


def _cell(record: list[str], columns: dict[str, int], name: str) -> str | None:
    position = columns.get(name)
    if position is None or position >= len(record):
        return None
    return record[position].strip() or None


def _row(record: list[str], columns: dict[str, int], row_number: int) -> CostRow:
    # STEPS
    # 1. code = _cell(record, columns, "code"). When it is None raise
    #    CostFileError("missing_code", f"row {row_number} has no cost code", row_number).
    # 2. figures = {}. For each name of MEASURE_COLUMNS: text = _cell(record, columns,
    #    name); a None text is skipped; otherwise figures[name] = figure(text). A ValueError
    #    from figure is CostFileError("bad_number", f"row {row_number}: {name} is not a
    #    plain number", row_number) raised `from None` (the cell text never goes into a
    #    message).
    # 3. Return CostRow(code=code, description=_cell(..., "description"),
    #    parent_code=_cell(..., "parent_code"), uom=_cell(..., "uom"), figures=figures).
    # 4. A pydantic ValidationError from CostRow becomes CostFileError("bad_row", f"row
    #    {row_number}: {fields} is not usable", row_number) `from None`, where fields = ',
    #    '.join(sorted({'.'.join(str(p) for p in e['loc']) for e in exc.errors()})). Only
    #    the field names go into the message, never the values.
    raise NotImplementedError
