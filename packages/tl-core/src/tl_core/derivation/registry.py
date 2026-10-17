"""The extractor registry and the guarded call of a plugin (brief 9 M1; P1-I3 T03).

Extractors are plugins found through the entry-point group ``throughline.extractors`` (the
contract: ``tl_core.derivation.types``). Each entry point names a zero-argument callable that
returns an object satisfying ``Extractor``. The pipeline never imports a plugin package by name.

* :func:`load_extractors` reads the group once per process and fails loud: a plugin that does not
  import, does not return an ``Extractor`` or is named differently from its entry point raises
  :class:`ExtractorLoadError` at first use, never a silent gap (the ADR-0010 pattern).
* :func:`choose` picks the extractor for a source: an explicit name wins, otherwise the single
  extractor that accepts the source.
* :func:`run_extraction` calls a plugin and does not trust it: it refuses a source over the size
  bound, turns an exception into a failed result, and refuses a result that breaks the contract
  (bounds, shape) by returning a failed result instead of passing the rows on.

STUB (P1-I3-T03): the bodies of ``_discover``, ``load_extractors``, ``choose``,
``contract_problem`` and ``run_extraction`` raise NotImplementedError; everything else is final.
Each body has a STEPS comment. Implement them, then delete this paragraph, the STEPS comments, the
``ruff: noqa`` line and the ``pyright`` line below.
"""

# ruff: noqa: F401 -- STUB: these imports are used once the bodies are written
# pyright: reportUnusedImport=false, reportUnusedFunction=false

from __future__ import annotations

import threading
from collections.abc import Generator, Mapping
from contextlib import contextmanager
from importlib.metadata import entry_points
from typing import Any, BinaryIO

from tl_core.derivation.types import (
    EXTRACTOR_ENTRY_POINT,
    MAX_CELL_CHARS,
    MAX_COLUMNS,
    MAX_ROWS,
    MAX_SOURCE_BYTES,
    ExtractionProblem,
    ExtractionResult,
    Extractor,
    SourceFile,
)


class ExtractorLoadError(RuntimeError):
    """An installed extractor plugin could not be loaded, or two plugins claim one name."""


class NoExtractorError(LookupError):
    """No extractor fits: none has the given name, or none accepts the source."""


class AmbiguousExtractorError(LookupError):
    """More than one extractor accepts the source and no name was given."""


_lock = threading.Lock()
_override: dict[str, Extractor] | None = None
_loaded: dict[str, Extractor] | None = None


def _discover() -> dict[str, Extractor]:
    """Read the entry points of the group and build the extractors by name."""
    # STEPS
    # 1. found: dict[str, Extractor] = {}.
    # 2. For each `entry` in `entry_points(group=EXTRACTOR_ENTRY_POINT)` sorted by `entry.name`
    #    (call `entry_points` through the module-level name: the tests replace it):
    #    a. `produced = entry.load()()` inside try/except Exception as exc: raise
    #       ExtractorLoadError(f"extractor {entry.name!r} cannot be loaded: "
    #       f"{type(exc).__name__}: {exc}") from exc.
    #    b. If `not isinstance(produced, Extractor)`: raise ExtractorLoadError(f"extractor
    #       {entry.name!r}: its entry point must return an Extractor").
    #    c. If `produced.name != entry.name`: raise ExtractorLoadError(f"extractor entry point
    #       {entry.name!r} returned an extractor named {produced.name!r}").
    #    d. If `entry.name in found`: raise ExtractorLoadError(f"extractor {entry.name!r} is
    #       declared twice").
    #    e. found[entry.name] = produced.
    # 3. Return found.
    raise NotImplementedError


def load_extractors() -> dict[str, Extractor]:
    """The installed extractors by name, sorted by name. Discovered once per process.

    Raises :class:`ExtractorLoadError` when a plugin is broken (see the module docstring).
    """
    # STEPS
    # 1. `global _loaded`; `with _lock:`.
    # 2. If `_override is not None`: return dict(_override).
    # 3. If `_loaded is None`: `_loaded = _discover()` (a failure leaves `_loaded` None, so the
    #    next call raises again instead of returning an empty registry).
    # 4. Return dict(_loaded).
    raise NotImplementedError


@contextmanager
def use_extractors(extractors: Mapping[str, Extractor]) -> Generator[None]:
    """Install ``extractors`` as the only ones for the block (tests and embedders)."""
    global _override
    with _lock:
        previous, _override = _override, dict(extractors)
    try:
        yield
    finally:
        with _lock:
            _override = previous


def forget_loaded() -> None:
    """Drop the discovered extractors; the next ``load_extractors`` reads the entry points."""
    global _loaded
    with _lock:
        _loaded = None


def choose(
    extractors: Mapping[str, Extractor], source: SourceFile, name: str | None = None
) -> Extractor:
    """The extractor to use for ``source``.

    An explicit ``name`` wins, whether or not that extractor would accept the source (it answers
    ``unsupported`` itself). Without a name the single extractor whose ``accepts`` is true is
    used. Raises :class:`NoExtractorError` (unknown name, or none accepts) and
    :class:`AmbiguousExtractorError` (several accept; the message names them).
    """
    # STEPS
    # 1. If `name is not None`: `found = extractors.get(name)`; if None raise NoExtractorError(
    #    f"no extractor named {name!r} (known: {known})") where known is the names sorted and
    #    joined by ", ", or "none installed" when there are none; else return found.
    # 2. accepting: list[Extractor] = []; for each extractor in name order (`sorted(extractors)`):
    #    call `candidate.accepts(source)` inside try/except Exception as exc: raise
    #    ExtractorLoadError(f"extractor {candidate.name!r} failed in accepts: "
    #    f"{type(exc).__name__}") from exc; append the ones that return true.
    # 3. None accept: raise NoExtractorError(f"no extractor accepts {source.filename!r} "
    #    f"({source.content_type})").
    # 4. Several accept: raise AmbiguousExtractorError(f"several extractors accept "
    #    f"{source.filename!r}: {names}; name one") with names joined by ", ".
    # 5. Return the one.
    raise NotImplementedError


def _opaque(value: object) -> object:
    """``value`` typed as unknown: a plugin's answer is checked, not believed."""
    return value


def _failed(extractor: Extractor, code: str, message: str) -> ExtractionResult:
    return ExtractionResult(
        extractor=extractor.name,
        extractor_version=extractor.version,
        status="failed",
        problems=[ExtractionProblem(code=code, message=message)],
    )


def contract_problem(
    extractor: Extractor, source: SourceFile, result: ExtractionResult
) -> str | None:
    """Why ``result`` breaks the extractor contract, or ``None`` when it keeps it.

    The checks are the bounds and the shape of ``tests/contract/test_extractor_contract.py``: the
    names match, metadata matches the source, a metadata-only result has no rows, columns and rows
    stay inside the bounds, every row has exactly the columns, no cell is longer than the bound.
    """
    # STEPS (check in this order; return the first message that applies, else None)
    # 1. `result.extractor != extractor.name or result.extractor_version != extractor.version`:
    #    "the result names another extractor or version".
    # 2. status "ok" or "metadata_only": `result.metadata is None`: "the result has no file
    #    metadata"; its `sha256` or `size` differs from the source's: "the file metadata does
    #    not match the source".
    # 3. status "metadata_only" with rows: "a metadata-only result must have no rows".
    # 4. `len(result.columns) > MAX_COLUMNS`: f"more than {MAX_COLUMNS} columns".
    # 5. Duplicate column names: "the column names are not unique".
    # 6. `len(result.rows) > MAX_ROWS`: f"more than {MAX_ROWS} rows".
    # 7. For each row: `list(row) != result.columns`: "a row does not have exactly the columns,
    #    in order"; a cell that is not None and longer than MAX_CELL_CHARS: f"a cell is longer
    #    than {MAX_CELL_CHARS} characters".
    raise NotImplementedError


def run_extraction(
    extractors: Mapping[str, Extractor],
    source: SourceFile,
    data: BinaryIO,
    *,
    name: str | None = None,
    options: Mapping[str, Any] | None = None,
) -> ExtractionResult:
    """Choose an extractor, call it, and return a result that keeps the contract.

    Raises what :func:`choose` raises. Everything else comes back as a result: a source over
    ``MAX_SOURCE_BYTES`` is ``failed`` with the problem ``source_too_large`` (the extractor is not
    called); an exception in the plugin is ``failed`` with ``extractor_crashed`` (the message holds
    the exception type, never its text, a trace or a path); a result that breaks the contract is
    ``failed`` with ``contract_violation`` and the rule broken. The caller's ``options`` are copied.
    """
    # STEPS
    # 1. `extractor = choose(extractors, source, name)` (its errors propagate).
    # 2. If `source.size > MAX_SOURCE_BYTES`: return _failed(extractor, "source_too_large",
    #    f"the file is {source.size} bytes; the limit is {MAX_SOURCE_BYTES}"). The plugin is not
    #    called.
    # 3. In try/except Exception as exc: `produced = _opaque(extractor.extract(source, data,
    #    dict(options or {})))`. On an exception return _failed(extractor, "extractor_crashed",
    #    f"extractor {extractor.name} failed: {type(exc).__name__}"): never the text of `exc`.
    # 4. If `not isinstance(produced, ExtractionResult)`: return _failed(extractor,
    #    "contract_violation", "the result is not an ExtractionResult").
    # 5. `broken = contract_problem(extractor, source, produced)`; if not None return
    #    _failed(extractor, "contract_violation", broken).
    # 6. Return `produced` unchanged (a "failed" result of the plugin passes through as it is).
    raise NotImplementedError
