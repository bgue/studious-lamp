"""Write verbs of `tl mat`: receive, move (adjust --direction), reserve, mto assign (T05c)."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parents[2] / "tl-modules" / "materials" / "tests"))

import acc_t05c  # noqa: E402
from acc_runner import check_ids, run_check  # noqa: E402


@pytest.mark.parametrize("label", check_ids(acc_t05c))
def test_write_verb(
    label: str,
    tmp_path_factory: pytest.TempPathFactory,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """One named check per test (the id is the check function); checks that build on the
    earlier ones of the script run after them, in order."""
    run_check(acc_t05c, label, tmp_path_factory, monkeypatch, capsys, cumulative=True)
