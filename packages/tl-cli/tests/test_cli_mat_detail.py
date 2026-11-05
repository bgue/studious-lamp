"""tl mat mto show and item-projects (T05d)."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parents[2] / "tl-modules" / "materials" / "tests"))

import acc_t05d  # noqa: E402
from acc_runner import run_main  # noqa: E402


def test_mto_show_and_item_projects(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    run_main(acc_t05d, tmp_path, monkeypatch, capsys)
