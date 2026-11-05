"""Stock and Movement log screens at 80 and 170 columns (T06f)."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parents[2] / "tl-modules" / "materials" / "tests"))

import acc_t06f  # noqa: E402
import acc_t06g  # noqa: E402
from acc_runner import run_main  # noqa: E402


def test_stock_and_movement_screens(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    run_main(acc_t06f, tmp_path, monkeypatch, capsys)


def test_movement_for_columns_and_receive_signs(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    run_main(acc_t06g, tmp_path, monkeypatch, capsys)
