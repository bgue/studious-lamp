"""Running an extractor in a child process under a wall-clock limit (P1-I3 security)."""

from __future__ import annotations

import hashlib
import time

import pytest
from tl_core.derivation.isolated import ExtractorSelectionError, run_isolated
from tl_core.derivation.types import SourceFile

FACTORY = "tl_core.derivation.testing:make_extractors"
CSV = b"tag,service\n47-FV-1001,Feed\n"


def source(filename: str, data: bytes = CSV) -> SourceFile:
    return SourceFile(
        file_id="f1",
        filename=filename,
        content_type="text/csv",
        size=len(data),
        sha256=hashlib.sha256(data).hexdigest(),
        source_ref="src.doc.ISD-001@A",
    )


def test_an_extractor_runs_in_a_child_and_its_result_comes_back() -> None:
    result = run_isolated(source("index.csv"), CSV, factory=FACTORY, name="fake", timeout_s=60)
    assert result.status == "ok" and result.rows == [{"tag": "47-FV-1001", "service": "Feed"}]
    assert result.extractor == "fake"


def test_the_options_reach_the_extractor() -> None:
    data = b"a,b\n1,2\n"
    result = run_isolated(
        source("x.slow", data), data, factory=FACTORY, name="slow", options={"seconds": 0.01}
    )
    assert result.status == "ok" and result.extractor == "slow"


def test_a_stuck_extractor_is_abandoned_at_the_limit_with_a_fixed_problem() -> None:
    started = time.monotonic()
    result = run_isolated(
        source("x.slow"), CSV, factory=FACTORY, name="slow", options={"seconds": 60}, timeout_s=3
    )
    assert time.monotonic() - started < 30
    assert result.status == "failed" and result.rows == []
    (problem,) = result.problems
    assert problem.code == "timeout" and problem.message == "extraction timed out after 3 s"


def test_a_process_that_dies_without_answering_is_a_crash_not_a_hang() -> None:
    result = run_isolated(source("a.csv"), CSV, factory=FACTORY, name="dying", timeout_s=60)
    assert result.status == "failed"
    assert result.problems[0].code == "extractor_crashed"


def test_the_child_cannot_take_more_memory_than_its_limit() -> None:
    result = run_isolated(
        source("a.csv"), CSV, factory=FACTORY, name="greedy", memory_limit_mb=512, timeout_s=60
    )
    assert result.status == "failed"
    assert result.problems[0].code == "extractor_crashed"


def test_no_extractor_for_the_file_is_raised_in_the_parent() -> None:
    with pytest.raises(ExtractorSelectionError) as caught:
        run_isolated(source("scan.pdf"), CSV, factory=FACTORY, name="nope")
    assert caught.value.kind == "NoExtractorError"
    assert "nope" in str(caught.value)
