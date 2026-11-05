"""Fake and embedded clients agree on the materials reads (T04b); attach_record_file (S6)."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parents[2] / "tl-modules" / "materials" / "tests"))

import acc_s5  # noqa: E402
import acc_s6  # noqa: E402
import acc_t04b  # noqa: E402
from acc_runner import check_ids, run_check, run_main  # noqa: E402


@pytest.mark.parametrize("label", check_ids(acc_t04b))
def test_t04b_clients(
    label: str,
    tmp_path_factory: pytest.TempPathFactory,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """One named check per test (the id is the check function); checks that build on the
    earlier ones of the script run after them, in order."""
    run_check(acc_t04b, label, tmp_path_factory, monkeypatch, capsys, cumulative=True)


@pytest.mark.parametrize("label", check_ids(acc_s6))
def test_attach_record_file(
    label: str,
    tmp_path_factory: pytest.TempPathFactory,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """One named check per test (the id is the check function); checks that build on the
    earlier ones of the script run after them, in order."""
    run_check(acc_s6, label, tmp_path_factory, monkeypatch, capsys, cumulative=True)


def test_the_view_keys_agree_across_the_clients(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """S5: mto-line key and item-projects code agree on both clients (script, sqlite leg)."""
    run_main(acc_s5, tmp_path, monkeypatch, capsys)
