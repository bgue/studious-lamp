"""MTO line text (T06d): columns, sections, state words, no None, the textual-free import."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parents[2] / "tl-modules" / "materials" / "tests"))

import acc_t06d  # noqa: E402
from acc_runner import check_ids, run_check  # noqa: E402


@pytest.mark.parametrize("label", check_ids(acc_t06d))
def test_mto_check(
    label: str,
    tmp_path_factory: pytest.TempPathFactory,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """One named check of the ported script per test; the id is the check function's name."""
    run_check(acc_t06d, label, tmp_path_factory, monkeypatch, capsys)


def test_mto_screen_at_80_and_170_columns(
    tmp_path_factory: pytest.TempPathFactory,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """The screen on a headless `TlApp` at 80 and 170 columns, plain walk and Esc."""
    run_check(acc_t06d, None, tmp_path_factory, monkeypatch, capsys, screens=True)
