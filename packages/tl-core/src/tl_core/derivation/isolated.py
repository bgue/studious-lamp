"""Run an extractor in a child process under a wall-clock limit (ADR-0014; P1-I3 security).

An extractor reads a file a stranger may have made. It cannot be trusted to return: a hostile PDF
or spreadsheet can loop for ever, and a thread cannot be stopped. So a job runs the extractor here:

* the parent starts a fresh interpreter (``spawn``, nothing inherited), sends it the source
  description, the options and the bytes over a pipe, and waits at most ``timeout_s`` seconds for
  the result;
* the child limits its own address space (``memory_limit_mb``), builds the extractors, calls
  :func:`tl_core.derivation.registry.run_extraction` and sends the result back as JSON;
* on timeout the parent kills the child and returns a ``failed`` result with the fixed problem
  ``timeout`` ("extraction timed out after N s"); a child that dies returns ``extractor_crashed``;
* whatever comes back is parsed and checked against the contract again in the parent, because the
  child ran plugin code.

No transaction is open while this runs (the job runner reads the bytes first, in a read-only unit
of work), so a stuck extractor never holds the writer lock. ``factory`` is for tests: a
``"module:callable"`` string, importable in the child, that returns the extractors by name instead
of the installed entry points.
"""

from __future__ import annotations

import importlib
import io
import multiprocessing
from collections.abc import Mapping
from multiprocessing.connection import Connection
from typing import Any

from pydantic import ValidationError

from tl_core.derivation.registry import (
    AmbiguousExtractorError,
    ExtractorLoadError,
    NoExtractorError,
    contract_problem,
    load_extractors,
    run_extraction,
)
from tl_core.derivation.types import (
    ExtractionProblem,
    ExtractionResult,
    Extractor,
    SourceFile,
)

DEFAULT_TIMEOUT_S = 60.0
DEFAULT_MEMORY_LIMIT_MB = 2048


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


def _limit_memory(megabytes: int | None) -> None:
    if megabytes is None:
        return
    try:
        import resource

        limit = megabytes * 1024 * 1024
        resource.setrlimit(resource.RLIMIT_AS, (limit, limit))
    except (ImportError, ValueError, OSError):  # no limit is better than no extraction
        pass


def _extractors_from(factory: str | None) -> Mapping[str, Extractor]:
    if factory is None:
        return load_extractors()
    module_name, _, attribute = factory.partition(":")
    built: Any = getattr(importlib.import_module(module_name), attribute)()
    return built  # type: ignore[no-any-return]


def _child(conn: Connection, factory: str | None, memory_limit_mb: int | None) -> None:
    """The child's whole life: receive, extract, answer, exit."""
    try:
        _limit_memory(memory_limit_mb)
        header = conn.recv()
        data = conn.recv_bytes()
        source = SourceFile.model_validate_json(header["source"])
        try:
            result = run_extraction(
                _extractors_from(factory),
                source,
                io.BytesIO(data),
                name=header["name"],
                options=header["options"],
            )
        except (NoExtractorError, AmbiguousExtractorError, ExtractorLoadError) as exc:
            conn.send(("selection", type(exc).__name__, str(exc)))
            return
        conn.send(("result", result.model_dump_json(), ""))
    finally:
        conn.close()


def run_isolated(
    source: SourceFile,
    data: bytes,
    *,
    name: str | None = None,
    options: Mapping[str, Any] | None = None,
    timeout_s: float = DEFAULT_TIMEOUT_S,
    memory_limit_mb: int | None = DEFAULT_MEMORY_LIMIT_MB,
    factory: str | None = None,
) -> ExtractionResult:
    """Extract ``data`` in a child process and return a result that keeps the contract.

    Raises :class:`ExtractorSelectionError` when no extractor fits (``kind`` is the name of the
    registry's exception). Everything else comes back as a result: ``timeout``,
    ``extractor_crashed``, ``contract_violation`` (see the module docstring).
    """
    context = multiprocessing.get_context("spawn")
    parent, child_end = context.Pipe()
    process = context.Process(
        target=_child, args=(child_end, factory, memory_limit_mb), daemon=True
    )
    process.start()
    child_end.close()
    label = name or "extractor"
    try:
        parent.send(
            {"source": source.model_dump_json(), "name": name, "options": dict(options or {})}
        )
        parent.send_bytes(data)
        if not parent.poll(timeout_s):
            process.kill()
            return _failed(label, "timeout", f"extraction timed out after {timeout_s:g} s")
        try:
            kind, first, second = parent.recv()
        except (EOFError, OSError):
            return _failed(
                label, "extractor_crashed", "the extractor process ended without an answer"
            )
    except (BrokenPipeError, OSError):
        return _failed(label, "extractor_crashed", "the extractor process ended without an answer")
    finally:
        parent.close()
        process.join(5)
        if process.is_alive():
            process.kill()
            process.join()
    if kind == "selection":
        raise ExtractorSelectionError(first, second)
    try:
        result = ExtractionResult.model_validate_json(first)
    except ValidationError:
        return _failed(label, "contract_violation", "the result is not an ExtractionResult")
    broken = contract_problem(_Named(result), source, result)  # type: ignore[arg-type]
    if broken is not None:
        return _failed(result.extractor, "contract_violation", broken)
    return result
