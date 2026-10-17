"""Read a CSV file into a ``RawGrid`` (P1-I3B-T09a).

Safe against hostile input in the ways that matter for text: the encoding is checked, no line is
longer than any legitimate record can be, a cell over the csv module's field limit is a refusal,
a quote that is never closed is a refusal (``strict=True``, L-P1-I1-2), and the number of cells and
characters is counted as the file is read (``CellBudget``).
"""

from __future__ import annotations

import csv
import io
from collections.abc import Iterator
from itertools import islice

from tl_core.derivation import MAX_CELL_CHARS, MAX_COLUMNS, MAX_ROWS, Cell

from tl_extract.options import TableOptions
from tl_extract.reading import CellBudget, GridMeta, RawGrid, Refusal

#: The longest line of a legitimate record: every column at the cell limit, plus delimiters.
MAX_LINE_CHARS = (MAX_COLUMNS + 1) * (MAX_CELL_CHARS + 1)

DELIMITER_CANDIDATES = (",", ";", "\t", "|")
DELIMITER_NAMES = {",": "comma", ";": "semicolon", "\t": "tab", "|": "bar"}

NOT_UTF8 = "the file is not text in UTF-8 (or UTF-16 with a byte-order mark); save it as CSV UTF-8"
DELIMITER_NOTE = "delimiter detected: {name}"


def decode_text(raw: bytes) -> str:
    """The text of the file. A UTF-8 byte-order mark is dropped; UTF-16 is read when its byte-order
    mark says so (a spreadsheet's "Unicode text" export); anything else must be valid UTF-8.

    Raises ``Refusal("not_utf8", ...)``.
    """
    try:
        if raw.startswith((b"\xff\xfe", b"\xfe\xff")):
            return raw.decode("utf-16")
        return raw.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise Refusal("not_utf8", NOT_UTF8) from exc


def _lines(text: str) -> Iterator[str]:
    for line in io.StringIO(text, newline=""):
        if len(line) > MAX_LINE_CHARS:
            raise Refusal(
                "record_too_long",
                "a line of the file is far longer than a row can be",
            )
        yield line


def _records(text: str, delimiter: str) -> Iterator[list[str]]:
    reader = csv.reader(_lines(text), delimiter=delimiter, strict=True)
    while True:
        try:
            record = next(reader)
        except StopIteration:
            return
        except csv.Error as exc:
            if "field larger than field limit" in str(exc):
                raise Refusal(
                    "cell_too_long",
                    f"a cell near line {reader.line_num} is longer than a cell can be",
                ) from exc
            raise Refusal(
                "malformed_csv",
                f"the file is not valid CSV near line {reader.line_num}",
            ) from exc
        yield record


def detect_delimiter(text: str, header_row: int) -> str:
    """The candidate delimiter that splits the header record into the most cells; a comma when
    none splits it. Ties go to the earlier candidate (comma, semicolon, tab, bar)."""
    best = ","
    best_count = 1
    for candidate in DELIMITER_CANDIDATES:
        try:
            record = next(islice(_records(text, candidate), header_row - 1, None), [])
        except Refusal:
            continue
        if len(record) > best_count:
            best = candidate
            best_count = len(record)
    return best


def _cell(text: str) -> Cell:
    return text if text else None


def read_csv(raw: bytes, options: TableOptions) -> RawGrid:
    """The records of ``raw`` as a ``RawGrid`` (see its docstring for what the rows hold).

    Raises ``Refusal`` with the code ``not_utf8``, ``record_too_long``, ``cell_too_long``,
    ``malformed_csv``, ``too_many_rows``, ``too_many_cells`` or ``too_much_text``.
    """
    text = decode_text(raw)
    delimiter = options.delimiter or detect_delimiter(text, options.header_row)
    notes: list[str] = []
    if options.delimiter is None and delimiter != ",":
        notes.append(DELIMITER_NOTE.format(name=DELIMITER_NAMES[delimiter]))
    budget = CellBudget()
    rows: list[list[Cell]] = []
    skipped = 0
    kept = 0
    for index, record in enumerate(_records(text, delimiter), start=1):
        cells = [_cell(value) for value in record]
        while cells and not (cells[-1] or "").strip():
            cells.pop()
        del cells[MAX_COLUMNS + 1 :]
        budget.take(cells)
        if index <= options.header_row:
            rows.append(cells)
            continue
        if not cells:
            skipped += 1
            continue
        kept += 1
        if kept > MAX_ROWS:
            raise Refusal(
                "too_many_rows",
                f"the file has more than {MAX_ROWS} data rows; split the file",
            )
        rows.append(cells)
    return RawGrid(rows=rows, skipped_blank_rows=skipped, notes=notes, meta=GridMeta())
