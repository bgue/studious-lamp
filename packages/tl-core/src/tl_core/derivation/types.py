"""Derivation contracts for P1-I3 (brief §9 M1 derivation pipeline; ADR-0008 decision 8).

Frozen for the increment: change only by orchestrator decision.

An *extractor* turns one source file (a rendition of a document revision) into an
:class:`ExtractionResult`. Extractors are plugins found through the entry-point group
:data:`EXTRACTOR_ENTRY_POINT`; each entry point names a zero-argument callable that returns an
object satisfying :class:`Extractor`.

ADR-0008 decision 8 applies: **no LLM call, no OCR service, no spend.** Extractors for
unstructured sources (PDF tables, OCR) report the real file metadata and leave ``rows`` empty with
status ``"metadata_only"`` and a note naming the decision. Structured tabular files that a person
supplies as the derived content (CSV, XLSX) are read deterministically and do fill ``rows``
(FANOUT D1): that is data entry, not content extraction.

The pipeline (WS-A) owns jobs, validation against a ``DocumentSchema``, the derived-document
records and publishing. Extractors (WS-B) own reading bytes. Extractors never write to the ledger,
never open a unit of work, never touch the network, and never see a secret.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, BinaryIO, Literal, Protocol, runtime_checkable

from pydantic import BaseModel, Field

#: Entry-point group under which extractor plugins are registered.
EXTRACTOR_ENTRY_POINT = "throughline.extractors"

#: Hard bounds every extractor enforces (FANOUT D4). Bigger inputs are refused, not truncated.
MAX_SOURCE_BYTES = 50 * 1024 * 1024
MAX_ROWS = 20_000
MAX_COLUMNS = 200
MAX_CELL_CHARS = 10_000
#: Data cells per result (rows x columns, header excluded); 20 000 x 50 fits, 20 000 x 200 does not.
MAX_CELLS = 1_000_000
#: Bounds on the rest of a result (FANOUT D10): the parent refuses a result past any of them.
MAX_TEXT_CHARS = 1_000
MAX_NAME_CHARS = 255
MAX_SHEET_NAMES = 256
MAX_NOTES = 100
MAX_PROBLEMS = 1_000
MAX_MESSAGE_CHARS = 500
#: Resource envelope the pipeline runs every extractor in (FANOUT D9): a separate process.
EXTRACT_MAX_SECONDS = 60
EXTRACT_MAX_MEMORY_BYTES = 1024 * 1024 * 1024

#: ``ok``: rows (if the kind yields rows) and metadata are complete.
#: ``metadata_only``: metadata only; content extraction is stubbed (ADR-0008 decision 8).
#: ``unsupported``: this extractor does not read this file; only ``notes`` is set.
#: ``failed``: the file could not be read; ``problems`` says why (no stack traces, no paths).
ExtractionStatus = Literal["ok", "metadata_only", "unsupported", "failed"]

#: A cell value as read: text, or None for an empty cell. Typing happens in validation.
Cell = str | None


class SourceFile(BaseModel):
    """What an extractor is told about the file. The bytes come separately as a stream."""

    file_id: str
    #: Display name only; never used to open anything.
    filename: str
    content_type: str
    size: int
    sha256: str
    #: Provenance of the source, e.g. "src.doc.ISD-001@A" (document key @ revision code).
    source_ref: str


class FileMetadata(BaseModel):
    """Real properties of the file where the format exposes them; None where it does not."""

    content_type: str
    size: int
    sha256: str
    page_count: int | None = None
    sheet_names: list[str] | None = None
    title: str | None = None
    author: str | None = None
    #: ISO 8601 as stored in the file, not interpreted.
    created: str | None = None
    modified: str | None = None
    #: PDF producer or the application that wrote the file.
    producer: str | None = None
    #: Images: the format as read from the header (e.g. "png", "jpeg", "tiff") and pixel size.
    image_format: str | None = None
    width: int | None = None
    height: int | None = None


class ColumnProfile(BaseModel):
    """A light profile of one extracted column, for header mapping and the validation report."""

    name: str
    non_empty: int
    distinct: int
    max_length: int
    samples: list[str] = Field(default_factory=list[str], max_length=5)


class ExtractionProblem(BaseModel):
    """A file- or row-level reading problem. Messages hold fixed text and the caller's values."""

    #: e.g. "too_many_rows", "not_utf8", "duplicate_header", "encrypted_pdf".
    code: str
    message: str
    #: 1-based data row (header excluded), when the problem is about one row.
    row: int | None = None


class ExtractionResult(BaseModel):
    extractor: str
    extractor_version: str
    status: ExtractionStatus
    metadata: FileMetadata | None = None
    #: The sheet the rows came from (XLSX).
    sheet: str | None = None
    columns: list[str] = Field(default_factory=list[str])
    #: Keys are exactly ``columns``, in order.
    rows: list[dict[str, Cell]] = Field(default_factory=list[dict[str, Cell]])
    profiles: list[ColumnProfile] = Field(default_factory=list[ColumnProfile])
    problems: list[ExtractionProblem] = Field(default_factory=list[ExtractionProblem])
    #: e.g. "content extraction stubbed (ADR-0008 decision 8)".
    notes: list[str] = Field(default_factory=list[str])


@runtime_checkable
class Extractor(Protocol):
    """A plugin that reads one kind of file. Pure: no ledger, no network, no global state."""

    #: Unique, e.g. "tabular", "pdf", "ocr".
    name: str
    #: Bump when the output for the same input changes.
    version: str

    def accepts(self, source: SourceFile) -> bool:
        """Whether this extractor reads this file (content type and the extension of filename)."""
        ...

    def extract(
        self, source: SourceFile, data: BinaryIO, options: Mapping[str, Any]
    ) -> ExtractionResult:
        """Read ``data`` (exactly ``source.size`` bytes) and return a result.

        Never raises for bad input: a bad file is ``status="failed"`` with problems. Options are
        extractor-specific and validated by the extractor (e.g. ``{"sheet": "Index",
        "header_row": 1}`` for the tabular extractor).
        """
        ...


# Pipeline-side signatures, implemented in WS-A and listed here so WS-B can test against them:
#   tl_core.derivation.registry.load_extractors() -> dict[str, Extractor]
#       Loads EXTRACTOR_ENTRY_POINT. A plugin that fails to load is an error at first use, never a
#       silent gap (the ADR-0010 decision 3 pattern).
#   tl_core.derivation.registry.choose(extractors, source, name: str | None) -> Extractor
#       An explicit name wins; otherwise the single extractor that accepts the source.
# WS-B ships each extractor as an entry point in its package's pyproject.toml, with a test that
# calls tests/contract/test_extractor_contract.py::check_extractor_contract against it.
