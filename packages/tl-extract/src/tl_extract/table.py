"""From raw grid to extracted table: headers, rows, profiles (P1-I3B-S1; FANOUT D1, D4).

``build_table`` is the one place that turns what a grid reader found (``RawGrid``) into the
``columns``, ``rows`` and ``profiles`` of an ``ExtractionResult``, so CSV and XLSX behave alike.

Rules (each is pinned by ``tests/test_table.py``):

* The header record is ``options.header_row``. A header cell is stripped and its inner
  whitespace collapsed. A blank header cell is an unnamed column: it is ignored, as the P1-I2
  import does (L-P1-I2-16), and the result says so in a note. A header with a control character,
  or over ``MAX_HEADER_CHARS``, refuses the file.
* More than ``MAX_COLUMNS`` columns (up to the last named one) refuses the file.
* ``normalise_headers`` and ``header_map`` rename columns (see ``TableOptions``). Two columns with
  the same final name refuse the file (``duplicate_header``) unless ``duplicate_headers`` is
  ``suffix``.
* A data cell is stripped; an empty cell is None. A cell with a control character is None and a
  problem of its row (``control_character``); the rest of the row is kept. A cell over
  ``MAX_CELL_CHARS`` refuses the file (``cell_too_long``). Data in a column that has no name
  (a blank header cell, or a position past the last header cell) is not read and is a problem
  of its row (``extra_cells``). At most ``MAX_PROBLEMS`` problems are listed.
* A row is numbered by its place among the kept data rows (the first is 1), so that
  ``problem.row`` indexes ``rows``. Blank rows are skipped and counted in a note. More than
  ``MAX_ROWS`` kept rows refuses the file.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from tl_core.derivation import (
    MAX_CELL_CHARS,
    MAX_COLUMNS,
    MAX_ROWS,
    Cell,
    ColumnProfile,
    ExtractionProblem,
)

from tl_extract.options import TableOptions
from tl_extract.reading import (
    MAX_CELLS,
    MAX_HEADER_CHARS,
    MAX_PROBLEMS,
    RawGrid,
    Refusal,
    has_unstorable_character,
    problem,
    shown,
)


@dataclass
class Table:
    columns: list[str]
    rows: list[dict[str, Cell]]
    profiles: list[ColumnProfile]
    problems: list[ExtractionProblem] = field(default_factory=list[ExtractionProblem])
    notes: list[str] = field(default_factory=list[str])


class Problems:
    """Collects row problems and lists at most ``MAX_PROBLEMS`` of them; the rest are counted in
    one closing problem, so a bad file cannot make a result of a million problems."""

    def __init__(self) -> None:
        self._items: list[ExtractionProblem] = []
        self._more = 0

    def add(self, item: ExtractionProblem) -> None:
        if len(self._items) < MAX_PROBLEMS:
            self._items.append(item)
        else:
            self._more += 1

    def listed(self) -> list[ExtractionProblem]:
        if not self._more:
            return list(self._items)
        closing = problem("more_problems", f"{self._more} more problem(s) are not listed")
        return [*self._items, closing]


def match_key(header: str) -> str:
    """The loose form two header spellings are compared in: lower case, every run of characters
    that are not letters or digits one ``_``, no ``_`` at either end."""
    return re.sub(r"[\W_]+", "_", header.lower()).strip("_")


def snake_case(header: str) -> str:
    """``match_key``, or the header itself when nothing of it is a letter or digit."""
    return match_key(header) or header


def _header_names(raw_header: list[Cell]) -> tuple[list[tuple[int, str]], list[int]]:
    """The named columns as (position, collapsed name) and the positions of unnamed ones."""
    cells = list(raw_header)
    while cells and (cells[-1] is None or not cells[-1].strip()):
        cells.pop()
    if len(cells) > MAX_COLUMNS:
        raise Refusal(
            "too_many_columns",
            f"the header has more than {MAX_COLUMNS} columns; split the file",
        )
    named: list[tuple[int, str]] = []
    unnamed: list[int] = []
    for position, cell in enumerate(cells, start=1):
        text = " ".join((cell or "").split())
        if not text:
            unnamed.append(position)
            continue
        if has_unstorable_character(cell or ""):
            raise Refusal(
                "bad_header", f"the header cell at position {position} holds a control character"
            )
        if len(text) > MAX_HEADER_CHARS:
            raise Refusal(
                "bad_header",
                f"the header cell at position {position} is longer than {MAX_HEADER_CHARS} "
                "characters; is the header row right?",
            )
        named.append((position, text))
    return named, unnamed


def _rename(
    named: list[tuple[int, str]], options: TableOptions, notes: list[str]
) -> list[tuple[int, str]]:
    hints = {match_key(key): value for key, value in options.header_map.items()}
    renamed: list[tuple[int, str]] = []
    mapped: list[str] = []
    for position, name in named:
        hint = hints.get(match_key(name))
        if hint is not None:
            if hint != name:
                mapped.append(f"{shown(name)} -> {shown(hint)}")
            renamed.append((position, hint))
        elif options.normalise_headers:
            renamed.append((position, snake_case(name)))
        else:
            renamed.append((position, name))
    if mapped:
        notes.append("header hints applied: " + "; ".join(mapped))
    return renamed


def _unique(
    named: list[tuple[int, str]], options: TableOptions, notes: list[str]
) -> list[tuple[int, str]]:
    names = [name for _, name in named]
    twice = sorted({name for name in names if names.count(name) > 1})
    if not twice:
        return named
    if options.duplicate_headers == "refuse":
        raise Refusal(
            "duplicate_header",
            "the file has a column twice: " + ", ".join(shown(name) for name in twice),
        )
    taken = set(names)
    seen: dict[str, int] = {}
    result: list[tuple[int, str]] = []
    renamed: list[str] = []
    for position, name in named:
        count = seen.get(name, 0) + 1
        seen[name] = count
        if count == 1:
            result.append((position, name))
            continue
        candidate = f"{name}_{count}"
        while candidate in taken:
            count += 1
            seen[name] = count
            candidate = f"{name}_{count}"
        taken.add(candidate)
        result.append((position, candidate))
        renamed.append(f"{shown(name)} -> {shown(candidate)}")
    notes.append("duplicate headers renamed: " + "; ".join(renamed))
    return result


def _profile(name: str, values: list[Cell]) -> ColumnProfile:
    seen: dict[str, None] = {}
    non_empty = 0
    longest = 0
    for value in values:
        if value is None:
            continue
        non_empty += 1
        longest = max(longest, len(value))
        seen.setdefault(value, None)
    return ColumnProfile(
        name=name,
        non_empty=non_empty,
        distinct=len(seen),
        max_length=longest,
        samples=list(seen)[:5],
    )


def build_table(grid: RawGrid, options: TableOptions) -> Table:
    """Build the table of ``grid`` under ``options``. Raises ``Refusal`` where the rules above
    say the file is refused."""
    if len(grid.rows) < options.header_row:
        raise Refusal(
            "no_header",
            f"the file has no row {options.header_row} to read the column names from",
        )
    notes: list[str] = list(grid.notes)
    named, unnamed = _header_names(grid.rows[options.header_row - 1])
    if not named:
        raise Refusal("no_header", f"row {options.header_row} has no column names")
    if unnamed:
        listed = ", ".join(str(p) for p in unnamed[:10]) + (", ..." if len(unnamed) > 10 else "")
        notes.append(f"ignored {len(unnamed)} unnamed column(s) at position(s) {listed}")
    named = _unique(_rename(named, options, notes), options, notes)
    columns = [name for _, name in named]
    named_positions = {position for position, _ in named}
    problems = Problems()

    rows: list[dict[str, Cell]] = []
    skipped = grid.skipped_blank_rows
    for record in grid.rows[options.header_row :]:
        if all(cell is None or not cell.strip() for cell in record):
            skipped += 1
            continue
        if len(rows) >= MAX_ROWS:
            raise Refusal(
                "too_many_rows",
                f"the file has more than {MAX_ROWS} data rows; split the file",
            )
        row_number = len(rows) + 1
        row: dict[str, Cell] = {}
        for position, name in named:
            raw = record[position - 1] if position <= len(record) else None
            text = (raw or "").strip()
            if not text:
                row[name] = None
                continue
            if has_unstorable_character(text):
                problems.add(
                    problem(
                        "control_character",
                        f"{shown(name)}: holds a control character; the cell is left empty",
                        row_number,
                    )
                )
                row[name] = None
                continue
            if len(text) > MAX_CELL_CHARS:
                raise Refusal(
                    "cell_too_long",
                    f"a cell of column {shown(name)} is longer than {MAX_CELL_CHARS} characters",
                    row_number,
                )
            row[name] = text
        if any(
            cell is not None and cell.strip()
            for position, cell in enumerate(record, start=1)
            if position not in named_positions
        ):
            problems.add(
                problem(
                    "extra_cells",
                    "the row has data in a column that has no name; it is not read",
                    row_number,
                )
            )
        rows.append(row)
        if len(rows) * len(columns) > MAX_CELLS:
            raise Refusal(
                "too_many_cells", f"the table holds more than {MAX_CELLS} cells; split the file"
            )
    if skipped:
        notes.append(f"skipped {skipped} blank row(s)")
    if not rows:
        notes.append("the table has no data rows")
    profiles = [_profile(name, [row[name] for row in rows]) for name in columns]
    return Table(
        columns=columns, rows=rows, profiles=profiles, problems=problems.listed(), notes=notes
    )
