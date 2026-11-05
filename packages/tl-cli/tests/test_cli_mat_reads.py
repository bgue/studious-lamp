"""The tl mat read verbs and the ls aliases (T05b)."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parents[2] / "tl-modules" / "materials" / "tests"))

import acc_t05b  # noqa: E402
from acc_runner import run_main  # noqa: E402


def test_read_verbs(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    run_main(acc_t05b, tmp_path, monkeypatch, capsys)
