"""The tl mat write verbs: refusals, adjust --direction, a bad line exits 1 (T05c)."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parents[2] / "tl-modules" / "materials" / "tests"))

import acc_t05c  # noqa: E402
from acc_runner import run_main  # noqa: E402


def test_write_verbs(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    run_main(acc_t05c, tmp_path, monkeypatch, capsys)
