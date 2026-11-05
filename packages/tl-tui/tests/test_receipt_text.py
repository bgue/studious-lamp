"""Receipt panel and log text (T06b): seed panel, columns, empties, the amber MTR Note."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parents[2] / "tl-modules" / "materials" / "tests"))

import acc_t06b  # noqa: E402
from acc_runner import ledger_copy, point_at_seed  # noqa: E402

SIZES = acc_t06b.SIZES


@pytest.fixture
def db(
    tmp_path: Path, tmp_path_factory: pytest.TempPathFactory, monkeypatch: pytest.MonkeyPatch
) -> Path:
    point_at_seed(acc_t06b, tmp_path_factory, monkeypatch)
    return ledger_copy(acc_t06b, tmp_path)


def test_seed_panel_sections_and_widths(db: Path) -> None:
    """80 and 170 columns: no None, no bare dash, in width, sections in order."""
    acc_t06b.check_seed_panel(db)


def test_columns_for_drop_order() -> None:
    acc_t06b.check_columns_for()


def test_rejection_line_in_the_panel() -> None:
    acc_t06b.check_rejection()


def test_empty_values_and_mtr_words() -> None:
    acc_t06b.check_empty_and_mtr()


def test_missing_mtr_is_an_amber_note_first_in_files() -> None:
    """The MTR line is a Note in the waiting style (yellow); present or not required: no Note."""
    acc_t06b.check_mtr_note()


def test_lines_table() -> None:
    acc_t06b.check_lines_table()


def test_import_leaves_textual_out_of_sys_modules() -> None:
    """Runs the import in a subprocess."""
    acc_t06b.check_import_leaves_textual()


@pytest.mark.parametrize("size", SIZES, ids=lambda s: f"{s[0]}x{s[1]}")
def test_receipt_log_screen_walk(db: Path, size: tuple[int, int]) -> None:
    acc_t06b.screen_check(db, size)
