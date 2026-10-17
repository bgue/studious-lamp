"""Run an extractor in a child process inside a resource envelope (ADR-0014; FANOUT D9, D10).

An extractor reads a file a stranger may have made. The pipeline never calls it in the worker: it
goes through :func:`tl_core.derivation.envelope.run_in_envelope` (a fresh interpreter, a scrubbed
environment, ``RLIMIT_AS`` and ``RLIMIT_CPU``, a wall clock, ``SIGKILL``, nothing unpickled). This
module is the extractor side of that:

* the parent sends the source description, the options, the name and the bytes; the child builds
  the extractors, calls :func:`tl_core.derivation.registry.run_extraction` and answers with the
  result as JSON bytes;
* a breach (the wall clock, memory, CPU, death by signal, exit with no answer, a limit that cannot
  be set) is one ``failed`` result with the fixed problem ``extraction_limit`` and fixed text: no
  trace, no path, no detail;
* the answer is parsed with pydantic and checked against the contract again in the parent, because
  the child ran plugin code: shape, bounds (rows, columns, cells, text) and metadata. An answer
  that is not valid JSON of an ``ExtractionResult``, or is larger than the cap, is a
  ``contract_violation``.

No transaction is open while this runs (the job runner reads the bytes first, in a read-only unit
of work), so a stuck extractor never holds the writer lock. ``factory`` is for tests: a
``"module:callable"`` string, importable in the child, that returns the extractors by name instead
of the installed entry points. The limits are parameters so tests can use small ones; the defaults
are the contract's.
"""

from __future__ import annotations

import importlib
import io
import json
from collections.abc import Mapping
from typing import Any, cast

from pydantic import ValidationError

from tl_core.derivation.envelope import (
    DEFAULT_MEMORY_LIMIT_MB,
    DEFAULT_TIMEOUT_S,
    MAX_ANSWER_BYTES,
    Breach,
    run_in_envelope,
)
from tl_core.derivation.registry import (
    LIMIT_CODE,
    LIMIT_MESSAGE,
    AmbiguousExtractorError,
    ExtractorLoadError,
    NoExtractorError,
    contract_problem,
    load_extractors,
    run_extraction,
)
from tl_core.derivation.types import (
    Cell,
    ExtractionProblem,
    ExtractionResult,
    Extractor,
    SourceFile,
)

ENTRY = "tl_core.derivation.isolated:extract_entry"
TAG_RESULT = b"R"
TAG_SELECTION = b"S"

__all__ = [
    "DEFAULT_MEMORY_LIMIT_MB",
    "DEFAULT_TIMEOUT_S",
    "ExtractorSelectionError",
    "run_isolated",
]


class ExtractorSelectionError(LookupError):
    """No extractor fits, or several do, or a plugin is broken: the child said so."""

    def __init__(self, kind: str, message: str) -> None:
        super().__init__(message)
        self.kind = kind


class _Named:
    """Just enough of an extractor for ``contract_problem`` on the parent's side."""

    def __init__(self, result: ExtractionResult) -> None:
        self.name = result.extractor
        self.version = result.extractor_version


def _failed(source_name: str, code: str, message: str) -> ExtractionResult:
    return ExtractionResult(
        extractor=source_name,
        extractor_version="",
        status="failed",
        problems=[ExtractionProblem(code=code, message=message)],
    )


def _extractors_from(factory: str | None) -> Mapping[str, Extractor]:
    if factory is None:
        return load_extractors()
    module_name, _, attribute = factory.partition(":")
    built: Any = getattr(importlib.import_module(module_name), attribute)()
    return built  # type: ignore[no-any-return]


def _wire(result: ExtractionResult) -> bytes:
    """The result as JSON with each row a list in column order: no column name is repeated per row,
    so a table is about as large on the wire as the text in it."""
    body = result.model_dump(mode="json")
    body["rows"] = [list(row.values()) for row in result.rows]
    return json.dumps(body, ensure_ascii=False, separators=(",", ":")).encode()


def _unwire(payload: bytes) -> ExtractionResult:
    """Parse the child's answer. Raises ``ValueError`` for anything that is not a result.

    The result is validated without its rows first; the rows are checked to be lists of exactly
    as many cells as there are columns (a text or ``null`` each), and only then rebuilt as dicts.
    """
    loaded: Any = json.loads(payload)
    if not isinstance(loaded, dict):
        raise ValueError("not an object")
    body = cast(dict[str, Any], loaded)
    raw_rows: Any = body.pop("rows", [])
    if not isinstance(raw_rows, list):
        raise ValueError("rows is not a list")
    result = ExtractionResult.model_validate(body)
    width = len(result.columns)
    rows: list[dict[str, Cell]] = []
    for row in cast(list[Any], raw_rows):
        if not isinstance(row, list) or len(cast(list[Any], row)) != width:
            raise ValueError("a row is not a list of one cell per column")
        cells = cast(list[Any], row)
        if any(cell is not None and not isinstance(cell, str) for cell in cells):
            raise ValueError("a cell is not text or null")
        rows.append(dict(zip(result.columns, cast(list[Cell], cells), strict=True)))
    result.rows = rows
    return result


def extract_entry(header: Mapping[str, Any], data: bytes) -> tuple[bytes, bytes]:
    """What the child runs: choose an extractor, call it, answer with the result as JSON."""
    source = SourceFile.model_validate_json(header["source"])
    try:
        result = run_extraction(
            _extractors_from(header["factory"]),
            source,
            io.BytesIO(data),
            name=header["name"],
            options=header["options"],
        )
    except (NoExtractorError, AmbiguousExtractorError, ExtractorLoadError) as exc:
        return TAG_SELECTION, json.dumps({"kind": type(exc).__name__, "message": str(exc)}).encode()
    return TAG_RESULT, _wire(result)


def run_isolated(
    source: SourceFile,
    data: bytes,
    *,
    name: str | None = None,
    options: Mapping[str, Any] | None = None,
    timeout_s: float = DEFAULT_TIMEOUT_S,
    memory_limit_mb: int | None = DEFAULT_MEMORY_LIMIT_MB,
    factory: str | None = None,
    max_answer: int = MAX_ANSWER_BYTES,
    _entry: str = ENTRY,
) -> ExtractionResult:
    """Extract ``data`` in a child process and return a result that keeps the contract.

    Raises :class:`ExtractorSelectionError` when no extractor fits (``kind`` is the name of the
    registry's exception). Everything else comes back as a result: a breach of the envelope is
    ``extraction_limit``, an answer that is too large, unreadable or breaks the contract is
    ``contract_violation``. (``_entry`` is for the tests of the parent's side only.)
    """
    label = name or "extractor"
    header = {
        "source": source.model_dump_json(),
        "name": name,
        "options": dict(options or {}),
        "factory": factory,
    }
    try:
        answer = run_in_envelope(
            _entry,
            header,
            data,
            timeout_s=timeout_s,
            memory_limit_mb=memory_limit_mb,
            max_answer=max_answer,
        )
    except Breach as breach:
        if breach.reason == "too_large":
            return _failed(label, "contract_violation", "the result is too large")
        return _failed(label, LIMIT_CODE, LIMIT_MESSAGE)
    if answer.tag == TAG_SELECTION:
        try:
            said = json.loads(answer.payload)
            kind, message = str(said["kind"])[:100], str(said["message"])[:300]
        except (ValueError, KeyError, TypeError):
            return _failed(label, "contract_violation", "the answer is not understood")
        raise ExtractorSelectionError(kind, message)
    if answer.tag != TAG_RESULT:
        return _failed(label, "contract_violation", "the answer is not understood")
    try:
        result = _unwire(answer.payload)
    except (ValidationError, ValueError):
        return _failed(label, "contract_violation", "the result is not an ExtractionResult")
    broken = contract_problem(_Named(result), source, result)  # type: ignore[arg-type]
    if broken is not None:
        return _failed(result.extractor, "contract_violation", broken)
    return result
