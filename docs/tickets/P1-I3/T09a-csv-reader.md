# P1-I3-T09a — CSV reader

Status: ready
Tier: haiku
Labels: core
Depends on: P1-I3B-S1, S2b, S4 on `p1/i3b` (the package, the shared helpers and the stubs are in the tree); no other ticket
Branch: `p1/i3b-t09a-csv-reader`

## Goal
`read_csv(raw, options)` turns the bytes of a CSV file into a `RawGrid` of records of raw cell text. `packages/tl-extract/src/tl_extract/csvgrid.py` has the constants, `_cell` and the signatures written; `decode_text`, `_lines`, `_records`, `detect_delimiter` and `read_csv` raise `NotImplementedError`. You implement them by their STEPS comments. One provided test file must pass. This reader is the first line of defence against hostile text: the encoding is checked, no line may be longer than a row can be, a quote that is never closed is refused, and every cell is counted as it is read.

## Brief references (pasted)
> **FANOUT D1 (orchestrator decision).** ADR-0008 decision 8 is applied as follows. PDF and OCR extractors read real metadata and return `status="metadata_only"` with empty rows and a note naming the decision. A CSV or XLSX that a person attaches as the derived content is read deterministically and fills `rows`: that is data entry, not content extraction. No LLM, no OCR engine, no network, no spend.
>
> **FANOUT D4 (bounds).** 50 MiB per source, 20 000 rows, 200 columns, 10 000 characters per cell; bigger is refused with a problem, never truncated. Extractors are pure: no ledger, no unit of work, no network, no filesystem path from user input.
>
> **Contract (`tl_core.derivation.types`).** `extract` never raises for bad input: a bad file is `status="failed"` with problems; messages hold fixed text and the caller's values, never a stack trace or a path.
>
> **How the package is built.** The readers of this package are small functions that return a value or raise `Refusal(code, message)`. `reading.run_guarded` (in the extractor, already written) turns a `Refusal`, and any other exception, into a `failed` result. A reader therefore never builds an `ExtractionResult`.

### Specification
- The reader enforces **resource** limits and shape only. The meaning of the header (names, duplicates, blank names, `MAX_COLUMNS`, `MAX_CELL_CHARS`, control characters in a cell) is judged by `table.build_table`, which is written and has its own tests. Do not do that work here, and do not change `table.py`, `reading.py` or `options.py`.
- Do not call `csv.field_size_limit`: it sets a limit for the whole process. The csv module's own default (131072) is the limit the provided test expects.
- A message never contains `str(exc)`, a path, or the text of a cell. The messages that tests compare are the constants at the top of the module (`NOT_UTF8`, `DELIMITER_NOTE`).
- The reader is pure: it reads `raw` and returns; no file, no clock, no global state.

### Learnings that apply
> **L-P1-I1-2.** `csv.reader` takes a quote that is never closed as the end of the cell unless `strict=True`; use it for any file a person exported.
>
> **L-P1-I2-16.** A legacy export often ends every line with commas, so its header has several blank cells; that is why trailing blank cells are dropped from every record here and why `build_table` ignores blank header names.
>
> **L-P1-I2-17.** A NUL in text crashes Postgres only; the reader passes it through as part of the cell and `build_table` turns it into a problem of its row. Do not strip or reject it here.

> **L-P0-I1-6.** ruff's `E501` applies to comments and docstrings at 100 columns, and pyright strict flags `@contextmanager` functions annotated `Iterator[X]`. Wrap prose.
>
> **L-P0-I8A-9.** Hostile input raises errors other than the ones a parser documents (`RecursionError`, `ValueError` for integers over 4300 digits, `OverflowError`). Here `run_guarded` catches them, so do not add `except Exception` to a reader unless the STEPS say so.
>
> **L-P0-I6C-8 / L-P1-I0B-3.** Write files with the Write tool, not a long `cat > file <<'EOF'` inside a `&&` chain, and never `pkill -f`: kill only a PID you started.

## Interfaces (verbatim from the repo at the branch point)
`packages/tl-extract/src/tl_extract/csvgrid.py` (the stub you complete; the whole file):
```python
# ruff: noqa: F401, F841
"""Read a CSV file into a ``RawGrid`` (P1-I3B-T09a).

Safe against hostile input in the ways that matter for text: the encoding is checked, no line is
longer than any legitimate record can be, a cell over the csv module's field limit is a refusal,
a quote that is never closed is a refusal (``strict=True``, L-P1-I1-2), and the number of cells and
characters is counted as the file is read (``CellBudget``).

STUB (P1-I3B-T09a): the functions with a STEPS comment are for you to write. When they are
written, delete this paragraph, the STEPS comments and the `ruff: noqa` line at the top.
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
    # STEPS
    # 1. If raw starts with b"\xff\xfe" or b"\xfe\xff", return raw.decode("utf-16") (the codec
    #    reads the mark and picks the byte order).
    # 2. Otherwise return raw.decode("utf-8-sig"): that drops a UTF-8 byte-order mark and
    #    refuses bytes that are not UTF-8.
    # 3. Catch UnicodeDecodeError around both and raise Refusal("not_utf8", NOT_UTF8) from the
    #    error.
    raise NotImplementedError


def _lines(text: str) -> Iterator[str]:
    # STEPS
    # 1. Iterate io.StringIO(text, newline=""): newline="" keeps every line ending, as the csv
    #    module wants.
    # 2. A line longer than MAX_LINE_CHARS raises Refusal("record_too_long", "a line of the file
    #    is far longer than a row can be"); any other line is yielded as it is.
    raise NotImplementedError


def _records(text: str, delimiter: str) -> Iterator[list[str]]:
    # STEPS
    # 1. reader = csv.reader(_lines(text), delimiter=delimiter, strict=True). strict=True makes
    #    a quote that is never closed an error (L-P1-I1-2).
    # 2. Write a `while True` loop around `record = next(reader)` inside try, so that only
    #    reading is covered by the except clauses and not the code that consumes the generator.
    #    StopIteration ends the generator (return). Otherwise yield the record (a list[str]).
    # 3. On csv.Error: if "field larger than field limit" is in str(exc) raise
    #    Refusal("cell_too_long", f"a cell near line {reader.line_num} is longer than a cell can
    #    be") from exc; for any other csv.Error raise Refusal("malformed_csv", f"the file is not
    #    valid CSV near line {reader.line_num}") from exc. str(exc) itself never goes into a
    #    message.
    raise NotImplementedError


def detect_delimiter(text: str, header_row: int) -> str:
    """The candidate delimiter that splits the header record into the most cells; a comma when
    none splits it. Ties go to the earlier candidate (comma, semicolon, tab, bar)."""
    # STEPS
    # 1. best = ","; best_count = 1.
    # 2. For each candidate of DELIMITER_CANDIDATES, in order: record =
    #    next(islice(_records(text, candidate), header_row - 1, None), []). That is the
    #    header_row-th record read with that delimiter, or an empty list when the file has fewer
    #    records. A Refusal raised while reading it skips this candidate (continue).
    # 3. If len(record) > best_count then candidate and len(record) become best and best_count.
    #    Only a strictly larger count wins, so ties keep the earlier candidate and a header that
    #    no candidate splits stays a comma.
    # 4. Return best.
    raise NotImplementedError


def _cell(text: str) -> Cell:
    return text if text else None


def read_csv(raw: bytes, options: TableOptions) -> RawGrid:
    """The records of ``raw`` as a ``RawGrid`` (see its docstring for what the rows hold).

    Raises ``Refusal`` with the code ``not_utf8``, ``record_too_long``, ``cell_too_long``,
    ``malformed_csv``, ``too_many_rows``, ``too_many_cells`` or ``too_much_text``.
    """
    # STEPS
    # 1. text = decode_text(raw). delimiter = options.delimiter or detect_delimiter(text,
    #    options.header_row).
    # 2. notes = []. When options.delimiter is None and delimiter != ",", append
    #    DELIMITER_NOTE.format(name=DELIMITER_NAMES[delimiter]).
    # 3. budget = CellBudget(); rows = []; skipped = 0; kept = 0.
    # 4. for index, record in enumerate(_records(text, delimiter), start=1): cells =
    #    [_cell(value) for value in record]. Drop trailing cells that are blank (`while cells
    #    and not (cells[-1] or "").strip(): cells.pop()`). Cut the record to MAX_COLUMNS + 1
    #    cells (`del cells[MAX_COLUMNS + 1 :]`). Then budget.take(cells).
    # 5. If index <= options.header_row: rows.append(cells) and continue. The records up to and
    #    including the header are kept as they are, blank or not.
    # 6. Later records: if cells is empty, skipped += 1 and continue. Otherwise kept += 1; if
    #    kept > MAX_ROWS raise Refusal("too_many_rows", f"the file has more than {MAX_ROWS} data
    #    rows; split the file"); rows.append(cells).
    # 7. Return RawGrid(rows=rows, skipped_blank_rows=skipped, notes=notes, meta=GridMeta()).
    raise NotImplementedError
```

`packages/tl-extract/src/tl_extract/reading.py` (excerpt; read-only for you):
```python
#: Cells of one table (rows times named columns). The contract allows 20 000 x 200 = 4 million,
#: which would hold gigabytes of text; one million is more than any index or list needs.
MAX_CELLS = 1_000_000

#: Characters of cell text read from one file, over all cells.
MAX_TOTAL_CHARS = 64 * 1024 * 1024

#: A sheet that was formatted down to row one million has blank rows with cells; after this many
#: blank rows in a row the reader stops and says so in a note.
MAX_BLANK_RUN = 1000

class Refusal(Exception):
    """A reader cannot go on. ``code`` is the problem code; ``message`` is fixed text.

    Never reaches a caller: ``run_guarded`` turns it into a ``failed`` result.
    """

    def __init__(self, code: str, message: str, row: int | None = None) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.row = row

class CellBudget:
    """Counts the cells and the characters a reader has taken, and refuses past the limits."""

    cells: int = 0
    chars: int = 0

    def take(self, record: Sequence[Cell]) -> None:
        """Count one record (a row of cells). Raises ``Refusal`` at ``MAX_CELLS`` or
        ``MAX_TOTAL_CHARS``."""
        self.cells += len(record)
        self.chars += sum(len(cell) for cell in record if cell is not None)
        if self.cells > MAX_CELLS:
            raise Refusal(
                "too_many_cells",
                f"the file holds more than {MAX_CELLS} cells; split it",
            )
        if self.chars > MAX_TOTAL_CHARS:
            raise Refusal(
                "too_much_text",
                f"the file holds more than {MAX_TOTAL_CHARS // (1024 * 1024)} MiB of cell text; "
                "split it",
            )

class GridMeta:
    """What a spreadsheet file says about itself (XLSX core properties). All text is cleaned."""

    title: str | None = None
    author: str | None = None
    created: str | None = None
    modified: str | None = None

class RawGrid:
    """What a grid reader (CSV or XLSX) hands to ``table.build_table``.

    ``rows`` are records of raw cell text, not stripped: ``None`` is an empty cell. They hold the
    records up to and including the header record (``options.header_row``), as they are, and then
    the data records that are not entirely blank. A record is cut after the last non-empty cell
    or after ``MAX_COLUMNS + 1`` cells, whichever comes first, so a cell at position
    ``MAX_COLUMNS + 1`` is how a too-wide header is seen without keeping a million cells.
    """

    rows: list[list[Cell]]
    #: The sheet read (XLSX), else None.
    sheet: str | None = None
    #: Every sheet's name (XLSX), else None.
    sheet_names: list[str] | None = None
    #: Data records skipped because every cell was blank.
    skipped_blank_rows: int = 0
    #: Notes the reader adds (for instance that it stopped at a long run of blank rows).
    notes: list[str] = field(default_factory=list[str])
    meta: GridMeta = field(default_factory=GridMeta)

def has_unstorable_character(text: str) -> bool:
    """A control character other than tab, CR and LF (as the P1-I2 import reads them), or a
    character that cannot be encoded as UTF-8 (a lone surrogate)."""
    for ch in text:
        code = ord(ch)
        if (code < 32 and ch not in "\t\r\n") or code == 127 or 0xD800 <= code <= 0xDFFF:
            return True
    return False

def shown(text: str, limit: int = 60) -> str:
    """Text that came from a file, made safe to put in a message: control characters become ``?``
    and a long text is cut with an ellipsis."""
    cleaned = "".join("?" if has_unstorable_character(ch) else ch for ch in text)
    cleaned = " ".join(cleaned.split())
    return cleaned if len(cleaned) <= limit else cleaned[: limit - 1] + "…"

def clean_metadata_text(text: str | None, limit: int = 1000) -> str | None:
    """A metadata string of a file (title, author, producer) made storable: unstorable characters
    become spaces, runs of whitespace one space, and the text is cut at ``limit``.

    None and an empty result are None.
    """
    if text is None:
        return None
    cleaned = "".join(" " if has_unstorable_character(ch) else ch for ch in text)
    cleaned = " ".join(cleaned.split())
    if not cleaned:
        return None
    return cleaned[:limit]
```

`packages/tl-extract/src/tl_extract/options.py` (excerpt; read-only for you):
```python
class TableOptions(BaseModel):
    """Options of ``TabularExtractor.extract``.

    * ``sheet``: the XLSX sheet to read, by name; default the first worksheet.
    * ``header_row``: the 1-based record that holds the column names (rows above it are skipped).
    * ``delimiter``: the CSV delimiter; default detected from the header record.
    * ``header_map``: column-name hints, ``{"TAG NO": "tag_number"}``. A header matches a hint
      when both are the same after lower-casing and replacing every run of characters that are
      not letters or digits by ``_`` (``Tag No.`` matches ``TAG NO``). The result uses the hint's
      value exactly as written.
    * ``normalise_headers``: write the headers that no hint named as lower-case ``snake_case``.
    * ``duplicate_headers``: ``refuse`` (default) fails the file when two columns end up with the
      same name; ``suffix`` keeps the first and names the others ``name_2``, ``name_3``.
    """

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    sheet: Annotated[str, Field(min_length=1, max_length=MAX_HEADER_CHARS)] | None = None
    header_row: Annotated[int, Field(ge=1, le=MAX_HEADER_ROW)] = 1
    delimiter: Delimiter | None = None
    header_map: dict[
        Annotated[str, Field(min_length=1, max_length=MAX_HEADER_CHARS)],
        Annotated[str, Field(min_length=1, max_length=MAX_HEADER_CHARS)],
    ] = Field(default_factory=dict[str, str], max_length=200)
    normalise_headers: bool = False
    duplicate_headers: Literal["refuse", "suffix"] = "refuse"
```


## Context (read these, nothing else)
- `packages/tl-extract/src/tl_extract/csvgrid.py`
- `packages/tl-extract/src/tl_extract/reading.py`
- `packages/tl-extract/src/tl_extract/options.py`
- `docs/tickets/P1-I3/provided/t09a-test_csvgrid.py.txt`
- `packages/tl-extract/tests/extractsupport.py` (the test helpers the provided test imports)
may explore: (none)

## Allowed paths
- `packages/tl-extract/src/tl_extract/csvgrid.py` (edit)
- `packages/tl-extract/tests/test_csvgrid.py` (create; byte-identical copy of the provided test)
- `docs/reports/P1-I3/P1-I3-T09a.md` (create; commit it)

## Steps
1. `uv sync --all-packages` (a new worktree has an empty `.venv`).
2. Copy `docs/tickets/P1-I3/provided/t09a-test_csvgrid.py.txt` to `packages/tl-extract/tests/test_csvgrid.py`. Do not edit it.
3. Implement the functions marked STEPS in `csvgrid.py`. Remove the `STUB` paragraph of the module docstring, the STEPS comments and the `# ruff: noqa: F401, F841` line; remove the imports that are then unused.
4. Run the acceptance commands. Write the report and commit it with the code.

## Acceptance
```
just check
uv run pytest packages/tl-extract/tests/test_csvgrid.py -q
uv run pytest packages/tl-extract -q
```
Expected: `just check` clean; 33 tests pass in `test_csvgrid.py` (31 test functions; the rest are parametrized cases); the whole package passes (109 tests that are already there, plus these). These tests do not touch a database, so there is no `--adapters` run.

## Tests to add
None beyond the provided file.

## Report requirements
Standard report (`docs/templates/haiku-report.md`) plus: the decisive lines of each acceptance command, and one line for every STEPS line you did differently from what it says, with the reason (or "none").

## Escalation triggers
- Stop and report *Blocked* if a STEPS line and the provided test disagree, or if a test needs a change outside the Allowed paths.
- Stop if the ticket seems to need a new dependency, a change to `reading.py`, `options.py` or `table.py`, or a change to the provided test.

## Blocked
(implementer writes here)

## Decision
(supervisor or orchestrator writes here)
