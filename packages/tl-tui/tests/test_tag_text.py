"""The text of the tag register: rows, detail, class cycle, summary line (P1-I1-T09d)."""

from __future__ import annotations

from typing import Any, Literal

import pytest
from tl_mod_engineering.views import TagView
from tl_schema.forms import ConformanceIssue
from tl_tui.tag_text import COLUMNS, detail_lines, next_class, row_cells, summary_line


def view(**more: Any) -> TagView:
    fields: dict[str, Any] = {
        "id": "T1",
        "number": "47-FV-1001",
        "title": "Feed gas control",
        "class_code": "ControlValve",
        "status": "Design",
        "area": "47",
        "mnemonic": "FV",
        "sequence": 1001,
        "segments": {"area": "47", "mnemonic": "FV", "seq": "1001"},
        "pattern_code": "tag",
        "number_status": "ok",
        "violations": [],
        "origin": "created",
        "conformance": "nonconformant",
        "version": 3,
        "psets": {},
        "issues": [],
    }
    fields.update(more)
    return TagView(**fields)


def issue(
    path: str = "psets.valve_data", level: Literal["warning", "nonconformant"] = "nonconformant"
) -> ConformanceIssue:
    return ConformanceIssue(
        path=path,
        level=level,
        rule="class_required",
        message="required by the class",
    )


def test_a_row_has_one_cell_per_column() -> None:
    assert COLUMNS == ("Number", "Class", "Status", "Number check", "Conformance", "Title")
    assert row_cells(view()) == (
        "47-FV-1001",
        "Control valve",
        "Design",
        "ok",
        "✗ nonconformant",
        "Feed gas control",
    )


def test_a_missing_class_or_status_is_a_dash_and_a_bad_number_says_bad() -> None:
    cells = row_cells(view(class_code=None, status=None, number_status="violation"))
    assert cells[1:4] == ("-", "-", "does not fit")


def test_the_detail_names_the_parts_the_class_and_what_is_lacking() -> None:
    lines = detail_lines(view(issues=[issue(), issue("psets.valve_data.size_in", "warning")]))
    assert lines == [
        "47-FV-1001  Feed gas control",
        "class Control valve  |  status Design  |  conformance nonconformant",
        "number ok: Area 47, Mnemonic FV, Seq 1001",
        "lacks:",
        "  nonconformant  Valve data required by the class",
        "  warning  Valve data / Size in required by the class",
    ]


def test_technical_mode_adds_the_raw_class_path_and_segments() -> None:
    lines = detail_lines(view(issues=[issue()]), technical=True)
    assert lines[1].startswith("class ControlValve  |")
    assert lines[2] == "number ok: area=47 mnemonic=FV seq=1001"
    assert lines[4] == "  nonconformant  psets.valve_data required by the class"


def test_the_detail_shows_a_violation_of_the_number_and_a_clean_tag() -> None:
    bad = view(
        number="LEGACY-1",
        title="LEGACY-1",
        class_code=None,
        status=None,
        segments={},
        number_status="violation",
        conformance="ok",
        violations=[
            {"segment": None, "level": "error", "message": "'LEGACY-1' does not fit the pattern"}
        ],
    )
    assert detail_lines(bad) == [
        "LEGACY-1  LEGACY-1",
        "class -  |  status -  |  conformance ok",
        "number does not fit the pattern",
        "  ! number: 'LEGACY-1' does not fit the pattern (error)",
        "nothing lacking",
    ]
    assert detail_lines(view())[-1] == "no detail loaded"  # a listing carries no issues
    segment = view(violations=[{"segment": "mnemonic", "level": "error", "message": "unknown"}])
    assert "  ! mnemonic: unknown (error)" in detail_lines(segment)


@pytest.mark.parametrize(
    ("current", "expected"),
    [
        (None, "ControlValve"),
        ("ControlValve", "ManualValve"),
        ("ManualValve", None),
        ("Gone", None),
    ],
)
def test_the_class_filter_cycles_through_the_classes_in_the_list(
    current: str | None, expected: str | None
) -> None:
    assert next_class(current, ["ManualValve", "ControlValve", "ControlValve"]) == expected


def test_no_classes_means_the_filter_stays_on_all() -> None:
    assert next_class(None, []) is None


def test_the_summary_line_lists_only_the_filters_that_apply() -> None:
    plain: dict[str, Any] = {
        "class_code": None,
        "violations_only": False,
        "include_ended": False,
        "text": "",
    }
    assert summary_line(5, 7, **plain) == "5 of 7 tags"
    assert summary_line(1, 1, **plain) == "1 of 1 tags"
    everything: dict[str, Any] = {
        "class_code": "Pump",
        "violations_only": True,
        "include_ended": True,
        "text": " fv ",
    }
    assert summary_line(2, 7, **everything) == (
        '2 of 7 tags  class Pump  violations only  incl. ended  filter "fv"'
    )
    assert "class Control valve" in summary_line(
        1, 7, **{**everything, "class_code": "ControlValve"}
    )
