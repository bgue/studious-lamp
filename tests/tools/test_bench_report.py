"""``tests/bench/bench_report.py``: results files in, the markdown tables of the perf report out."""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

PATH = Path(__file__).resolve().parents[1] / "bench" / "bench_report.py"


def load() -> ModuleType:
    spec = importlib.util.spec_from_file_location("bench_report", PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["bench_report"] = module
    spec.loader.exec_module(module)
    return module


def series(
    dialect: str,
    target: str,
    scenario: str,
    median: float,
    p95: float,
    *,
    informational: bool = False,
) -> dict[str, Any]:
    return {
        "target": target,
        "scenario": scenario,
        "dialect": dialect,
        "records": 100000,
        "n": 60,
        "median_ms": median,
        "p95_ms": p95,
        "max_ms": p95 * 1.1,
        "round_p95_ms": [p95, p95, p95],
        "round_median_ms": [median, median, median],
        "load_before_round": [1.0, 1.0, 1.0],
        "note": "",
        "informational": informational,
    }


def run(label: str, rows: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "label": label,
        "git": "abc1234",
        "started_at": "20261010T000000Z",
        "finished_load_average": [1.0, 1.0, 1.0],
        "machine": {"nproc": 4, "cpu": "test cpu", "load_average_at_start": [1.0, 1.0, 1.0]},
        "series": rows,
        "extras": {},
    }


BASE = run(
    "baseline",
    [
        series("sqlite", "grid_scroll", "first_page", 36.1, 40.2),
        series("sqlite", "grid_filter", "filter slow: apply (count + page)", 480.0, 520.0),
        series("sqlite", "grid_filter", "filter slow: count", 240.0, 260.0, informational=True),
        series("postgres", "grid_scroll", "first_page", 5.0, 9.0),
        series("postgres", "realtime", "api write to sse", 15.0, 24.0),
        series("sqlite", "rebuild", "full rebuild (10000 records)", 40000.0, 41000.0),
    ],
)
AFTER = run(
    "after",
    [
        series("sqlite", "grid_scroll", "first_page", 2.0, 4.0),
        series("sqlite", "grid_filter", "filter slow: apply (count + page)", 100.0, 130.0),
        series("sqlite", "grid_filter", "filter new: apply (count + page)", 10.0, 12.0),
    ],
)


def write(tmp_path: Path, name: str, body: dict[str, Any]) -> Path:
    path = tmp_path / name
    path.write_text(json.dumps(body), encoding="utf-8")
    return path


def test_each_target_gets_a_heading_and_a_table() -> None:
    text = load().render_targets([BASE])
    for heading in (
        "## Grid scroll (p95 target 150 ms)",
        "## Grid filter (p95 target 150 ms)",
        "## Realtime (p95 target 2000 ms)",
        "## Rebuild (no hard target: hours, not days)",
    ):
        assert heading in text.splitlines()
    assert "| dialect | scenario | median ms | p95 ms | target ms | met |" in text
    assert "## Grid sort" not in text  # a target with no series is left out


def test_rows_show_one_decimal_the_target_and_whether_it_was_met() -> None:
    text = load().render_targets([BASE])
    assert "| sqlite | first_page | 36.1 | 40.2 | 150 | yes |" in text
    assert "| sqlite | filter slow: apply (count + page) | 480.0 | 520.0 | 150 | NO |" in text
    assert "| postgres | api write to sse | 15.0 | 24.0 | 2000 | yes |" in text


def test_informational_and_rebuild_rows_carry_no_verdict() -> None:
    text = load().render_targets([BASE])
    assert "| sqlite | filter slow: count | 240.0 | 260.0 | - | info |" in text
    assert "| sqlite | full rebuild (10000 records) | 40000.0 | 41000.0 | - | n/a |" in text


def test_a_verdict_line_per_dialect_ignores_informational_rows() -> None:
    lines = load().render_targets([BASE]).splitlines()
    assert "Verdict sqlite: met (worst p95 40.2 ms)" in lines  # the scroll table
    assert (
        "Verdict sqlite: NOT MET (worst p95 520.0 ms in filter slow: apply (count + page))" in lines
    )
    assert "Verdict postgres: met (worst p95 9.0 ms)" in lines
    assert not any(line.startswith("Verdict") and "260.0" in line for line in lines)
    rebuild = lines[lines.index("## Rebuild (no hard target: hours, not days)") :]
    assert not any(line.startswith("Verdict") for line in rebuild)


def test_rows_keep_dialect_order_then_the_order_of_the_file() -> None:
    text = load().render_targets([BASE])
    assert text.index("| sqlite | first_page") < text.index("| postgres | first_page")


def test_a_later_run_replaces_the_same_series_of_an_earlier_one() -> None:
    text = load().render_targets([BASE, AFTER])
    assert "| sqlite | first_page | 2.0 | 4.0 | 150 | yes |" in text
    assert "36.1" not in text
    assert "| sqlite | filter new: apply (count + page) | 10.0 | 12.0 | 150 | yes |" in text
    assert "| postgres | first_page | 5.0 | 9.0 | 150 | yes |" in text  # not in the later run


def test_compare_lists_the_series_both_runs_have_with_the_ratio_of_the_p95() -> None:
    text = load().render_compare(BASE, AFTER)
    assert "| dialect | scenario | before p95 ms | after p95 ms | change |" in text
    assert "| sqlite | first_page | 40.2 | 4.0 | x0.10 |" in text
    assert "| sqlite | filter slow: apply (count + page) | 520.0 | 130.0 | x0.25 |" in text
    assert "filter new" not in text and "api write" not in text


def test_main_prints_the_tables_for_one_or_more_files(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    module = load()
    one = write(tmp_path, "one.json", BASE)
    two = write(tmp_path, "two.json", AFTER)
    assert module.main([str(one), str(two)]) == 0
    assert "| sqlite | first_page | 2.0 | 4.0 | 150 | yes |" in capsys.readouterr().out


def test_main_compare_takes_exactly_two_files(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    module = load()
    one = write(tmp_path, "one.json", BASE)
    two = write(tmp_path, "two.json", AFTER)
    assert module.main(["--compare", str(one), str(two)]) == 0
    assert "before p95 ms" in capsys.readouterr().out
    assert module.main(["--compare", str(one)]) == 2


def test_main_reports_a_missing_file_on_stderr(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert load().main([str(tmp_path / "nope.json")]) == 2
    assert "nope.json" in capsys.readouterr().err
