"""Running an extractor in a child process inside the resource envelope (FANOUT D9)."""

from __future__ import annotations

import hashlib
import subprocess
import time
from pathlib import Path
from typing import Any

import pytest
from tl_core.derivation import envelope
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


@pytest.fixture
def children(monkeypatch: pytest.MonkeyPatch) -> list[subprocess.Popen[Any]]:
    """Every child process the envelope starts, so a test can see that it is gone."""
    started: list[subprocess.Popen[Any]] = []
    real = subprocess.Popen

    def recording(*args: Any, **kwargs: Any) -> subprocess.Popen[Any]:
        process = real(*args, **kwargs)
        started.append(process)
        return process

    monkeypatch.setattr(subprocess, "Popen", recording)
    return started


def only_problem(result: ExtractionResult) -> ExtractionProblem:
    assert result.status == "failed" and result.rows == []
    (problem,) = result.problems
    return problem


def assert_limit(result: ExtractionResult, children: list[subprocess.Popen[Any]]) -> None:
    problem = only_problem(result)
    assert (problem.code, problem.message) == ("extraction_limit", LIMIT_TEXT)
    assert children and all(c.poll() is not None for c in children)  # the child is gone, reaped


def test_a_stuck_extractor_is_killed_at_the_wall_clock_with_a_fixed_problem(
    children: list[subprocess.Popen[Any]],
) -> None:
    started = time.monotonic()
    result = run_isolated(
        source("x.slow"), CSV, factory=FACTORY, name="slow", options={"seconds": 60}, timeout_s=2
    )
    assert time.monotonic() - started < 30
    assert_limit(result, children)


def test_a_process_that_dies_without_answering_is_a_limit_breach_not_a_hang(
    children: list[subprocess.Popen[Any]],
) -> None:
    result = run_isolated(source("a.csv"), CSV, factory=FACTORY, name="dying", timeout_s=60)
    assert_limit(result, children)


def test_the_child_cannot_take_more_memory_than_its_limit(
    children: list[subprocess.Popen[Any]],
) -> None:
    result = run_isolated(
        source("a.csv"), CSV, factory=FACTORY, name="greedy", memory_limit_mb=512, timeout_s=60
    )
    assert_limit(result, children)


def test_a_child_that_burns_cpu_is_stopped_and_reaped(
    children: list[subprocess.Popen[Any]],
) -> None:
    started = time.monotonic()
    result = run_isolated(
        source("a.spin"), CSV, factory=FACTORY, name="spin", timeout_s=2, memory_limit_mb=512
    )
    assert time.monotonic() - started < 30
    assert_limit(result, children)


def test_a_limit_that_cannot_be_set_fails_the_call_instead_of_running_without_it(
    children: list[subprocess.Popen[Any]],
) -> None:
    result = run_isolated(
        source("a.csv"), CSV, factory=FACTORY, name="fake", memory_limit_mb=2**50, timeout_s=60
    )
    assert_limit(result, children)


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


def test_nothing_the_child_sends_is_unpickled(tmp_path: Path) -> None:
    marker = tmp_path / "executed"
    result = run_isolated(
        source("a.csv"),
        CSV,
        options={"marker": str(marker)},
        _entry="tl_core.derivation.testing:hostile_pickle_entry",
    )
    assert not marker.exists()  # the parent did not run what the pickle asked for
    assert only_problem(result).code == "contract_violation"


def test_an_answer_over_the_cap_is_refused_before_it_is_read() -> None:
    result = run_isolated(
        source("a.csv"),
        CSV,
        max_answer=1000,
        _entry="tl_core.derivation.testing:big_answer_entry",
    )
    problem = only_problem(result)
    assert (problem.code, problem.message) == ("contract_violation", "the result is too large")


def test_the_child_sees_a_scrubbed_environment_and_few_descriptors(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("TL_OBJECT_SECRET", "do-not-leak")
    monkeypatch.setenv("TL_DB", "postgresql://u:p@host/db")
    monkeypatch.setenv("TL_SESSION_FILE", "/home/x/session.json")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "do-not-leak")
    result = run_isolated(source("a.env"), CSV, factory=FACTORY, name="env", timeout_s=60)
    assert result.status == "metadata_only"
    names, descriptors = result.notes
    seen = set(filter(None, names.split(",")))
    assert seen <= set(envelope.ENV_ALLOWED) | {"LC_CTYPE"}  # python may set the coercion variable
    assert not any(n.startswith(("TL_", "AWS_")) for n in seen)
    assert "do-not-leak" not in names
    assert len([d for d in descriptors.split(",") if d]) <= 6  # stdin, stdout, stderr, the answer


def test_the_environment_scrubber_keeps_only_what_the_interpreter_needs() -> None:
    kept = envelope.scrubbed_environment(
        {"PATH": "/bin", "PYTHONPATH": "/x", "LANG": "C", "TL_DB": "x", "HOME": "/root", "A": "b"}
    )
    assert kept == {"PATH": "/bin", "PYTHONPATH": "/x", "LANG": "C"}


def test_no_extractor_for_the_file_is_raised_in_the_parent() -> None:
    with pytest.raises(ExtractorSelectionError) as caught:
        run_isolated(source("scan.pdf"), CSV, factory=FACTORY, name="nope")
    assert caught.value.kind == "NoExtractorError"
    assert "nope" in str(caught.value)


def test_the_workers_current_directory_is_not_on_the_childs_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A file named like a standard module in the cwd must not run in the child (``-P``)."""
    marker = tmp_path / "ran"
    (tmp_path / "json.py").write_text(f"open({str(marker)!r}, 'w').write('shadowed')\n")
    monkeypatch.chdir(tmp_path)
    result = run_isolated(source("a.csv"), CSV, factory=FACTORY, name="fake", timeout_s=60)
    assert result.status == "ok"
    assert not marker.exists()


def _alive(pid: int) -> bool:
    try:
        state = Path(f"/proc/{pid}/stat").read_text().rsplit(")", 1)[1].split()[0]
    except (FileNotFoundError, ProcessLookupError):
        return False
    return state != "Z"  # a zombie is dead; nobody has reaped it yet


def test_a_process_the_extractor_started_does_not_outlive_the_call() -> None:
    answer = envelope.run_in_envelope(
        "tl_core.derivation.testing:grandchild_entry", {}, b"", timeout_s=60
    )
    pid = int(answer.payload)
    deadline = time.monotonic() + 10
    while _alive(pid) and time.monotonic() < deadline:
        time.sleep(0.05)
    assert not _alive(pid)


def test_the_answer_cap_comes_from_the_source_bound() -> None:
    from tl_core.derivation.types import MAX_SOURCE_BYTES

    assert envelope.MAX_ANSWER_BYTES == 2 * MAX_SOURCE_BYTES + 1024 * 1024


def test_a_process_that_ignores_sigterm_does_not_outlive_the_call() -> None:
    """The leader leaves at once; the grandchild ignores SIGTERM, so only SIGKILL ends it."""
    answer = envelope.run_in_envelope(
        "tl_core.derivation.testing:stubborn_grandchild_entry", {}, b"", timeout_s=60
    )
    pid = int(answer.payload)
    deadline = time.monotonic() + 10
    while _alive(pid) and time.monotonic() < deadline:
        time.sleep(0.05)
    assert not _alive(pid)


def test_rows_travel_as_lists_and_come_back_as_rows() -> None:
    from tl_core.derivation.isolated import _unwire, _wire  # pyright: ignore[reportPrivateUsage]

    result = ExtractionResult(
        extractor="x",
        extractor_version="1",
        status="ok",
        columns=["a", "b"],
        rows=[{"a": "1", "b": None}, {"a": "2", "b": "3"}],
    )
    wire = _wire(result)
    assert b'"rows":[["1",null],["2","3"]]' in wire
    assert _unwire(wire) == result


@pytest.mark.parametrize(
    "rows",
    [
        [["1"]],  # too few cells
        [["1", "2", "3"]],  # too many
        [{"a": "1", "b": "2"}],  # a dict, the old shape
        [["1", 2]],  # a cell that is not text
        "rows",
    ],
)
def test_a_row_of_the_wrong_shape_is_refused_before_it_is_rebuilt(rows: object) -> None:
    import json

    from tl_core.derivation.isolated import _unwire  # pyright: ignore[reportPrivateUsage]

    body = {"extractor": "x", "extractor_version": "1", "status": "ok", "columns": ["a", "b"]}
    with pytest.raises(ValueError):
        _unwire(json.dumps({**body, "rows": rows}).encode())
