"""The pure text of the shared log screen (P1-UX2-S2)."""

from __future__ import annotations

from dataclasses import dataclass

import pytest
from rich.cells import cell_len
from tl_tui.log_text import WIDE_COLUMNS, actions_text, breadcrumb_text, is_wide, key_label

NUMBER = "P123-RFI-0328"
TITLE = "Conflict in piling/utilities at AZ203"


@dataclass(frozen=True)
class Act:
    key: str
    label: str


def test_breadcrumb_with_a_record() -> None:
    assert (
        breadcrumb_text("P123", "RFI Log", NUMBER, TITLE, 120)
        == f"P123 › RFI Log › {NUMBER}: {TITLE}"
    )


def test_breadcrumb_without_a_record_is_the_log_only() -> None:
    assert breadcrumb_text("P123", "RFI Log", None, None, 80) == "P123 › RFI Log"
    assert breadcrumb_text("P123", "RFI Log", None, "orphan title", 80) == "P123 › RFI Log"
    assert breadcrumb_text("P123", "RFI Log", "", "", 80) == "P123 › RFI Log"


def test_breadcrumb_without_a_title_ends_at_the_number() -> None:
    assert breadcrumb_text("P123", "RFI Log", NUMBER, None, 80) == f"P123 › RFI Log › {NUMBER}"
    assert breadcrumb_text("P123", "RFI Log", NUMBER, "  ", 80) == f"P123 › RFI Log › {NUMBER}"


@pytest.mark.parametrize("width", [40, 80, 160])
def test_breadcrumb_shortens_the_title_to_the_width(width: int) -> None:
    title = "Conflict in piling and utilities at AZ203 " * 6
    text = breadcrumb_text("P123", "RFI Log", NUMBER, title, width)
    assert cell_len(text) <= width
    assert text.startswith(f"P123 › RFI Log › {NUMBER}: Con")
    assert text.endswith("…")


def test_breadcrumb_keeps_a_title_that_fits_exactly() -> None:
    full = f"P123 › RFI Log › {NUMBER}: {TITLE}"
    assert breadcrumb_text("P123", "RFI Log", NUMBER, TITLE, cell_len(full)) == full
    cut = breadcrumb_text("P123", "RFI Log", NUMBER, TITLE, cell_len(full) - 1)
    assert cut.endswith("…") and cell_len(cut) == cell_len(full) - 1


def test_breadcrumb_never_cuts_project_log_or_number() -> None:
    head = f"P123 › RFI Log › {NUMBER}"
    for width in (-5, 0, 1, 10, cell_len(head), cell_len(head) + 2, cell_len(head) + 3):
        text = breadcrumb_text("P123", "RFI Log", NUMBER, TITLE, width)
        assert text.startswith(head)
    assert breadcrumb_text("P123", "RFI Log", NUMBER, TITLE, 10) == head  # no room for any title
    one = breadcrumb_text("P123", "RFI Log", NUMBER, TITLE, cell_len(head) + 3)
    assert one == f"{head}: …"


def test_breadcrumb_counts_wide_characters_in_cells() -> None:
    title = "杭州桥梁桩基础与管线冲突 " * 3
    for width in (40, 60, 80):
        text = breadcrumb_text("P123", "RFI Log", NUMBER, title, width)
        assert cell_len(text) <= width
        assert text.endswith("…")
    # a wide character that straddles the cut is dropped whole, not split
    text = breadcrumb_text("P1", "L", "N1", "桥桥桥桥", cell_len("P1 › L › N1: ") + 4)
    assert text == "P1 › L › N1: 桥…"


def test_breadcrumb_flattens_line_breaks_in_a_title() -> None:
    assert breadcrumb_text("P1", "L", "N1", "two\nlines", 80) == "P1 › L › N1: two lines"


def test_actions_text_lists_keys_labels_and_open() -> None:
    acts = [Act("a", "Answer"), Act("c", "Close")]
    assert actions_text(acts, can_open=True) == "[a] Answer  [c] Close  [Enter] Open record"
    assert actions_text(acts, can_open=False) == "[a] Answer  [c] Close"
    assert actions_text([], can_open=True) == "[Enter] Open record"


def test_actions_text_is_empty_for_nothing() -> None:
    assert actions_text([], can_open=False) == ""


def test_actions_text_shows_key_names_as_a_person_reads_them() -> None:
    acts = [Act("ctrl+e", "Escalate"), Act("f6", "Panels"), Act("shift+f6", "Back")]
    assert actions_text(acts, can_open=False) == "[Ctrl+E] Escalate  [F6] Panels  [Shift+F6] Back"
    assert key_label("escape") == "Esc" and key_label("slash") == "/" and key_label("a") == "a"
    assert key_label("pageup") == "PgUp" and key_label("ctrl+shift+x") == "Ctrl+Shift+X"


def test_is_wide_switches_at_160_columns() -> None:
    assert WIDE_COLUMNS == 160
    assert not is_wide(159)
    assert is_wide(160)
    assert is_wide(300) and not is_wide(0)
