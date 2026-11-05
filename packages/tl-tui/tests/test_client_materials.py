"""Fake and embedded clients agree on the materials reads and the write door (T04b)."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parents[2] / "tl-modules" / "materials" / "tests"))

import acc_s5  # noqa: E402
import acc_s6  # noqa: E402
import acc_t04b  # noqa: E402
from acc_runner import run_main  # noqa: E402


def test_fake_and_embedded_agree(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    run_main(acc_t04b, tmp_path, monkeypatch, capsys)


def test_attach_record_file_hidden_is_missing_and_no_event_on_refusal(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    run_main(acc_s6, tmp_path, monkeypatch, capsys)


def test_the_view_keys_agree_across_the_clients(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    run_main(acc_s5, tmp_path, monkeypatch, capsys)
