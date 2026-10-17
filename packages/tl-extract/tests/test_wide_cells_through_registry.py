"""A legal wide cell goes through the real tabular extractor and the registry's checks.

The security re-review of b5f5d41 found the parent bounding a profile sample at ``MAX_TEXT_CHARS``
(1 000), so a cell of 5 000 characters, legal under ``MAX_CELL_CHARS`` (10 000), failed extraction.
A profile sample is a cell, so it is bounded as a cell is.
"""

from __future__ import annotations

import io

from extractsupport import source_for
from tl_core.derivation import MAX_CELL_CHARS, ExtractionResult
from tl_core.derivation.isolated import run_isolated
from tl_core.derivation.registry import run_extraction
from tl_extract.tabular import TabularExtractor


def csv_with(width: int) -> bytes:
    return f"tag,remarks\n47-FV-1001,{'r' * width}\n47-FV-1002,short\n".encode()


def check(result: ExtractionResult, width: int) -> None:
    assert result.status == "ok" and result.problems == []
    assert result.rows[0]["remarks"] == "r" * width
    (remarks,) = [p for p in result.profiles if p.name == "remarks"]
    assert remarks.max_length == width
    assert "r" * width in remarks.samples


def test_a_five_thousand_character_cell_extracts_in_process() -> None:
    data = csv_with(5000)
    result = run_extraction(
        {"tabular": TabularExtractor()}, source_for("wide.csv", "text/csv", data), io.BytesIO(data)
    )
    check(result, 5000)


def test_a_five_thousand_character_cell_extracts_in_the_envelope() -> None:
    data = csv_with(5000)
    check(run_isolated(source_for("wide.csv", "text/csv", data), data, timeout_s=60), 5000)


def test_a_cell_of_exactly_the_bound_passes_and_one_more_is_refused_by_the_extractor() -> None:
    data = csv_with(MAX_CELL_CHARS)
    check(
        run_isolated(source_for("wide.csv", "text/csv", data), data, timeout_s=60), MAX_CELL_CHARS
    )
    over = csv_with(MAX_CELL_CHARS + 1)
    refused = run_isolated(source_for("wide.csv", "text/csv", over), over, timeout_s=60)
    assert refused.status == "failed" and refused.rows == []
