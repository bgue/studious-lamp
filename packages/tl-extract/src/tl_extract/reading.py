"""Shared limits and helpers of every reader in this package (P1-I3B-S1).

Extractors read untrusted bytes. The rules that keep that safe live here, once:

* the bounds of the contract (``MAX_SOURCE_BYTES``, ``MAX_ROWS``, ``MAX_COLUMNS``,
  ``MAX_CELL_CHARS``) plus three of our own that cap memory (``MAX_CELLS``, ``MAX_TOTAL_CHARS``)
  and time (``MAX_BLANK_RUN``); a bigger input is refused with a problem, never truncated;
* a reader that cannot go on raises ``Refusal``; ``run_guarded`` turns that, and any other error,
  into a ``failed`` result whose messages hold fixed text and a short, cleaned excerpt of what the
  file said, never a path, never a stack trace;
* text that came from a file is cleaned before it reaches a message or a metadata field
  (``shown``, ``clean_metadata_text``), and a cell with a control character is a problem of its
  row (``has_unstorable_character``): a NUL crashes Postgres and a lone surrogate poisons the
  driver connection (L-P1-I2-17, L-P1-I0A-14).
"""

from __future__ import annotations

import logging
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from typing import BinaryIO

from tl_core.derivation import (
    MAX_SOURCE_BYTES,
    Cell,
    ExtractionProblem,
    ExtractionResult,
    FileMetadata,
    SourceFile,
)

#: Cells of one table (rows times named columns). The contract allows 20 000 x 200 = 4 million,
#: which would hold gigabytes of text; one million is more than any index or list needs.
MAX_CELLS = 1_000_000
#: Characters of cell text read from one file, over all cells.
MAX_TOTAL_CHARS = 64 * 1024 * 1024
#: The header is a row number a person types; titles above a header block are rarely deeper.
MAX_HEADER_ROW = 1000
#: A column name longer than this is a sign of a wrong header row, not a name.
MAX_HEADER_CHARS = 200
#: A sheet that was formatted down to row one million has blank rows with cells; after this many
#: blank rows in a row the reader stops and says so in a note.
MAX_BLANK_RUN = 1000
#: The note every ``metadata_only`` result carries (the contract checks for "ADR-0008").
STUBBED_NOTE = "content extraction stubbed (ADR-0008 decision 8): {what} was not read"

#: Row problems a result lists; the rest are counted in one closing problem.
MAX_PROBLEMS = 1000
#: Longest message a problem carries.
MAX_MESSAGE_CHARS = 300


class Refusal(Exception):
    """A reader cannot go on. ``code`` is the problem code; ``message`` is fixed text.

    Never reaches a caller: ``run_guarded`` turns it into a ``failed`` result.
    """

    def __init__(self, code: str, message: str, row: int | None = None) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.row = row


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


def problem(code: str, message: str, row: int | None = None) -> ExtractionProblem:
    """An ``ExtractionProblem`` whose message is cut to ``MAX_MESSAGE_CHARS``."""
    if len(message) > MAX_MESSAGE_CHARS:
        message = message[: MAX_MESSAGE_CHARS - 1] + "…"
    return ExtractionProblem(code=code, message=message, row=row)


def metadata_for(source: SourceFile, **extra: object) -> FileMetadata:
    """The metadata every result carries (content type, size, hash) plus what the format gave."""
    return FileMetadata.model_validate(
        {
            "content_type": source.content_type,
            "size": source.size,
            "sha256": source.sha256,
            **extra,
        }
    )


def read_exact(source: SourceFile, data: BinaryIO) -> bytes:
    """Read the source: exactly ``source.size`` bytes, and never more than ``MAX_SOURCE_BYTES``.

    Raises ``Refusal`` (``source_too_large`` before anything is read; ``size_mismatch`` when the
    stream holds more or fewer bytes than it was said to).
    """
    if source.size < 0 or source.size > MAX_SOURCE_BYTES:
        raise Refusal(
            "source_too_large",
            f"the file is {source.size} bytes; an extractor takes at most "
            f"{MAX_SOURCE_BYTES // (1024 * 1024)} MiB",
        )
    raw = data.read(source.size + 1)
    if len(raw) != source.size:
        raise Refusal(
            "size_mismatch",
            f"the stream holds {len(raw)} bytes but the file is said to be {source.size}",
        )
    return raw


def failed(
    name: str,
    version: str,
    source: SourceFile,
    problems: Sequence[ExtractionProblem],
    notes: Sequence[str] = (),
) -> ExtractionResult:
    """A ``failed`` result: the metadata the source already tells, and why it could not be read."""
    return ExtractionResult(
        extractor=name,
        extractor_version=version,
        status="failed",
        metadata=metadata_for(source),
        problems=list(problems),
        notes=list(notes),
    )


def run_guarded(
    name: str,
    version: str,
    source: SourceFile,
    body: Callable[[], ExtractionResult],
) -> ExtractionResult:
    """Run ``body`` and never let it raise: ``extract`` must return a result for any input.

    A ``Refusal`` becomes a ``failed`` result with its code and message. Any other exception (a
    parser library's own error, ``RecursionError`` on a deeply nested file, ``MemoryError``) becomes
    ``failed`` with the code ``unreadable`` and fixed text: the exception's text can hold names and
    paths from inside the file or the machine, so it is logged at debug level and not returned.
    """
    try:
        return body()
    except Refusal as refusal:
        return failed(name, version, source, [problem(refusal.code, refusal.message, refusal.row)])
    except Exception as exc:
        logging.getLogger(__name__).debug("extractor %s failed: %r", name, exc)
        return failed(
            name,
            version,
            source,
            [problem("unreadable", "the file could not be read as the format it claims to be")],
        )


@dataclass
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


@dataclass
class GridMeta:
    """What a spreadsheet file says about itself (XLSX core properties). All text is cleaned."""

    title: str | None = None
    author: str | None = None
    created: str | None = None
    modified: str | None = None


@dataclass
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
