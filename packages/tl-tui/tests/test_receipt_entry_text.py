"""Receipt entry form text and screen (T06e): messages, Delete, refusal, MTR file."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parents[2] / "tl-modules" / "materials" / "tests"))

import acc_t06e  # noqa: E402
from acc_runner import point_at_seed  # noqa: E402

SIZES = acc_t06e.SIZES


@pytest.fixture(autouse=True)
def seed(tmp_path_factory: pytest.TempPathFactory, monkeypatch: pytest.MonkeyPatch) -> None:
    point_at_seed(acc_t06e, tmp_path_factory, monkeypatch)


def test_header_messages() -> None:
    acc_t06e.check_header_messages()


def test_line_messages() -> None:
    acc_t06e.check_line_messages()


def test_two_lines_build_one_create_receipt() -> None:
    acc_t06e.check_build_two_lines()


def test_no_none_or_bare_dash() -> None:
    acc_t06e.check_no_none_or_dash()


def test_hints() -> None:
    acc_t06e.check_hints()


def test_import_leaves_textual_out_of_sys_modules() -> None:
    """Runs the import in a subprocess."""
    acc_t06e.check_textual_free()


@pytest.mark.parametrize("size", SIZES, ids=lambda s: f"{s[0]}x{s[1]}")
def test_entry_screen_delete_keeps_cursor_and_refused_save_keeps_the_form(
    size: tuple[int, int],
) -> None:
    """On the screen: Delete on line 2 of 3, on the last row and on row 0 keeps the cursor on the
    right row; a bad location on Ctrl+S keeps the form open with the typed lines, says why
    ("Pick a location of this project.", "! Not saved") and books nothing; the fix then saves."""
    acc_t06e.screen_check(size)


def test_item_crumb() -> None:
    acc_t06e.check_item_crumb()


def test_mtr_path_messages() -> None:
    acc_t06e.check_mtr_text()


def test_mtr_file_attached_on_save_with_the_fake() -> None:
    acc_t06e.check_mtr_fake_saves()


def test_mtr_file_attached_on_the_real_ledger() -> None:
    acc_t06e.check_mtr_real_ledger()
