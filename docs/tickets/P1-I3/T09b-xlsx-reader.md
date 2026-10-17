# P1-I3-T09b — XLSX reader

Status: ready
Tier: haiku
Labels: core, security
Depends on: P1-I3B-S1, S2b, S4 on `p1/i3b` (the package, the shared helpers and the stubs are in the tree); no other ticket
Branch: `p1/i3b-t09b-xlsx-reader`

## Goal
`read_xlsx(raw, options)` turns the bytes of an XLSX workbook into a `RawGrid`, safely. `packages/tl-extract/src/tl_extract/xlsxgrid.py` has the constants, `_member_limit`, `_chunks` and `_iso` written; `check_archive`, `scan_xml_parts`, `cell_text`, `read_xlsx`, `_read_workbook` and `_read_rows` raise `NotImplementedError`. You implement them by their STEPS comments. One provided test file must pass. An XLSX is a ZIP archive of XML, so the order of the guards is the point: the archive's declared sizes are checked, then every XML part is scanned for a document type or entity declaration, and only then does openpyxl parse anything, read-only, values only, without following links.

## Brief references (pasted)
> **FANOUT D1 (orchestrator decision).** ADR-0008 decision 8 is applied as follows. PDF and OCR extractors read real metadata and return `status="metadata_only"` with empty rows and a note naming the decision. A CSV or XLSX that a person attaches as the derived content is read deterministically and fills `rows`: that is data entry, not content extraction. No LLM, no OCR engine, no network, no spend.
>
> **FANOUT D4 (bounds).** 50 MiB per source, 20 000 rows, 200 columns, 10 000 characters per cell; bigger is refused with a problem, never truncated. Extractors are pure: no ledger, no unit of work, no network, no filesystem path from user input.
>
> **Contract (`tl_core.derivation.types`).** `extract` never raises for bad input: a bad file is `status="failed"` with problems; messages hold fixed text and the caller's values, never a stack trace or a path.
>
> **How the package is built.** The readers of this package are small functions that return a value or raise `Refusal(code, message)`. `reading.run_guarded` (in the extractor, already written) turns a `Refusal`, and any other exception, into a `failed` result. A reader therefore never builds an `ExtractionResult`.

### Specification
- Do not change `reading.py`, `options.py`, `table.py` or the provided test. Semantic limits (`MAX_COLUMNS`, `MAX_CELL_CHARS`, headers) are judged by `table.build_table`; this reader enforces resource limits and shape.
- Call openpyxl as `openpyxl.load_workbook(...)` (the module attribute; the test replaces it and checks the three keyword arguments). Do not write `from openpyxl import load_workbook`.
- Never evaluate a formula (`data_only=True` reads the value the file stored), never open an external link (`keep_links=False`), never run a macro, never extract a part to disk.
- The size a ZIP archive declares for a part bounds what Python's `zipfile` returns for it, so `check_archive` on the declared sizes is a real limit. Do not read a part to find out how big it is.
- A message never contains `str(exc)`, a path, a part name or the text of a cell, except the sheet names `SHEET_NOT_FOUND` shows through `shown(...)`.
- openpyxl in `read_only` mode fills a gap between two rows with empty rows and does not pad after the last row; `iter_rows(max_col=...)` cuts and pads every record to that width. Rely on that, and on `MAX_BLANK_RUN`, to stop a sheet that is formatted down to a million rows.

### Learnings that apply
> **L-P1-I2-16 / L-P1-I2-17** as for the CSV reader: trailing blank cells are dropped, a NUL or control character is passed through for `build_table` to turn into a problem.
>
> **What openpyxl does without a core part.** It answers `workbook.properties` with `creator="openpyxl"` and the time of the call. The reader must not ask for properties when `docProps/core.xml` is not in the archive (`has_core_properties`), or a made-up author and date reach the result.

> **L-P0-I1-6.** ruff's `E501` applies to comments and docstrings at 100 columns, and pyright strict flags `@contextmanager` functions annotated `Iterator[X]`. Wrap prose.
>
> **L-P0-I8A-9.** Hostile input raises errors other than the ones a parser documents (`RecursionError`, `ValueError` for integers over 4300 digits, `OverflowError`). Here `run_guarded` catches them, so do not add `except Exception` to a reader unless the STEPS say so.
>
> **L-P0-I6C-8 / L-P1-I0B-3.** Write files with the Write tool, not a long `cat > file <<'EOF'` inside a `&&` chain, and never `pkill -f`: kill only a PID you started.

## Interfaces (verbatim from the repo at the branch point)
`packages/tl-extract/src/tl_extract/xlsxgrid.py` (the stub you complete; the whole file):
```python
# ruff: noqa: F401, F841
"""Read an XLSX workbook into a ``RawGrid`` (P1-I3B-T09b).

An XLSX file is a ZIP archive of XML parts, which makes it the most dangerous input of this
package. The guards, in the order they run:

1. the bytes must be a ZIP archive with a workbook part (``not_xlsx``);
2. the archive is checked before anything is parsed: at most ``MAX_MEMBERS`` parts, no encrypted
   part, a name that is a plain relative path, the declared size of each part and of all parts
   together under their limits (``zip_bomb``); the size the archive declares bounds what the
   reader will return, so the declared sizes are the real bounds;
3. every XML part is scanned for a document type declaration or an entity declaration, and for an
   encoding that hides one (UTF-16), and refused if it has one (``unsafe_xlsx``): a workbook
   written by a spreadsheet program has none, and without them entity expansion cannot happen;
4. openpyxl opens the workbook ``read_only`` (rows are streamed, not built), ``data_only`` (the
   values the file stored; a formula is never evaluated) and ``keep_links=False`` (external
   workbooks are never opened). Macros are never run.

Cell values are turned into text here, deterministically (see ``cell_text``).

STUB (P1-I3B-T09b): the functions with a STEPS comment are for you to write. When they are
written, delete this paragraph, the STEPS comments and the `ruff: noqa` line at the top.
"""

from __future__ import annotations

import datetime as dt
import io
import warnings
import zipfile
import zlib
from collections.abc import Iterator

import openpyxl
from tl_core.derivation import MAX_COLUMNS, MAX_ROWS, Cell

from tl_extract.options import TableOptions
from tl_extract.reading import (
    MAX_BLANK_RUN,
    CellBudget,
    GridMeta,
    RawGrid,
    Refusal,
    clean_metadata_text,
    shown,
)

MAX_MEMBERS = 2000
MAX_TOTAL_UNCOMPRESSED = 200 * 1024 * 1024
MAX_SHARED_STRINGS_BYTES = 32 * 1024 * 1024
MAX_SHEET_BYTES = 150 * 1024 * 1024
MAX_OTHER_BYTES = 16 * 1024 * 1024
XML_SUFFIXES = (".xml", ".rels", ".vml")
SCAN_CHUNK = 64 * 1024
FORBIDDEN = (b"<!DOCTYPE", b"<!ENTITY")

NOT_XLSX = "the file is not an XLSX workbook (a ZIP archive)"
LINKS_NOTE = "the workbook links to other workbooks; the links are not followed"
MACROS_NOTE = "the workbook holds macros; they are never run"
BLANK_RUN_NOTE = "reading stopped after {count} blank rows in a row"
SHEET_NOT_FOUND = "there is no sheet {name}; the sheets are: {available}"


def _member_limit(name: str) -> int:
    if name == "xl/sharedStrings.xml":
        return MAX_SHARED_STRINGS_BYTES
    if name.startswith("xl/worksheets/") and name.endswith(".xml"):
        return MAX_SHEET_BYTES
    return MAX_OTHER_BYTES


def check_archive(archive: zipfile.ZipFile) -> None:
    """Refuse an archive by what it declares, before any part is read. Raises ``Refusal``
    (``not_xlsx``, ``zip_bomb`` or ``encrypted_file``)."""
    # STEPS
    # 1. members = archive.infolist(). If len(members) > MAX_MEMBERS raise Refusal("zip_bomb",
    #    f"the workbook has more than {MAX_MEMBERS} parts").
    # 2. total = 0. For each info in members, name = info.filename, then these checks in this
    #    order:
    # 3. (a) an unsafe name: it starts with "/", or ".." is one of the parts of
    #    name.replace("\\", "/").split("/"), or it contains "\x00": Refusal("not_xlsx", "the
    #    workbook has a part with an unsafe name").
    # 4. (b) info.flag_bits & 0x1 (an encrypted part): Refusal("encrypted_file", "the workbook
    #    is encrypted; it cannot be read").
    # 5. (c) info.file_size > _member_limit(name): Refusal("zip_bomb", f"a part of the workbook
    #    expands to {info.file_size} bytes; too big").
    # 6. (d) total += info.file_size.
    # 7. After the loop, if total > MAX_TOTAL_UNCOMPRESSED raise Refusal("zip_bomb", f"the
    #    workbook expands to {total} bytes; the limit is {MAX_TOTAL_UNCOMPRESSED // (1024 *
    #    1024)} MiB").
    # 8. names = {info.filename for info in members}. If "xl/workbook.xml" or
    #    "[Content_Types].xml" is not in names raise Refusal("not_xlsx", "the file is a ZIP
    #    archive but not an XLSX workbook").
    raise NotImplementedError


def _chunks(archive: zipfile.ZipFile, name: str) -> Iterator[bytes]:
    with archive.open(name) as part:
        while chunk := part.read(SCAN_CHUNK):
            yield chunk


def scan_xml_parts(archive: zipfile.ZipFile) -> None:
    """Refuse a workbook whose XML declares a document type or an entity, or is in an encoding
    that would hide one. Raises ``Refusal("unsafe_xlsx", ...)``."""
    # STEPS
    # 1. For each info in archive.infolist(): skip it unless
    #    info.filename.lower().endswith(XML_SUFFIXES), and skip it when info.file_size == 0.
    # 2. tail = b""; first = True. For each chunk in _chunks(archive, info.filename):
    # 3. (a) On the first chunk only: head = chunk[:4]. If head starts with b"\xff\xfe" or
    #    b"\xfe\xff", or b"\x00" is in head, raise Refusal("unsafe_xlsx", "the workbook has an
    #    XML part in an unsupported encoding"). UTF-16 text would hide a declaration from the
    #    byte search below.
    # 4. (b) window = tail + chunk. If any marker of FORBIDDEN is in window raise
    #    Refusal("unsafe_xlsx", "the workbook declares a document type or an entity, which a
    #    spreadsheet program never writes").
    # 5. (c) tail = window[-(len(FORBIDDEN[0]) - 1) :], the last 8 bytes, so that a marker split
    #    between two chunks is still found.
    raise NotImplementedError


def cell_text(value: object) -> Cell:
    """A cell value as text, the same for the same value every time.

    None and an empty string are None. A bool is ``TRUE`` or ``FALSE``. An int is its digits. A
    float is written with up to 15 significant digits and no trailing zeros (``2024.0`` is
    ``2024``). A date is ``YYYY-MM-DD``; a date with a time is ISO 8601 and drops the time when it
    is midnight; a time of day is ``HH:MM:SS``. Everything else is ``str(value)``.
    """
    # STEPS
    # 1. Test the value in this order; the first that fits decides (bool must come before int,
    #    and datetime before date):
    # 2. None gives None. A bool gives "TRUE" or "FALSE". An int gives str(value). A float gives
    #    format(value, ".15g").
    # 3. A datetime.datetime gives value.date().isoformat() when value.time() ==
    #    datetime.time(0), else value.isoformat(). A datetime.date gives value.isoformat(). A
    #    datetime.time gives value.isoformat().
    # 4. Anything else: text = str(value); return text if text else None. The module imports
    #    datetime as dt.
    raise NotImplementedError


def _iso(value: object) -> str | None:
    if isinstance(value, dt.datetime):
        text = value.isoformat(timespec="seconds")
        return text if value.tzinfo is not None else text + "Z"
    return None


def read_xlsx(raw: bytes, options: TableOptions) -> RawGrid:
    """The rows of one sheet of ``raw`` as a ``RawGrid`` (see its docstring for what they hold).

    The sheet is ``options.sheet`` or the first visible worksheet. Rows are read until the end of
    the sheet or until ``MAX_BLANK_RUN`` blank rows in a row (a note says so).

    Raises ``Refusal`` with the code ``not_xlsx``, ``zip_bomb``, ``encrypted_file``,
    ``unsafe_xlsx``, ``sheet_not_found``, ``no_sheet``, ``too_many_rows``, ``too_many_cells`` or
    ``too_much_text``.
    """
    # STEPS
    # 1. If not raw.startswith(b"PK\x03\x04") raise Refusal("not_xlsx", NOT_XLSX).
    # 2. archive = zipfile.ZipFile(io.BytesIO(raw)). zipfile.BadZipFile raises the same Refusal,
    #    from the error.
    # 3. with archive: call check_archive(archive) and scan_xml_parts(archive) inside a try;
    #    zipfile.BadZipFile, EOFError and zlib.error there become Refusal("not_xlsx", "the
    #    workbook archive is damaged") from the error. Then names = set(archive.namelist()).
    # 4. notes = []. If any name starts with "xl/externalLinks/" append LINKS_NOTE. If
    #    "xl/vbaProject.bin" is in names append MACROS_NOTE. In that order.
    # 5. with warnings.catch_warnings(): warnings.simplefilter("ignore") (openpyxl warns about
    #    workbooks other programs wrote). Inside it return _read_workbook(raw, options, notes,
    #    "docProps/core.xml" in names).
    raise NotImplementedError


def _read_workbook(
    raw: bytes, options: TableOptions, notes: list[str], has_core_properties: bool
) -> RawGrid:
    # STEPS
    # 1. workbook = openpyxl.load_workbook(io.BytesIO(raw), read_only=True, data_only=True,
    #    keep_links=False). Call it as `openpyxl.load_workbook` (the module attribute, not a
    #    name imported from it) with exactly these three keyword arguments: the test replaces
    #    that attribute and checks the call. Everything below runs in a try whose finally clause
    #    calls workbook.close().
    # 2. sheets = list(workbook.worksheets). If there are none raise Refusal("no_sheet", "the
    #    workbook has no worksheet").
    # 3. sheet_names = [clean_metadata_text(name) or "" for name in workbook.sheetnames].
    # 4. If options.sheet is not None: chosen is the sheet whose title == options.sheet (exact
    #    comparison). If there is none raise Refusal("sheet_not_found",
    #    SHEET_NOT_FOUND.format(name=shown(options.sheet, 40), available=available)) with
    #    available = ", ".join(shown(s.title, 40) for s in sheets[:10]). Otherwise chosen is the
    #    first sheet whose sheet_state == "visible", else sheets[0].
    # 5. meta = GridMeta(). Only when has_core_properties is true: props = workbook.properties;
    #    meta = GridMeta(title=clean_metadata_text(props.title),
    #    author=clean_metadata_text(props.creator), created=_iso(props.created),
    #    modified=_iso(props.modified)). Without a core part openpyxl makes up a creator and a
    #    time, so it must not be asked.
    # 6. rows, skipped = _read_rows(chosen.iter_rows(max_col=MAX_COLUMNS + 1, values_only=True),
    #    options, notes). title = clean_metadata_text(chosen.title) or "".
    # 7. After the try/finally return RawGrid(rows=rows, sheet=title, sheet_names=sheet_names,
    #    skipped_blank_rows=skipped, notes=notes, meta=meta).
    raise NotImplementedError


def _read_rows(
    source: Iterator[tuple[object, ...]], options: TableOptions, notes: list[str]
) -> tuple[list[list[Cell]], int]:
    # STEPS
    # 1. budget = CellBudget(); rows = []; skipped = 0; kept = 0; blank_run = 0.
    # 2. for index, values in enumerate(source, start=1): cells = [cell_text(v) for v in
    #    values]. Drop trailing cells that are blank (`while cells and not (cells[-1] or
    #    "").strip(): cells.pop()`). iter_rows has already cut the record at MAX_COLUMNS + 1
    #    cells. Then budget.take(cells).
    # 3. If index <= options.header_row: rows.append(cells) and continue (the records up to and
    #    including the header are kept as they are).
    # 4. If cells is empty: skipped += 1; blank_run += 1; if blank_run >= MAX_BLANK_RUN then
    #    notes.append(BLANK_RUN_NOTE.format(count=MAX_BLANK_RUN)) and break; otherwise continue.
    # 5. blank_run = 0; kept += 1; if kept > MAX_ROWS raise Refusal("too_many_rows", f"the sheet
    #    has more than {MAX_ROWS} data rows; split the file"); rows.append(cells).
    # 6. Return rows, skipped.
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
- `packages/tl-extract/src/tl_extract/xlsxgrid.py`
- `packages/tl-extract/src/tl_extract/reading.py`
- `packages/tl-extract/src/tl_extract/options.py`
- `docs/tickets/P1-I3/provided/t09b-test_xlsxgrid.py.txt`
- `packages/tl-extract/tests/extractsupport.py` (the test helpers the provided test imports)
may explore: (none)

## Allowed paths
- `packages/tl-extract/src/tl_extract/xlsxgrid.py` (edit)
- `packages/tl-extract/tests/test_xlsxgrid.py` (create; byte-identical copy of the provided test)
- `docs/reports/P1-I3/P1-I3-T09b.md` (create; commit it)

## Steps
1. `uv sync --all-packages` (a new worktree has an empty `.venv`).
2. Copy `docs/tickets/P1-I3/provided/t09b-test_xlsxgrid.py.txt` to `packages/tl-extract/tests/test_xlsxgrid.py`. Do not edit it.
3. Implement the functions marked STEPS in `xlsxgrid.py`. Remove the `STUB` paragraph of the module docstring, the STEPS comments and the `# ruff: noqa: F401, F841` line; remove the imports that are then unused.
4. Run the acceptance commands. Write the report and commit it with the code.

## Acceptance
```
just check
uv run pytest packages/tl-extract/tests/test_xlsxgrid.py -q
uv run pytest packages/tl-extract -q
```
Expected: `just check` clean; 76 tests pass in `test_xlsxgrid.py` (37 test functions; the rest are parametrized cases); the whole package passes (109 tests that are already there, plus these). These tests do not touch a database, so there is no `--adapters` run.

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
