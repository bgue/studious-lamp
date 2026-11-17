"""The rule of ``conftest.perf_requested``: named by path, or TL_PERF=1; never by a parent."""

from __future__ import annotations

from perf_gate import HERE, perf_requested  # pyright: ignore[reportMissingImports]


def test_perf_runs_only_when_asked() -> None:
    assert perf_requested([str(HERE)], {})
    assert perf_requested([f"{HERE}/test_budget.py::test_every_list_view_is_under_a_second"], {})
    assert perf_requested([], {"TL_PERF": "1"})
    assert not perf_requested([], {})
    assert not perf_requested([str(HERE.parent)], {})
    assert not perf_requested([], {"TL_PERF": "0"})
