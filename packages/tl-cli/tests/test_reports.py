"""The six materials reports, CSV and the report routes; heat_trace MTR (T05a)."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parents[2] / "tl-modules" / "materials" / "tests"))

import acc_t05a  # noqa: E402
from acc_runner import check_ids, run_check  # noqa: E402


@pytest.mark.parametrize("label", check_ids(acc_t05a))
def test_report(
    label: str,
    tmp_path_factory: pytest.TempPathFactory,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """One named check of the ported script per test; the id is the check function's name."""
    run_check(acc_t05a, label, tmp_path_factory, monkeypatch, capsys)
