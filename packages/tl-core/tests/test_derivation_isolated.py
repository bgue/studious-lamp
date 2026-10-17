"""Running an extractor in a child process inside the resource envelope (FANOUT D9)."""

from __future__ import annotations

import hashlib
import multiprocessing
import time

import pytest
from tl_core.derivation.isolated import (
    DEFAULT_MEMORY_LIMIT_MB,
    DEFAULT_TIMEOUT_S,
    ExtractorSelectionError,
    run_isolated,
)
from tl_core.derivation.types import (
    EXTRACT_MAX_MEMORY_BYTES,
    EXTRACT_MAX_SECONDS,
    ExtractionProblem,
    ExtractionResult,
    SourceFile,
)

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


LIMIT_TEXT = "the extraction used more time or memory than the limit allows"


def only_problem(result: ExtractionResult) -> ExtractionProblem:
    assert result.status == "failed" and result.rows == []
    (problem,) = result.problems
    return problem


def assert_limit(result: ExtractionResult) -> None:
    problem = only_problem(result)
    assert (problem.code, problem.message) == ("extraction_limit", LIMIT_TEXT)
    assert multiprocessing.active_children() == []  # the child is gone, reaped


def test_a_stuck_extractor_is_killed_at_the_wall_clock_with_a_fixed_problem() -> None:
    started = time.monotonic()
    result = run_isolated(
        source("x.slow"), CSV, factory=FACTORY, name="slow", options={"seconds": 60}, timeout_s=2
    )
    assert time.monotonic() - started < 30
    assert_limit(result)


def test_a_process_that_dies_without_answering_is_a_limit_breach_not_a_hang() -> None:
    assert_limit(run_isolated(source("a.csv"), CSV, factory=FACTORY, name="dying", timeout_s=60))


def test_the_child_cannot_take_more_memory_than_its_limit() -> None:
    result = run_isolated(
        source("a.csv"), CSV, factory=FACTORY, name="greedy", memory_limit_mb=512, timeout_s=60
    )
    assert_limit(result)


def test_a_child_that_burns_cpu_is_stopped_and_reaped() -> None:
    started = time.monotonic()
    result = run_isolated(
        source("a.spin"), CSV, factory=FACTORY, name="spin", timeout_s=2, memory_limit_mb=512
    )
    assert time.monotonic() - started < 30
    assert_limit(result)


def test_a_result_over_the_cell_bound_is_a_contract_violation() -> None:
    result = run_isolated(source("a.big"), CSV, factory=FACTORY, name="oversized", timeout_s=60)
    problem = only_problem(result)
    assert problem.code == "contract_violation" and "cells" in problem.message


def test_the_limit_message_never_carries_a_path_or_a_trace() -> None:
    result = run_isolated(source("a.csv"), CSV, factory=FACTORY, name="dying", timeout_s=60)
    text = only_problem(result).message
    assert "/" not in text and "Traceback" not in text and "File" not in text


def test_the_production_defaults_are_the_contracts() -> None:
    assert DEFAULT_TIMEOUT_S == EXTRACT_MAX_SECONDS
    assert DEFAULT_MEMORY_LIMIT_MB * 1024 * 1024 == EXTRACT_MAX_MEMORY_BYTES


def test_the_next_call_works_after_every_kind_of_failure() -> None:
    for name, filename in (("dying", "a.csv"), ("greedy", "a.csv"), ("oversized", "a.big")):
        run_isolated(source(filename), CSV, factory=FACTORY, name=name, memory_limit_mb=512)
    ok = run_isolated(source("index.csv"), CSV, factory=FACTORY, name="fake")
    assert ok.status == "ok"


def test_no_extractor_for_the_file_is_raised_in_the_parent() -> None:
    with pytest.raises(ExtractorSelectionError) as caught:
        run_isolated(source("scan.pdf"), CSV, factory=FACTORY, name="nope")
    assert caught.value.kind == "NoExtractorError"
    assert "nope" in str(caught.value)
