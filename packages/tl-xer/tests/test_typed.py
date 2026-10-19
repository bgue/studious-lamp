"""The XER document schema and the typed snapshot: errors and warnings (P1-I4-T04)."""

from __future__ import annotations

import pytest
from tl_xer import limits
from tl_xer.problems import Problems
from tl_xer.process import process
from tl_xer.reader import read_xer
from tl_xer.synth import week_pair
from tl_xer.typed import (
    ACTIVITY_COLUMNS,
    COLUMN_KINDS,
    TABLE_COLUMNS,
    Options,
    analyse,
    parse_date,
    parse_number,
)
from xersupport import (
    codes,
    drop_column,
    drop_table,
    encode,
    first_text,
    replace_once,
    second_text,
    set_cell,
)


def run(text: str, project: str | None = None):  # noqa: ANN201 - the test helper's result
    return process(encode(text), Options(project=project))


def problem_codes(text: str, project: str | None = None) -> list[object]:
    return codes(run(text, project).report["problems"])


def test_the_demo_file_is_valid_and_typed() -> None:
    outcome = run(first_text())
    assert outcome.status == "valid" and outcome.report["error_count"] == 0
    assert outcome.snapshot is not None
    project = outcome.snapshot.project
    assert project["short_name"] == "DEMO-RACK" and project["data_date"] == "2026-10-05T08:00"
    assert outcome.snapshot.counts() == {
        "calendars": 1,
        "wbs": 4,
        "activities": 21,
        "relationships": 23,
        "codes": 21,
        "udfs": 12,
    }


def test_each_typed_table_has_a_kind_for_every_column() -> None:
    for name, columns in TABLE_COLUMNS.items():
        assert len(COLUMN_KINDS[name]) == len(columns), name
    assert len(ACTIVITY_COLUMNS) == len(set(ACTIVITY_COLUMNS))


def test_an_activity_is_typed_with_hours_iso_dates_and_a_wbs_path() -> None:
    outcome = run(first_text())
    assert outcome.snapshot is not None
    row = dict(
        zip(
            ACTIVITY_COLUMNS,
            next(r for r in outcome.snapshot.tables["activities"] if r[0] == "A1230"),
            strict=True,
        )
    )
    assert row["name"] == "Install pipe rack supports"
    assert row["wbs_path"] == "DEMO > CON" and row["task_type"] == "task"
    assert row["status"] == "in_progress" and row["calendar_id"] == "1"
    assert row["original_duration_hr"] == 80.0 and row["remaining_duration_hr"] == 48.0
    assert row["early_finish"] == "2026-10-12T16:00" and row["actual_start"] == "2026-09-24T08:00"
    assert row["actual_finish"] is None
    assert row["total_float_hr"] == 72.0 and row["free_float_hr"] == 72.0
    assert row["percent_complete"] == 40.0 and row["critical"] is False


def test_the_second_file_shows_the_float_of_a1230_eroded_by_five_days() -> None:
    first, second = (run(t).snapshot for t in (first_text(), second_text()))
    assert first is not None and second is not None

    def floats(snapshot, code):  # noqa: ANN001, ANN202
        row = next(r for r in snapshot.tables["activities"] if r[0] == code)
        return row[ACTIVITY_COLUMNS.index("total_float_hr")]

    assert floats(first, "A1230") == 72.0 and floats(second, "A1230") == 32.0
    assert floats(first, "A1120") == 32.0 and floats(second, "A1120") == -8.0


def test_a_milestone_and_a_completed_activity_are_typed() -> None:
    snapshot = run(first_text()).snapshot
    assert snapshot is not None
    by_code = {
        r[0]: dict(zip(ACTIVITY_COLUMNS, r, strict=True)) for r in snapshot.tables["activities"]
    }
    assert by_code["A1300"]["task_type"] == "finish_milestone"
    done = by_code["A1000"]
    assert done["status"] == "completed" and done["percent_complete"] == 100.0
    assert done["total_float_hr"] is None and done["critical"] is False


def test_the_critical_flag_is_float_at_or_below_zero_and_not_complete() -> None:
    snapshot = run(second_text()).snapshot
    assert snapshot is not None
    flagged = sorted(
        str(r[0]) for r in snapshot.tables["activities"] if r[ACTIVITY_COLUMNS.index("critical")]
    )
    assert flagged == [
        "A1110",
        "A1120",
        "A1140",
        "A1150",
        "A1240",
        "A1250",
        "A1260",
        "A1270",
        "A1290",
        "A1300",
    ]


def test_a_completed_activity_is_never_critical_whatever_its_float_says() -> None:
    text = set_cell(first_text(), "TASK", 1, "total_float_hr_cnt", "0")
    snapshot = run(text).snapshot
    assert snapshot is not None
    first = snapshot.tables["activities"][0]
    assert first[0] == "A1000" and first[ACTIVITY_COLUMNS.index("status")] == "completed"
    assert first[ACTIVITY_COLUMNS.index("total_float_hr")] == 0.0
    assert first[ACTIVITY_COLUMNS.index("critical")] is False


def test_calendars_kept_are_the_ones_used_and_the_default() -> None:
    snapshot = run(first_text()).snapshot
    assert snapshot is not None
    assert [(r[0], r[1], r[6]) for r in snapshot.tables["calendars"]] == [
        ("1", "Five-day week", True)
    ]


def test_activity_codes_and_user_fields_are_flattened_per_activity() -> None:
    snapshot = run(first_text()).snapshot
    assert snapshot is not None
    assert ("A1230", "Area", "CON", "Construction", 13) in snapshot.tables["codes"]
    udfs = [r for r in snapshot.tables["udfs"] if r[0] == "A1230"]
    assert udfs == [("A1230", "user_field_1", "Contractor reference", "text", "CR-1230", 4)]


# --- errors ------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("version", "code"),
    [
        ("7.0", "unsupported_version"),
        ("31.1", "unsupported_version"),
        ("x", "bad_version"),
        ("", "bad_version"),
    ],
)
def test_an_unsupported_or_missing_version_is_an_error(version: str, code: str) -> None:
    text = replace_once(first_text(), "ERMHDR\t20.12", f"ERMHDR\t{version}")
    outcome = run(text)
    assert outcome.status == "invalid" and code in codes(outcome.report["problems"])


@pytest.mark.parametrize("table", ["PROJECT", "PROJWBS", "CALENDAR", "TASK", "TASKPRED"])
def test_a_required_table_that_is_missing_is_named(table: str) -> None:
    outcome = run(drop_table(first_text(), table))
    problems = outcome.report["problems"]
    assert outcome.status == "invalid"
    assert [(p["code"], p["table"]) for p in problems] == [("missing_table", table)]


@pytest.mark.parametrize(
    ("table", "column"),
    [
        ("TASK", "task_code"),
        ("TASK", "total_float_hr_cnt"),
        ("PROJECT", "last_recalc_date"),
        ("TASKPRED", "pred_type"),
    ],
)
def test_a_required_column_that_is_missing_is_named(table: str, column: str) -> None:
    problems = run(drop_column(first_text(), table, column)).report["problems"]
    assert [(p["code"], p["table"], p["field"]) for p in problems if p["severity"] == "error"] == [
        ("missing_column", table, column)
    ]


def test_a_missing_useful_column_is_a_warning_and_the_snapshot_is_built() -> None:
    outcome = run(drop_column(first_text(), "TASK", "free_float_hr_cnt"))
    assert outcome.status == "valid"
    assert [(p["severity"], p["code"], p["field"]) for p in outcome.report["problems"]] == [
        ("warning", "missing_optional_column", "free_float_hr_cnt")
    ]
    assert outcome.snapshot is not None
    assert all(
        r[ACTIVITY_COLUMNS.index("free_float_hr")] is None
        for r in outcome.snapshot.tables["activities"]
    )


def two_projects(text: str) -> str:
    row = "%R\t2\tOTHER\t1\t2026-10-05 08:00\t\t\t"
    return replace_once(text, "\r\n%T\tCALENDAR", f"\r\n{row}\r\n%T\tCALENDAR")


def test_a_file_with_two_projects_needs_the_one_to_read_to_be_named() -> None:
    text = two_projects(first_text())
    outcome = run(text)
    assert outcome.status == "invalid"
    [problem] = outcome.report["problems"]
    assert (
        problem["code"] == "multi_project"
        and "DEMO-RACK" in problem["message"]
        and "OTHER" in problem["message"]
    )
    chosen = run(text, "DEMO-RACK")
    assert chosen.status == "valid" and chosen.report["project"]["other_projects"] == 1


def test_a_named_project_that_the_file_lacks_is_an_error_even_for_a_single_project() -> None:
    assert problem_codes(first_text(), "NOPE") == ["project_not_found"]
    assert problem_codes(two_projects(first_text()), "NOPE") == ["project_not_found"]


def test_two_projects_with_the_name_asked_for_are_an_error() -> None:
    row = "%R\t2\tDEMO-RACK\t1\t2026-10-05 08:00\t\t\t"
    text = replace_once(first_text(), "\r\n%T\tCALENDAR", f"\r\n{row}\r\n%T\tCALENDAR")
    assert problem_codes(text, "DEMO-RACK") == ["duplicate_project"]


def test_the_project_option_is_not_echoed_beyond_the_id_limit() -> None:
    [problem] = run(first_text(), "N" * 50).report["problems"]
    assert len(problem["message"]) <= limits.MAX_MESSAGE_CHARS


def test_no_data_date_and_impossible_dates_are_errors() -> None:
    text = first_text()
    assert problem_codes(set_cell(text, "PROJECT", 1, "last_recalc_date", "")) == ["no_data_date"]
    assert problem_codes(set_cell(text, "PROJECT", 1, "last_recalc_date", "2026-02-30 08:00")) == [
        "bad_date"
    ]
    assert problem_codes(set_cell(text, "PROJECT", 1, "last_recalc_date", "05/10/2026")) == [
        "bad_date"
    ]


@pytest.mark.parametrize(
    "value",
    ["2026-02-30 08:00", "2026-13-01 08:00", "tomorrow", "2026-10-05 25:00", "2026-10-05T08:00"],
)
def test_a_task_date_that_is_not_a_date_names_the_row_and_the_column(value: str) -> None:
    outcome = run(set_cell(first_text(), "TASK", 13, "early_start_date", value))
    [problem] = outcome.report["problems"]
    assert (problem["code"], problem["table"], problem["row"], problem["field"]) == (
        "bad_date",
        "TASK",
        13,
        "early_start_date",
    )
    assert value not in problem["message"]


@pytest.mark.parametrize("value", ["abc", "1e5", "1,5", "--1", "NaN", "inf", "1" * 20])
def test_a_number_that_is_not_a_plain_decimal_is_an_error(value: str) -> None:
    outcome = run(set_cell(first_text(), "TASK", 13, "total_float_hr_cnt", value))
    assert codes(outcome.report["problems"]) == ["bad_number"]


def test_parse_helpers() -> None:
    assert parse_date("2026-10-05 08:30") == "2026-10-05T08:30"
    assert parse_date("2026-10-05") == "2026-10-05T00:00"
    assert parse_date(" ") is None
    assert parse_number("-12.5") == -12.5 and parse_number("") is None
    with pytest.raises(ValueError):
        parse_date("2026-02-29 00:00")
    with pytest.raises(ValueError):
        parse_number("1e3")


def test_a_repeated_activity_id_is_an_error_naming_both_rows() -> None:
    text = set_cell(first_text(), "TASK", 5, "task_code", "A1000")
    [problem] = run(text).report["problems"]
    assert problem["code"] == "duplicate_activity_id" and "rows 1 and 5" in problem["message"]


@pytest.mark.parametrize("value", ["", " ", "X" * (limits.MAX_ID_CHARS + 1)])
def test_an_activity_id_must_be_present_and_within_the_limit(value: str) -> None:
    assert problem_codes(set_cell(first_text(), "TASK", 3, "task_code", value)) == [
        "bad_activity_id"
    ]


def test_references_that_do_not_resolve_are_errors() -> None:
    text = first_text()
    assert problem_codes(set_cell(text, "TASK", 2, "wbs_id", "999")) == ["dangling_wbs"]
    assert problem_codes(set_cell(text, "TASK", 2, "clndr_id", "99")) == ["dangling_calendar"]
    assert problem_codes(set_cell(text, "TASKPRED", 3, "pred_task_id", "99999")) == [
        "bad_relationship"
    ]
    assert problem_codes(set_cell(text, "TASKPRED", 3, "pred_type", "PR_XX")) == [
        "bad_relationship"
    ]
    assert problem_codes(set_cell(text, "TASK", 2, "task_type", "TT_Other")) == [
        "unknown_task_type"
    ]
    assert problem_codes(set_cell(text, "TASK", 2, "status_code", "TK_Weird")) == ["unknown_status"]


def test_a_wbs_loop_is_an_error() -> None:
    text = set_cell(first_text(), "PROJWBS", 1, "parent_wbs_id", "103")
    assert "wbs_loop" in problem_codes(text)
    selfish = set_cell(first_text(), "PROJWBS", 2, "parent_wbs_id", "101")
    assert "wbs_loop" in problem_codes(selfish)


def test_a_wbs_path_longer_than_the_text_limit_is_an_error() -> None:
    text = set_cell(first_text(), "PROJWBS", 2, "wbs_short_name", "S" * limits.MAX_ID_CHARS)
    for row in (3, 4):
        text = set_cell(text, "PROJWBS", row, "parent_wbs_id", "101")
    # a chain of ten long names under the first area: 10 x 60 characters is over 500
    long_name = "Z" * limits.MAX_ID_CHARS
    extra = "\r\n".join(
        f"%R\t{300 + i}\t1\t{90 + i}\tN\t{long_name}\tN{i}\t{300 + i - 1 if i else 101}"
        for i in range(10)
    )
    text = replace_once(text, "\r\n%T\tTASK\r\n", f"\r\n{extra}\r\n%T\tTASK\r\n")
    assert "wbs_too_deep" in problem_codes(text)


def test_a_relationship_to_another_project_is_a_warning_and_is_left_out() -> None:
    text = set_cell(first_text(), "TASKPRED", 4, "pred_proj_id", "9")
    outcome = run(text)
    assert outcome.status == "valid"
    [problem] = outcome.report["problems"]
    assert (problem["severity"], problem["code"]) == ("warning", "external_relationships")
    assert outcome.snapshot is not None and len(outcome.snapshot.tables["relationships"]) == 22


def test_optional_tables_missing_or_partial_are_warnings_not_errors() -> None:
    outcome = run(drop_table(drop_table(first_text(), "UDFTYPE"), "UDFVALUE"))
    assert outcome.status == "valid" and outcome.snapshot is not None
    assert outcome.snapshot.tables["udfs"] == []
    partial = run(drop_table(first_text(), "TASKACTV"))
    assert partial.status == "valid"
    assert codes(partial.report["problems"]) == ["codes_incomplete"]


def test_a_name_over_the_text_limit_is_an_error() -> None:
    long_name = "n" * (limits.MAX_TEXT_CHARS + 1)
    assert problem_codes(set_cell(first_text(), "TASK", 2, "task_name", long_name)) == [
        "text_too_long"
    ]


def test_the_activity_limit_is_a_refusal_not_a_cut(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(limits, "MAX_ACTIVITIES", 20)
    outcome = run(first_text())
    assert outcome.status == "invalid" and codes(outcome.report["problems"]) == [
        "too_many_activities"
    ]


def test_the_report_keeps_a_bounded_list_and_counts_all_problems(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(limits, "MAX_PROBLEMS", 5)
    text = first_text()
    for row in range(1, 22):
        text = set_cell(text, "TASK", row, "early_start_date", "nope")
    report = run(text).report
    assert report["error_count"] == 21 and report["problem_count"] == 21
    assert len(report["problems"]) == 5 and report["truncated"] is True


def test_problems_collector_counts_beyond_its_bound(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(limits, "MAX_PROBLEMS", 2)
    problems = Problems()
    for n in range(4):
        problems.error("x", "m", row=n)
    problems.warn("w", "m")
    assert (problems.errors, problems.warnings, len(problems.kept), problems.truncated) == (
        4,
        1,
        2,
        True,
    )


def test_no_activities_and_no_wbs_are_errors() -> None:
    text = first_text()
    lines = [
        ln
        for ln in text.split("\r\n")
        if not (
            ln.startswith("%R\t")
            and ln.split("\t")[1].startswith("10")
            and len(ln.split("\t")) > 20
        )
    ]
    assert problem_codes("\r\n".join(lines)) == ["no_activities"]
    no_wbs = [
        ln for ln in text.split("\r\n") if not (ln.startswith("%R\t10") and ln.count("\t") == 7)
    ]
    assert "no_wbs" in problem_codes("\r\n".join(no_wbs))


def test_an_invalid_file_carries_no_snapshot_and_no_bundle() -> None:
    outcome = run(drop_table(first_text(), "TASK"))
    assert outcome.snapshot is None and outcome.typed_json is None and outcome.raw_gz is None


def test_running_out_of_memory_is_not_a_bad_file(monkeypatch: pytest.MonkeyPatch) -> None:
    from tl_xer import process as process_module

    def boom(_: bytes) -> None:
        raise MemoryError

    monkeypatch.setattr(process_module, "read_xer", boom)
    with pytest.raises(MemoryError):
        process(encode(first_text()), Options())


def test_analyse_is_a_pure_function_of_the_tables() -> None:
    raw = read_xer(encode(first_text()))
    one, two = Problems(), Problems()
    first = analyse(raw, Options(), one)
    second = analyse(raw, Options(), two)
    assert first is not None and second is not None
    assert first.tables == second.tables and first.project == second.project


def test_the_pair_of_demo_files_differs_only_where_the_scenario_says() -> None:
    first, second = week_pair()
    assert first.data_date != second.data_date
    one, two = run(first_text()).snapshot, run(second_text()).snapshot
    assert one is not None and two is not None
    codes_one = {r[0] for r in one.tables["activities"]}
    codes_two = {r[0] for r in two.tables["activities"]}
    assert codes_one - codes_two == {"A1990"} and codes_two - codes_one == {"A2500"}
