"""Validating extracted rows against a document schema (P1-I3 T04). No database."""

from __future__ import annotations

from typing import Any

import pytest
from tl_core.derivation.types import ExtractionProblem
from tl_mod_documents.derivation.validation import (
    MAX_ISSUES,
    MAX_SHOWN_VALUE,
    ValidationReport,
    read_cell,
    validate_result,
)

SCHEMA: dict[str, Any] = {
    "type": "object",
    "required": ["tag", "size_in"],
    "properties": {
        "tag": {"type": "string", "pattern": "^[0-9]{2}-[A-Z]{2,3}-[0-9]{3,5}$"},
        "size_in": {"type": "number", "minimum": 0.25, "maximum": 144},
        "count": {"type": "integer", "minimum": 0},
        "fat": {"type": "boolean"},
        "fail": {"type": "string", "enum": ["FC", "FO", "FL"]},
        "date": {"type": "string", "format": "date"},
        "note": {"type": ["string", "null"], "maxLength": 10},
    },
}
COLUMNS = ["tag", "size_in", "count", "fat", "fail", "date", "note"]


def row(**cells: str | None) -> dict[str, str | None]:
    base: dict[str, str | None] = {c: None for c in COLUMNS}
    base.update(tag="47-FV-1001", size_in="4")
    base.update(cells)
    return base


def check(
    rows: list[dict[str, str | None]],
    columns: list[str] | None = None,
    schema: dict[str, Any] | None = None,
    **more: Any,
) -> ValidationReport:
    return validate_result(
        schema or SCHEMA,
        columns if columns is not None else COLUMNS,
        rows,
        schema_code="instrument-index",
        schema_version="1.0.0",
        **more,
    )


def codes(report: ValidationReport) -> list[tuple[int | None, str | None, str]]:
    return [(i.row, i.column, i.code) for i in report.issues]


# --- reading a cell -----------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("prop", "cell", "value"),
    [
        ({"type": "string"}, "  47-FV-1  ", "47-FV-1"),
        ({}, "x", "x"),
        ({"type": "integer"}, " 12 ", 12),
        ({"type": "integer"}, "-3", -3),
        ({"type": "integer"}, "+7", 7),
        ({"type": "number"}, "4", 4.0),
        ({"type": "number"}, "4.5", 4.5),
        ({"type": "number"}, "-0.25", -0.25),
        ({"type": "number"}, "1e3", 1000.0),
        ({"type": "boolean"}, "Yes", True),
        ({"type": "boolean"}, "N", False),
        ({"type": "boolean"}, "1", True),
        ({"type": "boolean"}, "FALSE", False),
        ({"type": ["integer", "null"]}, "5", 5),
        ({"type": ["null", "number"]}, "2.5", 2.5),
    ],
)
def test_a_cell_is_read_as_the_property_declares(
    prop: dict[str, Any], cell: str, value: Any
) -> None:
    got = read_cell(prop, cell)
    assert got == (value, None, None) and type(got[0]) is type(value)


@pytest.mark.parametrize("cell", [None, "", "   ", "\t"])
def test_an_empty_cell_is_absent_whatever_the_type(cell: str | None) -> None:
    for kind in ("string", "integer", "number", "boolean"):
        assert read_cell({"type": kind}, cell) == (None, None, None)


@pytest.mark.parametrize(
    ("prop", "cell", "code"),
    [
        ({"type": "integer"}, "1.0", "not_an_integer"),
        ({"type": "integer"}, "1,000", "not_an_integer"),
        ({"type": "integer"}, "ten", "not_an_integer"),
        ({"type": "number"}, "abc", "not_a_number"),
        ({"type": "number"}, "NaN", "not_a_number"),
        ({"type": "number"}, "Infinity", "not_a_number"),
        ({"type": "number"}, "1e999", "not_a_number"),
        ({"type": "boolean"}, "maybe", "not_a_boolean"),
        ({"type": "array"}, "a,b", "unsupported_type"),
        ({"type": "object"}, "{}", "unsupported_type"),
    ],
)
def test_a_cell_that_cannot_be_read_says_why(prop: dict[str, Any], cell: str, code: str) -> None:
    value, got_code, message = read_cell(prop, cell)
    assert value is None and got_code == code and message


# --- validate_result: rows ----------------------------------------------------------------------


def test_good_rows_are_valid_and_the_report_names_the_schema() -> None:
    report = check([row(), row(tag="47-FV-1002", size_in="6", count="2", fat="yes", fail="FC")])
    assert report.status == "valid" and report.issues == []
    assert (report.schema_code, report.schema_version) == ("instrument-index", "1.0.0")
    assert (report.rows_checked, report.rows_with_errors) == (2, 0)
    assert (report.error_count, report.warning_count, report.truncated) == (0, 0, False)


def test_one_bad_cell_is_one_issue_with_its_row_column_and_value() -> None:
    report = check([row(), row(tag="47-FV-1002", fail="XX")])
    assert report.status == "invalid"
    assert (report.rows_checked, report.rows_with_errors, report.error_count) == (2, 1, 1)
    (issue,) = report.issues
    assert (issue.level, issue.row, issue.column, issue.code) == ("error", 2, "fail", "enum")
    assert issue.value == "XX" and "XX" in issue.message


def test_an_unreadable_cell_is_one_issue_and_not_also_a_missing_value() -> None:
    report = check([row(size_in="four")])
    assert codes(report) == [(1, "size_in", "not_a_number")]
    assert report.issues[0].value == "four"


def test_each_json_schema_keyword_is_reported_under_its_own_name() -> None:
    report = check(
        [
            row(tag="bad tag", size_in="0.1", count="-1", date="2026-13-45", note="x" * 11),
            row(size_in="200"),
        ]
    )
    assert codes(report) == [
        (1, "count", "minimum"),
        (1, "date", "format"),
        (1, "note", "maxLength"),
        (1, "size_in", "minimum"),
        (1, "tag", "pattern"),
        (2, "size_in", "maximum"),
    ]
    assert report.rows_with_errors == 2 and report.error_count == 6


def test_a_blank_required_cell_is_a_required_error_of_its_field() -> None:
    report = check([row(tag=None), row(size_in="  ")])
    assert codes(report) == [(1, "tag", "required"), (2, "size_in", "required")]
    assert report.issues[0].message == "a value is required"


def test_a_blank_optional_cell_is_fine_and_a_null_type_accepts_it() -> None:
    assert check([row(count=None, fat="", note=None)]).status == "valid"


def test_every_missing_required_value_of_a_row_is_listed() -> None:
    report = check([row(tag=None, size_in=None)])
    assert sorted(codes(report)) == [(1, "size_in", "required"), (1, "tag", "required")]


def test_the_issues_of_a_row_come_in_column_order_of_the_schema_path() -> None:
    report = check([row(tag="x", count="-5")])
    assert [(i.column) for i in report.issues] == ["count", "tag"]


# --- validate_result: the file --------------------------------------------------------------


def test_a_required_property_with_no_column_is_a_file_level_error() -> None:
    report = check([{"tag": "47-FV-1001"}], columns=["tag"])
    assert (None, "size_in", "missing_column") in codes(report)
    assert (1, "size_in", "required") in codes(report)
    assert report.status == "invalid"


def test_an_unknown_column_is_a_warning_and_is_not_checked() -> None:
    report = check(
        [row(extra="whatever")],
        columns=[*COLUMNS, "extra"],
        schema={**SCHEMA, "additionalProperties": False},
    )
    assert report.status == "valid" and report.error_count == 0 and report.warning_count == 1
    (issue,) = report.issues
    assert (issue.level, issue.row, issue.column, issue.code) == (
        "warning",
        None,
        "extra",
        "unknown_column",
    )


def test_no_rows_is_not_valid() -> None:
    report = check([])
    assert report.status == "invalid" and codes(report) == [(None, None, "no_rows")]
    assert report.rows_checked == 0


def test_the_key_column_must_be_unique_and_the_later_row_is_blamed() -> None:
    report = check([row(), row(tag="47-FV-1002"), row(tag=" 47-FV-1001 ")], key_column="tag")
    (issue,) = report.issues
    assert (issue.row, issue.column, issue.code) == (3, "tag", "duplicate_key")
    assert "row 1" in issue.message and issue.value == "47-FV-1001"
    assert check([row(), row()]).status == "valid"  # no key column given: repeats are allowed


def test_blank_keys_are_not_duplicates_of_each_other() -> None:
    report = check([row(tag=None), row(tag=None)], key_column="tag")
    assert [i.code for i in report.issues] == ["required", "required"]


def test_problems_the_extractor_reported_make_the_table_invalid() -> None:
    report = check(
        [row()],
        problems=[
            ExtractionProblem(
                code="ragged_row", message="row has 3 cells, the header has 7", row=2
            ),
            ExtractionProblem(code="duplicate_header", message="column 'tag' appears twice"),
        ],
    )
    assert report.status == "invalid" and report.error_count == 2
    assert codes(report) == [(2, None, "ragged_row"), (None, None, "duplicate_header")]
    assert report.rows_with_errors == 1  # only the problem tied to a row counts as a bad row


def test_file_level_issues_come_before_row_issues() -> None:
    report = check([row(fail="XX")], columns=[*COLUMNS, "extra"])
    assert [i.row for i in report.issues] == [None, 1]


# --- caps and shape -----------------------------------------------------------------------------


def test_the_report_lists_a_thousand_issues_and_counts_all_of_them() -> None:
    rows = [row(fail="XX") for _ in range(MAX_ISSUES + 50)]
    report = check(rows)
    assert len(report.issues) == MAX_ISSUES and report.truncated
    assert report.error_count == MAX_ISSUES + 50 and report.rows_with_errors == MAX_ISSUES + 50
    assert report.issues[-1].row == MAX_ISSUES


def test_a_long_cell_is_cut_in_the_report() -> None:
    long = "Z" * 5000
    report = check([row(fail=long)])
    (issue,) = report.issues
    assert issue.value is not None and len(issue.value) <= MAX_SHOWN_VALUE
    assert len(issue.message) <= 300


def test_the_report_round_trips_through_json() -> None:
    report = check([row(fail="XX")])
    assert ValidationReport.model_validate_json(report.model_dump_json()) == report


def test_rows_are_not_changed_and_a_schema_without_properties_accepts_anything() -> None:
    rows = [row(fail="XX")]
    before = [dict(r) for r in rows]
    check(rows)
    assert rows == before
    assert check([{"a": "1"}], columns=["a"], schema={"type": "object"}).warning_count == 1
