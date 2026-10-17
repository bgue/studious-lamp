"""Run an extractor in a child process inside a resource envelope (ADR-0014; FANOUT D9).

An extractor reads a file a stranger may have made. A hostile PDF or spreadsheet can loop for
ever, eat all the memory, or crash a native library, and a reader cannot always bound that from the
inside. So a job runs the extractor here, in a process of its own, never in the worker's:

* the parent starts a fresh interpreter (``spawn``: nothing inherited, no database connection, no
  open files), sends it the source description, the options and the bytes over a pipe, and waits at
  most ``timeout_s`` seconds (default ``EXTRACT_MAX_SECONDS``). The child is given no path;
* the child limits its own address space (``RLIMIT_AS``, ``memory_limit_mb``, default
  ``EXTRACT_MAX_MEMORY_BYTES``) and its CPU time (``RLIMIT_CPU``, the wall clock rounded up), builds
  the extractors, calls :func:`tl_core.derivation.registry.run_extraction` and sends the result back
  as JSON;
* a breach (the wall clock, the memory limit, the CPU limit, a death by signal, an exit with no
  answer) is one ``failed`` result with the fixed problem ``extraction_limit`` and fixed text: no
  trace, no path, no detail. The child is killed (``SIGKILL`` after a short grace) and reaped;
* whatever comes back is parsed and checked against the contract again in the parent, because the
  child ran plugin code: shape, bounds (rows, columns, cell length, cells) and metadata.

No transaction is open while this runs (the job runner reads the bytes first, in a read-only unit
of work), so a stuck extractor never holds the writer lock. ``factory`` is for tests: a
``"module:callable"`` string, importable in the child, that returns the extractors by name instead
of the installed entry points. The limits are parameters so tests can use small ones; the defaults
are the contract's.
"""

from __future__ import annotations

import importlib
import io
import math
import multiprocessing
from collections.abc import Mapping
from multiprocessing.connection import Connection
from typing import Any

from pydantic import ValidationError

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
    EXTRACT_MAX_MEMORY_BYTES,
    EXTRACT_MAX_SECONDS,
    ExtractionProblem,
    ExtractionResult,
    Extractor,
    SourceFile,
)

DEFAULT_TIMEOUT_S = float(EXTRACT_MAX_SECONDS)
DEFAULT_MEMORY_LIMIT_MB = EXTRACT_MAX_MEMORY_BYTES // (1024 * 1024)
#: How long a child gets to leave after it is asked to, before it is killed.
KILL_GRACE_S = 1.0


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


def _limit_resources(megabytes: int | None, cpu_seconds: int | None) -> None:
    """Set the child's address-space and CPU limits (POSIX; a platform without them runs bare)."""
    try:
        import resource
    except ImportError:
        return
    for which, value in (
        (getattr(resource, "RLIMIT_AS", None), None if megabytes is None else megabytes * 1024**2),
        (getattr(resource, "RLIMIT_CPU", None), cpu_seconds),
    ):
        if which is None or value is None:
            continue
        try:
            resource.setrlimit(which, (value, value + 1 if which == resource.RLIMIT_CPU else value))
        except (ValueError, OSError):  # no limit is better than no extraction
            pass


def _extractors_from(factory: str | None) -> Mapping[str, Extractor]:
    if factory is None:
        return load_extractors()
    module_name, _, attribute = factory.partition(":")
    built: Any = getattr(importlib.import_module(module_name), attribute)()
    return built  # type: ignore[no-any-return]


def _child(
    conn: Connection, factory: str | None, memory_limit_mb: int | None, cpu_seconds: int | None
) -> None:
    """The child's whole life: receive, extract, answer, exit."""
    try:
        _limit_resources(memory_limit_mb, cpu_seconds)
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
        except MemoryError:  # building the extractors or the answer ran out of memory
            conn.send(("limit", "", ""))
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
    registry's exception). Everything else comes back as a result: a breach of the envelope is
    ``extraction_limit`` (see the module docstring), a result that breaks the contract is
    ``contract_violation``.
    """
    context = multiprocessing.get_context("spawn")
    parent, child_end = context.Pipe()
    cpu_seconds = max(1, math.ceil(timeout_s))
    process = context.Process(
        target=_child, args=(child_end, factory, memory_limit_mb, cpu_seconds), daemon=True
    )
    process.start()
    child_end.close()
    label = name or "extractor"
    limit = _failed(label, LIMIT_CODE, LIMIT_MESSAGE)
    try:
        parent.send(
            {"source": source.model_dump_json(), "name": name, "options": dict(options or {})}
        )
        parent.send_bytes(data)
        if not parent.poll(timeout_s):
            return limit
        try:
            kind, first, second = parent.recv()
        except (EOFError, OSError):  # died, was killed by a signal, or left without an answer
            return limit
    except (BrokenPipeError, OSError):
        return limit
    finally:
        parent.close()
        _reap(process)
    if kind == "limit":
        return limit
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


def _reap(process: Any) -> None:
    """Make sure the child is gone: let it leave, then ``SIGKILL``, then collect it."""
    process.join(KILL_GRACE_S if process.exitcode is None else 5)
    if process.is_alive():
        process.terminate()
        process.join(KILL_GRACE_S)
    if process.is_alive():
        process.kill()
        process.join()
