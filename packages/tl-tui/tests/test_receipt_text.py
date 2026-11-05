"""Receipt log and panel text on the seed (T06b): columns, rejection, MTR note, lines table."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parents[2] / "tl-modules" / "materials" / "tests"))

import acc_t06b  # noqa: E402
from acc_runner import run_main  # noqa: E402


def test_receipt_text_on_the_seed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    run_main(acc_t06b, tmp_path, monkeypatch, capsys)
