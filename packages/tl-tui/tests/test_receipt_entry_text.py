"""Receipt entry text and screen on the seed (T06e): Delete removes a line, a refusal keeps it."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parents[2] / "tl-modules" / "materials" / "tests"))

import acc_t06e  # noqa: E402
from acc_runner import run_main  # noqa: E402


def test_receipt_entry_on_the_seed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    run_main(acc_t06e, tmp_path, monkeypatch, capsys)
