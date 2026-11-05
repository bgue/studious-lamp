"""The six materials reports, CSV and the heat_trace MTR (T05a)."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parents[2] / "tl-modules" / "materials" / "tests"))

import acc_t05a  # noqa: E402
from acc_runner import run_main  # noqa: E402


def test_six_reports(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    run_main(acc_t05a, tmp_path, monkeypatch, capsys)
