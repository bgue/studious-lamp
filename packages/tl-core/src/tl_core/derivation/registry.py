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
"""

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
    found: dict[str, Extractor] = {}
    for entry in sorted(entry_points(group=EXTRACTOR_ENTRY_POINT), key=lambda e: e.name):
        try:
            produced = entry.load()()
        except Exception as exc:
            raise ExtractorLoadError(
                f"extractor {entry.name!r} cannot be loaded: {type(exc).__name__}: {exc}"
            ) from exc
        if not isinstance(produced, Extractor):
            raise ExtractorLoadError(
                f"extractor {entry.name!r}: its entry point must return an Extractor"
            )
        if produced.name != entry.name:
            raise ExtractorLoadError(
                f"extractor entry point {entry.name!r} returned an extractor named "
                f"{produced.name!r}"
            )
        if entry.name in found:
            raise ExtractorLoadError(f"extractor {entry.name!r} is declared twice")
        found[entry.name] = produced
    return found


def load_extractors() -> dict[str, Extractor]:
    """The installed extractors by name, sorted by name. Discovered once per process.

    Raises :class:`ExtractorLoadError` when a plugin is broken (see the module docstring).
    """
    global _loaded
    with _lock:
        if _override is not None:
            return dict(_override)
        if _loaded is None:
            # A failure raises here and leaves `_loaded` None, so the next call raises again
            # instead of returning an empty registry.
            _loaded = _discover()
        return dict(_loaded)


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
    if name is not None:
        found = extractors.get(name)
        if found is None:
            known = ", ".join(sorted(extractors)) or "none installed"
            raise NoExtractorError(f"no extractor named {name!r} (known: {known})")
        return found
    accepting: list[Extractor] = []
    for key in sorted(extractors):
        candidate = extractors[key]
        try:
            takes = candidate.accepts(source)
        except Exception as exc:
            raise ExtractorLoadError(
                f"extractor {candidate.name!r} failed in accepts: {type(exc).__name__}"
            ) from exc
        if takes:
            accepting.append(candidate)
    if not accepting:
        raise NoExtractorError(f"no extractor accepts {source.filename!r} ({source.content_type})")
    if len(accepting) > 1:
        names = ", ".join(candidate.name for candidate in accepting)
        raise AmbiguousExtractorError(
            f"several extractors accept {source.filename!r}: {names}; name one"
        )
    return accepting[0]


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
    if result.extractor != extractor.name or result.extractor_version != extractor.version:
        return "the result names another extractor or version"
    if result.status in ("ok", "metadata_only"):
        if result.metadata is None:
            return "the result has no file metadata"
        if result.metadata.sha256 != source.sha256 or result.metadata.size != source.size:
            return "the file metadata does not match the source"
    if result.status == "metadata_only" and result.rows:
        return "a metadata-only result must have no rows"
    if len(result.columns) > MAX_COLUMNS:
        return f"more than {MAX_COLUMNS} columns"
    if len(set(result.columns)) != len(result.columns):
        return "the column names are not unique"
    if len(result.rows) > MAX_ROWS:
        return f"more than {MAX_ROWS} rows"
    for row in result.rows:
        if list(row) != result.columns:
            return "a row does not have exactly the columns, in order"
        for cell in row.values():
            if cell is not None and len(cell) > MAX_CELL_CHARS:
                return f"a cell is longer than {MAX_CELL_CHARS} characters"
    return None


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
    extractor = choose(extractors, source, name)
    if source.size > MAX_SOURCE_BYTES:
        return _failed(
            extractor,
            "source_too_large",
            f"the file is {source.size} bytes; the limit is {MAX_SOURCE_BYTES}",
        )
    try:
        produced = _opaque(extractor.extract(source, data, dict(options or {})))
    except Exception as exc:
        return _failed(
            extractor,
            "extractor_crashed",
            f"extractor {extractor.name} failed: {type(exc).__name__}",
        )
    if not isinstance(produced, ExtractionResult):
        return _failed(extractor, "contract_violation", "the result is not an ExtractionResult")
    broken = contract_problem(extractor, source, produced)
    if broken is not None:
        return _failed(extractor, "contract_violation", broken)
    return produced
