"""Conformance checks every extractor must pass (P1-I3 FANOUT; `tl_core.derivation.types`).

WS-B calls `check_extractor_contract(extractor, samples)` from each extractor's own tests. The
checks are about the shape and the bounds of a result, not about what a given file contains.
"""

from __future__ import annotations

import hashlib
import io
from collections.abc import Iterable

from tl_core.derivation import (
    MAX_CELL_CHARS,
    MAX_CELLS,
    MAX_COLUMNS,
    MAX_MESSAGE_CHARS,
    MAX_NAME_CHARS,
    MAX_NOTES,
    MAX_PROBLEMS,
    MAX_ROWS,
    MAX_SHEET_NAMES,
    MAX_TEXT_CHARS,
    ExtractionResult,
    Extractor,
    SourceFile,
)


def source_for(filename: str, content_type: str, data: bytes) -> SourceFile:
    return SourceFile(
        file_id="f-test",
        filename=filename,
        content_type=content_type,
        size=len(data),
        sha256=hashlib.sha256(data).hexdigest(),
        source_ref="src.doc.TEST-001@A",
    )


def check_result_shape(extractor: Extractor, source: SourceFile, result: ExtractionResult) -> None:
    assert result.extractor == extractor.name
    assert result.extractor_version == extractor.version
    if result.status in ("ok", "metadata_only"):
        assert result.metadata is not None
        assert result.metadata.sha256 == source.sha256
        assert result.metadata.size == source.size
    if result.status == "metadata_only":
        assert result.rows == []
        assert any("ADR-0008" in note for note in result.notes)
    if result.status == "failed":
        assert result.problems, "a failed result says why"
    assert len(result.columns) <= MAX_COLUMNS
    assert len(result.rows) <= MAX_ROWS
    assert len(set(result.columns)) == len(result.columns), "columns are unique"
    for row in result.rows:
        assert list(row) == result.columns, "every row has exactly the columns, in order"
        for value in row.values():
            assert value is None or (isinstance(value, str) and len(value) <= MAX_CELL_CHARS)
    assert len(result.rows) * len(result.columns) <= MAX_CELLS
    assert all(len(name) <= MAX_NAME_CHARS for name in result.columns)
    assert result.sheet is None or len(result.sheet) <= MAX_NAME_CHARS
    assert len(result.notes) <= MAX_NOTES
    assert all(len(note) <= MAX_TEXT_CHARS for note in result.notes)
    assert len(result.problems) <= MAX_PROBLEMS
    if result.metadata is not None:
        meta = result.metadata
        for text in (meta.title, meta.author, meta.created, meta.modified, meta.producer):
            assert text is None or len(text) <= MAX_TEXT_CHARS
        names = meta.sheet_names or []
        assert len(names) <= MAX_SHEET_NAMES
        assert all(len(name) <= MAX_NAME_CHARS for name in names)
    for problem in result.problems:
        assert len(problem.message) <= MAX_MESSAGE_CHARS
        assert "Traceback" not in problem.message
        assert "/home/" not in problem.message and "/tmp/" not in problem.message


def check_extractor_contract(
    extractor: Extractor, samples: Iterable[tuple[str, str, bytes]]
) -> None:
    """Run the extractor over (filename, content_type, data) samples and check every result."""
    assert isinstance(extractor, Extractor)
    assert extractor.name and extractor.version
    for filename, content_type, data in samples:
        source = source_for(filename, content_type, data)
        if not extractor.accepts(source):
            continue
        result = extractor.extract(source, io.BytesIO(data), {})
        check_result_shape(extractor, source, result)
    junk = b"\x00\xff" * 64
    garbage = source_for("garbage.bin", "application/octet-stream", junk)
    if extractor.accepts(garbage):
        result = extractor.extract(garbage, io.BytesIO(junk), {})
        check_result_shape(extractor, garbage, result)
        assert result.status in ("failed", "unsupported", "metadata_only")


def test_contract_types_import() -> None:
    assert MAX_ROWS > 0 and MAX_COLUMNS > 0
