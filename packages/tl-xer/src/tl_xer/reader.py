"""Read the bytes of an XER file into raw tables (P1-I4-T03).

An XER file is tab-separated text. The first line is ``ERMHDR`` and the export header; then, for
each table, ``%T<TAB>NAME``, ``%F<TAB>col<TAB>col...``, any number of ``%R<TAB>field<TAB>...`` rows,
and the file ends with ``%E``. This module only tokenises and bounds; it knows nothing about what
P6 means by a table (``validate`` and ``typed`` do).

What makes it safe to point at a stranger's file:

* **Bounded before it is parsed.** The size, the tab count of a line (before the line is split),
  the columns of a table, the rows of a table and the cells of the file, the length of a field:
  each is checked as the file streams by, and a breach is a ``XerRefusal`` with a fixed message.
  Nothing is cut to fit.
* **The encoding is decided, not guessed per line.** UTF-16 is refused. A UTF-8 byte-order mark or
  valid UTF-8 means UTF-8; plain ASCII is ASCII; anything else is Windows-1252 (the encoding P6
  writes by default), and a byte that Windows-1252 leaves undefined is a refusal. The decision is
  one pass over the bytes in chunks, so no second copy of the file is held.
* **Names are unique ignoring case.** `A` and `a` in one table, or `ZZ` and `zz` as two tables,
  are refused: the lake and SQL fold case, so they would be one column or one table there.
* **No control characters.** NUL crashes Postgres (L-P1-I2-17); the other C0 and C1 controls,
  line and paragraph separators and text-direction marks have no place in a schedule and spoof a
  screen. They refuse the file; they are not stripped.
* **Streamed.** The file is read line by line from the bytes; a line is decoded alone.
* **No clock, no randomness, no state.** The same bytes give the same tables.
"""

from __future__ import annotations

import codecs
import io
import re
from dataclasses import dataclass

from tl_xer import limits
from tl_xer.refusals import XerRefusal

ENCODINGS = ("ascii", "utf-8", "cp1252")
_NAME = re.compile(r"[A-Za-z][A-Za-z0-9_]*")
FORBIDDEN = re.compile(
    "[\x00-\x08\x0b-\x1f\x7f-\x9f\u061c\u200e\u200f\u2028\u2029\u202a-\u202e\u2066-\u2069\ufeff]"
)
_CHUNK = 1 << 20
_UTF8_BOM = b"\xef\xbb\xbf"
_UTF16_BOMS = (b"\xff\xfe", b"\xfe\xff")


@dataclass(frozen=True)
class RawTable:
    """One ``%T`` section: its columns and its rows, every row padded to the column count."""

    name: str
    columns: tuple[str, ...]
    rows: tuple[tuple[str, ...], ...]

    def index(self) -> dict[str, int]:
        return {name: i for i, name in enumerate(self.columns)}


@dataclass(frozen=True)
class RawXer:
    header: tuple[str, ...]  # the ERMHDR fields after the marker: version, export date, ...
    tables: tuple[RawTable, ...]  # in file order
    encoding: str
    cells: int
    size: int  # bytes of the file: the typed text is bounded by a multiple of it

    def table(self, name: str) -> RawTable | None:
        for table in self.tables:
            if table.name == name:
                return table
        return None


def row_memory(line: str, values: list[str], columns: int) -> int:
    """What a ``%R`` line is estimated to take once read, in bytes.

    A slot for every column, a string object for every cell that is not empty (empty cells are the
    one shared empty string), the characters of the line, and the tuple and list of the row. A
    line with a non-ASCII character is counted at the wide size throughout. It over-counts a little
    (the tabs and the marker are counted as characters) and never under-counts.
    """
    ascii_only = line.isascii()
    filled = len(values) - values.count("")
    each = limits.STR_BYTES if ascii_only else limits.WIDE_STR_BYTES
    chars = len(line) if ascii_only else 2 * len(line)
    return limits.ROW_BYTES + limits.SLOT_BYTES * columns + each * filled + chars


def detect_encoding(data: bytes) -> tuple[str, int]:
    """``(encoding, bytes to skip)``: see the module docstring. Raises ``XerRefusal``."""
    if data[:2] in _UTF16_BOMS:
        raise XerRefusal("unsupported_encoding")
    if data.startswith(_UTF8_BOM):
        return "utf-8", len(_UTF8_BOM)
    if data.isascii():
        return "ascii", 0
    decoder = codecs.getincrementaldecoder("utf-8")()
    try:
        for start in range(0, len(data), _CHUNK):
            decoder.decode(data[start : start + _CHUNK])
        decoder.decode(b"", final=True)
    except UnicodeDecodeError:
        return "cp1252", 0  # strict: an undefined byte is refused when its line is decoded
    return "utf-8", 0


def _decode(line: bytes, encoding: str) -> str:
    try:
        return line.decode(encoding)
    except UnicodeDecodeError as exc:
        raise XerRefusal("bad_encoding") from exc


def _header(line: str) -> tuple[str, ...]:
    if line.count("\t") >= limits.MAX_HEADER_FIELDS:  # counted before the line is split
        raise XerRefusal("bad_header")
    fields = line.split("\t")
    if fields[0] != "ERMHDR":
        raise XerRefusal("bad_header")
    if any(len(f) > limits.MAX_HEADER_FIELD_CHARS for f in fields):
        raise XerRefusal("bad_header")
    return tuple(fields[1:])


def read_xer(data: bytes) -> RawXer:
    """The raw tables of ``data``. Raises ``XerRefusal`` (and nothing else) for a bad file."""
    if len(data) > limits.MAX_BYTES:
        raise XerRefusal("too_large")
    encoding, skip = detect_encoding(data)
    stream = io.BytesIO(data)
    stream.seek(skip)
    header: tuple[str, ...] | None = None
    tables: list[RawTable] = []
    seen: set[str] = set()
    # the table being read
    name: str | None = None
    columns: tuple[str, ...] | None = None
    rows: list[tuple[str, ...]] = []
    cells = 0
    memory = 0  # what the rows of the file are estimated to take, in bytes (see `row_memory`)
    total_rows = 0
    ended = False

    def close_table() -> None:
        nonlocal name, columns, rows
        if name is None:
            return
        if columns is None:
            raise XerRefusal("no_columns", table=name)
        tables.append(RawTable(name, columns, tuple(rows)))
        name, columns, rows = None, None, []

    for raw in stream:
        line = _decode(raw.rstrip(b"\r\n"), encoding)
        if not line:
            continue
        if FORBIDDEN.search(line) is not None:
            raise XerRefusal("control_character")
        if ended:
            raise XerRefusal("data_after_end")
        if header is None:
            if not line.startswith("ERMHDR"):
                raise XerRefusal("not_xer")
            header = _header(line)
            continue
        if line.count("\t") > limits.MAX_COLUMNS:
            raise XerRefusal("too_many_columns", table=name)
        fields = line.split("\t")
        marker = fields[0]
        if marker == "%R":
            if columns is None or name is None:
                raise XerRefusal("row_before_fields", table=name)
            values = fields[1:]
            if len(values) > len(columns):
                raise XerRefusal("ragged_row", table=name, row=len(rows) + 1)
            if len(rows) >= limits.MAX_ROWS_PER_TABLE:
                raise XerRefusal("too_many_rows", table=name)
            total_rows += 1
            if total_rows > limits.MAX_ROWS_TOTAL:
                raise XerRefusal("too_many_rows")
            cells += len(columns)
            memory += row_memory(line, values, len(columns))
            if memory > limits.MAX_ROW_MEMORY:
                raise XerRefusal("too_many_cells")
            if values and len(max(values, key=len)) > limits.MAX_FIELD_CHARS:
                raise XerRefusal("field_too_long", table=name, row=len(rows) + 1)
            if len(values) < len(columns):
                values.extend([""] * (len(columns) - len(values)))
            rows.append(tuple(values))
        elif marker == "%T":
            close_table()
            if len(fields) != 2:
                raise XerRefusal("bad_table_marker")
            table_name = fields[1]
            if len(table_name) > limits.MAX_NAME_CHARS or _NAME.fullmatch(table_name) is None:
                raise XerRefusal("bad_table_name")
            if table_name.lower() in seen:  # `ZZ` and `zz` are one table to the lake and to SQL
                raise XerRefusal("duplicate_table", table=table_name)
            if len(seen) >= limits.MAX_TABLES:
                raise XerRefusal("too_many_tables")
            seen.add(table_name.lower())
            name = table_name
        elif marker == "%F":
            if name is None or columns is not None:
                raise XerRefusal("fields_before_table", table=name)
            names = fields[1:]
            if not names:
                raise XerRefusal("no_columns", table=name)
            for column in names:
                if len(column) > limits.MAX_NAME_CHARS or _NAME.fullmatch(column) is None:
                    raise XerRefusal("bad_field_name", table=name)
            if len({column.lower() for column in names}) != len(names):  # `A` and `a` collide
                raise XerRefusal("duplicate_field", table=name)
            columns = tuple(names)
        elif marker == "%E":
            close_table()
            ended = True
        elif marker.startswith("%"):
            raise XerRefusal("unknown_marker", table=name)
        else:
            raise XerRefusal("unexpected_line", table=name)
    if header is None:
        raise XerRefusal("not_xer")
    if not ended:
        raise XerRefusal("missing_end")
    return RawXer(
        header=header, tables=tuple(tables), encoding=encoding, cells=cells, size=len(data)
    )
