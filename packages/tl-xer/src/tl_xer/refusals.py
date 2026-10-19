"""The ways a file is refused, each with a fixed message (P1-I4-T03).

A refusal never echoes the file: the text is fixed, and the only things added are a table name or a
column name that already passed the name pattern (ASCII letters, digits and underscore, at most 64
characters) and a row number. No path, no field value, no exception text.
"""

from __future__ import annotations

from typing import Final

#: code -> message. A code is part of the interface: the CLI, the TUI and the tests match on it.
MESSAGES: Final[dict[str, str]] = {
    "too_large": "the file is larger than the limit",
    "not_xer": "the file does not start with an ERMHDR line",
    "unsupported_encoding": "the file is UTF-16; export it as ANSI (Windows-1252) or UTF-8",
    "bad_encoding": "the file is neither UTF-8 nor Windows-1252",
    "control_character": "the file holds a control character or a text-direction mark",
    "bad_header": "the ERMHDR line is malformed",
    "unexpected_line": "a line is neither a table marker nor a row",
    "unknown_marker": "a line starts with an unknown marker",
    "bad_table_marker": "a %T line does not name exactly one table",
    "bad_table_name": "a table name is not made of letters, digits and underscores",
    "duplicate_table": "a table appears twice (names are compared ignoring case)",
    "too_many_tables": "the file has more tables than the limit",
    "fields_before_table": "a %F line comes before any %T line or repeats",
    "bad_field_name": "a column name is not made of letters, digits and underscores",
    "duplicate_field": "a table names a column twice (names are compared ignoring case)",
    "too_many_columns": "a table has more columns than the limit",
    "no_columns": "a table has no columns",
    "row_before_fields": "a %R line comes before the %F line of its table",
    "ragged_row": "a row has more fields than its table has columns",
    "field_too_long": "a field is longer than the limit",
    "too_many_rows": "a table, or the file as a whole, has more rows than the limit",
    "too_many_cells": "the file would take more memory to read than the limit allows",
    "data_after_end": "there is data after the %E line",
    "missing_end": "the file has no %E line; it was cut short",
    "parser_error": "the file could not be read",
}


class XerRefusal(Exception):  # noqa: N818 - a name for what happened
    """The file cannot be read. ``code`` keys ``MESSAGES``; ``table`` and ``row`` say where."""

    def __init__(self, code: str, *, table: str | None = None, row: int | None = None) -> None:
        super().__init__(code)
        self.code = code
        self.table = table
        self.row = row

    @property
    def message(self) -> str:
        return MESSAGES[self.code]
