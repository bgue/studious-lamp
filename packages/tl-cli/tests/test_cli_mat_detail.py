"""`tl mat mto show`, `item-projects` and the `ls` aliases (T05d)."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parents[2] / "tl-modules" / "materials" / "tests"))

import acc_t05d  # noqa: E402
from acc_runner import check_ids, run_check  # noqa: E402


@pytest.mark.parametrize("label", check_ids(acc_t05d))
def test_detail_verb(
    label: str,
    tmp_path_factory: pytest.TempPathFactory,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """One named check of the ported script per test; the id is the check function's name."""
    run_check(acc_t05d, label, tmp_path_factory, monkeypatch, capsys)
