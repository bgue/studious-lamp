# P1-I3-T10 — PDF properties with pypdf

Status: ready
Tier: haiku
Labels: core
Depends on: P1-I3B-S1, S2b, S4 on `p1/i3b` (the package, the shared helpers and the stubs are in the tree); no other ticket
Branch: `p1/i3b-t10-pdf-info`

## Goal
`read_pdf_info(raw)` returns the page count and the document information (title, author, producer, creation and modification dates) of a PDF, and `pdf_date_to_iso(text)` turns a PDF date string into ISO 8601. `packages/tl-extract/src/tl_extract/pdfinfo.py` has the constants, `PdfInfo` and `_text` written; `pdf_date_to_iso` and `read_pdf_info` raise `NotImplementedError`. You implement them by their STEPS comments. One provided test file must pass. Only the information dictionary and the page count are read: no page is parsed and no stream is decoded, because the content is stubbed (ADR-0008 decision 8).

## Brief references (pasted)
> **FANOUT D1 (orchestrator decision).** ADR-0008 decision 8 is applied as follows. PDF and OCR extractors read real metadata and return `status="metadata_only"` with empty rows and a note naming the decision. A CSV or XLSX that a person attaches as the derived content is read deterministically and fills `rows`: that is data entry, not content extraction. No LLM, no OCR engine, no network, no spend.
>
> **FANOUT D4 (bounds).** 50 MiB per source, 20 000 rows, 200 columns, 10 000 characters per cell; bigger is refused with a problem, never truncated. Extractors are pure: no ledger, no unit of work, no network, no filesystem path from user input.
>
> **Contract (`tl_core.derivation.types`).** `extract` never raises for bad input: a bad file is `status="failed"` with problems; messages hold fixed text and the caller's values, never a stack trace or a path.
>
> **How the package is built.** The readers of this package are small functions that return a value or raise `Refusal(code, message)`. `reading.run_guarded` (in the extractor, already written) turns a `Refusal`, and any other exception, into a `failed` result. A reader therefore never builds an `ExtractionResult`.

### Specification
- The only library is `pypdf` (BSD-3-Clause, already a dependency of the package, version 6.21). Do not add pdfplumber, Camelot, `cryptography` or any other dependency. Use `PdfReader(..., strict=False)`.
- An encrypted PDF is refused at once (`reader.is_encrypted`): do not call `decrypt`, do not read pages or metadata. A PDF that pypdf cannot open is `broken_pdf`; the exception's text is never put in a message.
- Do not touch `reader.pages[i]`, page content, annotations, attachments or XMP metadata. `len(reader.pages)` reads the page count only.
- `pdf_date_to_iso` is pure and total: any input gives an ISO string or None, never an exception. The provided test lists the accepted and the refused forms.
- Leave the logger line in the module as it is: it keeps pypdf's repair warnings off standard error.

### Learnings that apply
> **L-P0-I8A-9.** A damaged or hostile file raises errors other than the documented ones: here `read_pdf_info` converts every exception from pypdf into `Refusal("broken_pdf", ...)` and nothing else may escape.

> **L-P0-I1-6.** ruff's `E501` applies to comments and docstrings at 100 columns, and pyright strict flags `@contextmanager` functions annotated `Iterator[X]`. Wrap prose.
>
> **L-P0-I8A-9.** Hostile input raises errors other than the ones a parser documents (`RecursionError`, `ValueError` for integers over 4300 digits, `OverflowError`). Here `run_guarded` catches them, so do not add `except Exception` to a reader unless the STEPS say so.
>
> **L-P0-I6C-8 / L-P1-I0B-3.** Write files with the Write tool, not a long `cat > file <<'EOF'` inside a `&&` chain, and never `pkill -f`: kill only a PID you started.

## Interfaces (verbatim from the repo at the branch point)
`packages/tl-extract/src/tl_extract/pdfinfo.py` (the stub you complete; the whole file):
```python
# ruff: noqa: F401, F841
"""The properties of a PDF file, read with pypdf (P1-I3B-T10; ADR-0008 decision 8).

Only the document information is read: the page count and the title, author, producer and dates
of the information dictionary. No page is parsed, no content stream is decoded, no text is
extracted; that is the stubbed part of the decision. An encrypted PDF is refused without trying a
password, and any error inside pypdf is a refusal of this file, never an exception.

STUB (P1-I3B-T10): the functions with a STEPS comment are for you to write. When they are
written, delete this paragraph, the STEPS comments and the `ruff: noqa` line at the top.
"""

from __future__ import annotations

import io
import logging
import re
from calendar import monthrange
from dataclasses import dataclass

from pypdf import PdfReader

from tl_extract.reading import Refusal, clean_metadata_text

# pypdf reports repairs and damage through logging; a library adds a handler so that Python's
# last-resort handler does not print them to standard error.
logging.getLogger("pypdf").addHandler(logging.NullHandler())

#: A PDF whose header is not in the first kilobyte is not read as one.
HEADER_WINDOW = 1024

NOT_PDF = "the file is not a PDF (no %PDF- header)"
ENCRYPTED_PDF = "the PDF is encrypted; it cannot be read"
BROKEN_PDF = "the PDF is damaged and cannot be read"

_DATE = re.compile(
    r"^(?:D:)?(\d{4})(\d{2})?(\d{2})?(\d{2})?(\d{2})?(\d{2})?"
    r"(?:(Z)(?:00'?(?:00'?)?)?|([+-])(\d{2})(?:'?(\d{2})'?)?)?$"
)


@dataclass
class PdfInfo:
    page_count: int | None = None
    title: str | None = None
    author: str | None = None
    producer: str | None = None
    #: ISO 8601, written from the PDF date string (``D:20240301101530+02'00'``).
    created: str | None = None
    modified: str | None = None


def pdf_date_to_iso(text: str) -> str | None:
    """A PDF date string as ISO 8601, or None when it is not a valid date.

    The string is ``D:YYYYMMDDHHmmSSOHH'mm'`` with every part after the year optional. The result
    keeps the parts that are there: ``2024``, ``2024-03``, ``2024-03-01``, and from an hour on
    ``2024-03-01T10:15:30`` (minutes and seconds default to ``00``). A zone is ``Z`` or
    ``+02:00``; ``Z``, ``Z00'00'`` and ``+00'00'`` are written ``Z``. A month, day, hour, minute
    or second out of range, or any other shape, is None.
    """
    # STEPS
    # 1. match = _DATE.match(text.strip()). No match gives None.
    # 2. year, month, day, hour, minute, second, zulu, sign, zone_h, zone_m = match.groups().
    #    Each of them is a string or None. The pattern only lets a part appear when the parts
    #    before it do.
    # 3. Return None when a part is out of range: month not in 1..12; day not in
    #    1..calendar.monthrange(year, month)[1] (use year 1 when the year is 0); hour > 23;
    #    minute > 59; second > 59. Check only the parts that are present.
    # 4. result = year. If month: result += f"-{month}". If day: result += f"-{day}". If hour:
    #    result += f"T{hour}:{minute or '00'}:{second or '00'}".
    # 5. If hour is None return result: a zone means nothing without a time.
    # 6. If zulu: result += "Z". Elif sign: offset_m = zone_m or "00"; return None when
    #    int(zone_h) > 23 or int(offset_m) > 59; otherwise result += "Z" when (zone_h, offset_m)
    #    == ("00", "00"), else f"{sign}{zone_h}:{offset_m}".
    # 7. Return result.
    raise NotImplementedError


def _text(value: object) -> str | None:
    return clean_metadata_text(str(value)) if isinstance(value, str) else None


def read_pdf_info(raw: bytes) -> PdfInfo:
    """The page count and document information of the PDF in ``raw``.

    Raises ``Refusal`` with the code ``not_pdf`` (no ``%PDF-`` header in the first kilobyte),
    ``encrypted_pdf`` (the file is encrypted; no password is tried) or ``broken_pdf`` (pypdf
    could not open it or read its trailer).
    """
    # STEPS
    # 1. If b"%PDF-" is not in raw[:HEADER_WINDOW] raise Refusal("not_pdf", NOT_PDF).
    # 2. In one try block: reader = PdfReader(io.BytesIO(raw), strict=False). If
    #    reader.is_encrypted raise Refusal("encrypted_pdf", ENCRYPTED_PDF); do not touch pages
    #    or metadata and do not try a password. Then metadata = reader.metadata. Let a Refusal
    #    pass through (`except Refusal: raise`) and turn any other Exception into
    #    Refusal("broken_pdf", BROKEN_PDF) from the error.
    # 3. info = PdfInfo(). In its own try/except Exception: info.page_count = len(reader.pages).
    #    When it fails the page count stays None.
    # 4. If metadata is not None, in another try/except Exception (a failure leaves the fields
    #    not yet set as None): info.title, info.author and info.producer are
    #    _text(metadata.title), _text(metadata.author) and _text(metadata.producer). created =
    #    metadata.get("/CreationDate") and modified = metadata.get("/ModDate"); each field is
    #    pdf_date_to_iso(str(value)) when the value is not None.
    # 5. Return info.
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


## Context (read these, nothing else)
- `packages/tl-extract/src/tl_extract/pdfinfo.py`
- `packages/tl-extract/src/tl_extract/reading.py`
- `docs/tickets/P1-I3/provided/t10-test_pdfinfo.py.txt`
- `packages/tl-extract/tests/extractsupport.py` (the test helpers the provided test imports)
may explore: (none)

## Allowed paths
- `packages/tl-extract/src/tl_extract/pdfinfo.py` (edit)
- `packages/tl-extract/tests/test_pdfinfo.py` (create; byte-identical copy of the provided test)
- `docs/reports/P1-I3/P1-I3-T10.md` (create; commit it)

## Steps
1. `uv sync --all-packages` (a new worktree has an empty `.venv`).
2. Copy `docs/tickets/P1-I3/provided/t10-test_pdfinfo.py.txt` to `packages/tl-extract/tests/test_pdfinfo.py`. Do not edit it.
3. Implement the functions marked STEPS in `pdfinfo.py`. Remove the `STUB` paragraph of the module docstring, the STEPS comments and the `# ruff: noqa: F401, F841` line; remove the imports that are then unused.
4. Run the acceptance commands. Write the report and commit it with the code.

## Acceptance
```
just check
uv run pytest packages/tl-extract/tests/test_pdfinfo.py -q
uv run pytest packages/tl-extract -q
```
Expected: `just check` clean; 55 tests pass in `test_pdfinfo.py` (15 test functions; the rest are parametrized cases); the whole package passes (109 tests that are already there, plus these). These tests do not touch a database, so there is no `--adapters` run.

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
