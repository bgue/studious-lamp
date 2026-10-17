"""``build_table``: headers, rows and profiles from a raw grid (P1-I3B-S1)."""

from __future__ import annotations

import pytest
from extractsupport import grid_of
from tl_core.derivation import MAX_CELL_CHARS, MAX_COLUMNS, MAX_ROWS
from tl_extract.options import TableOptions
from tl_extract.reading import MAX_CELLS, MAX_HEADER_CHARS, MAX_PROBLEMS, RawGrid, Refusal
from tl_extract.table import build_table, match_key, snake_case

OPTIONS = TableOptions()


def refusal(grid: RawGrid, options: TableOptions = OPTIONS) -> Refusal:
    with pytest.raises(Refusal) as caught:
        build_table(grid, options)
    return caught.value


def test_a_header_and_rows_become_columns_and_rows_in_order() -> None:
    table = build_table(
        grid_of(["Tag", "Service"], ["47-FV-1001", "Feed gas"], ["47-FV-1002", None]), OPTIONS
    )
    assert table.columns == ["Tag", "Service"]
    assert table.rows == [
        {"Tag": "47-FV-1001", "Service": "Feed gas"},
        {"Tag": "47-FV-1002", "Service": None},
    ]
    assert table.problems == [] and table.notes == []


def test_cells_are_stripped_and_blank_cells_are_none() -> None:
    table = build_table(grid_of([" A ", "B"], ["  x  ", "   "], [None, "y"]), OPTIONS)
    assert table.columns == ["A", "B"]
    assert table.rows == [{"A": "x", "B": None}, {"A": None, "B": "y"}]


def test_header_whitespace_is_collapsed() -> None:
    table = build_table(grid_of(["TAG   NO", "P&ID\t(rev)"], ["a", "b"]), OPTIONS)
    assert table.columns == ["TAG NO", "P&ID (rev)"]


def test_a_short_row_is_padded_with_none() -> None:
    table = build_table(grid_of(["A", "B", "C"], ["1"]), OPTIONS)
    assert table.rows == [{"A": "1", "B": None, "C": None}]


def test_blank_rows_are_skipped_and_counted_and_rows_are_numbered_without_them() -> None:
    grid = grid_of(["A"], [None], ["1"], [" "], ["2\x01"])
    grid.skipped_blank_rows = 3
    table = build_table(grid, OPTIONS)
    assert [r["A"] for r in table.rows] == ["1", None]
    assert table.notes == ["skipped 5 blank row(s)"]
    assert [(p.code, p.row) for p in table.problems] == [("control_character", 2)]


def test_a_control_character_leaves_the_cell_empty_and_is_a_problem_of_its_row() -> None:
    table = build_table(grid_of(["A", "B"], ["ok", "bad\x00cell"], ["x\x07", "fine\tTab"]), OPTIONS)
    assert table.rows == [{"A": "ok", "B": None}, {"A": None, "B": "fine\tTab"}]
    assert [(p.code, p.row) for p in table.problems] == [
        ("control_character", 1),
        ("control_character", 2),
    ]
    assert "B" in table.problems[0].message


def test_a_lone_surrogate_is_unstorable_too() -> None:
    table = build_table(grid_of(["A"], ["a\ud800b"]), OPTIONS)
    assert table.rows == [{"A": None}]
    assert table.problems[0].code == "control_character"


def test_blank_header_cells_are_ignored_and_their_data_is_a_problem_of_the_row() -> None:
    table = build_table(
        grid_of(["A", None, "C", ""], ["1", "2", "3", None], ["4", None, "6"]), OPTIONS
    )
    assert table.columns == ["A", "C"]
    assert table.rows == [{"A": "1", "C": "3"}, {"A": "4", "C": "6"}]
    assert [(p.code, p.row) for p in table.problems] == [("extra_cells", 1)]
    assert table.notes == ["ignored 1 unnamed column(s) at position(s) 2"]


def test_data_past_the_last_header_cell_is_a_problem_of_the_row() -> None:
    table = build_table(grid_of(["A"], ["1", "2"]), OPTIONS)
    assert table.rows == [{"A": "1"}]
    assert [(p.code, p.row) for p in table.problems] == [("extra_cells", 1)]


def test_a_column_twice_refuses_the_file_naming_it() -> None:
    error = refusal(grid_of(["A", "B", "A"], ["1", "2", "3"]))
    assert error.code == "duplicate_header"
    assert error.message == "the file has a column twice: A"


def test_headers_that_differ_only_in_blank_space_are_the_same_column() -> None:
    assert refusal(grid_of(["Tag No", "Tag  No"], ["1", "2"])).code == "duplicate_header"


def test_duplicate_headers_can_be_suffixed() -> None:
    table = build_table(
        grid_of(["A", "A", "A_2", "A"], ["1", "2", "3", "4"]),
        TableOptions(duplicate_headers="suffix"),
    )
    assert table.columns == ["A", "A_3", "A_2", "A_4"]
    assert table.rows == [{"A": "1", "A_3": "2", "A_2": "3", "A_4": "4"}]
    assert table.notes == ["duplicate headers renamed: A -> A_3; A -> A_4"]


def test_header_hints_rename_columns_loosely_and_exactly() -> None:
    options = TableOptions(header_map={"TAG NO": "tag_number", "size (in)": "size_in"})
    table = build_table(grid_of(["Tag No.", "SIZE  (IN)", "Other"], ["a", "b", "c"]), options)
    assert table.columns == ["tag_number", "size_in", "Other"]
    assert table.notes == ["header hints applied: Tag No. -> tag_number; SIZE (IN) -> size_in"]


def test_hints_can_make_two_columns_collide_and_that_is_a_duplicate() -> None:
    options = TableOptions(header_map={"Tag": "number", "Number": "number"})
    assert refusal(grid_of(["Tag", "Number"], ["1", "2"]), options).code == "duplicate_header"


def test_normalise_headers_writes_snake_case_except_where_a_hint_named_the_column() -> None:
    options = TableOptions(normalise_headers=True, header_map={"P&ID": "pid"})
    table = build_table(
        grid_of(["TAG NO", "SIZE (IN)", "P&ID", "???"], ["a", "b", "c", "d"]), options
    )
    assert table.columns == ["tag_no", "size_in", "pid", "???"]


def test_match_key_and_snake_case() -> None:
    assert match_key("  Tag No.  ") == "tag_no"
    assert match_key("SIZE (IN)") == "size_in"
    assert match_key("a__b--c") == "a_b_c"
    assert match_key("Größe") == "größe"
    assert snake_case("???") == "???"


def test_header_row_skips_the_rows_above_it() -> None:
    grid = grid_of(["Instrument index", None], ["A", "B"], ["1", "2"])
    table = build_table(grid, TableOptions(header_row=2))
    assert table.columns == ["A", "B"] and table.rows == [{"A": "1", "B": "2"}]


def test_a_header_row_past_the_end_is_refused() -> None:
    assert refusal(grid_of(["A"], ["1"]), TableOptions(header_row=3)).code == "no_header"
    assert refusal(grid_of([None, None]), OPTIONS).code == "no_header"
    assert refusal(grid_of(), OPTIONS).code == "no_header"


def test_a_header_with_a_control_character_or_far_too_long_is_refused() -> None:
    assert refusal(grid_of(["A", "B\x00"], ["1", "2"])).code == "bad_header"
    assert refusal(grid_of(["x" * (MAX_HEADER_CHARS + 1)], ["1"])).code == "bad_header"


def test_too_many_columns_is_refused_and_exactly_the_limit_is_not() -> None:
    assert build_table(grid_of([f"c{i}" for i in range(MAX_COLUMNS)], []), OPTIONS)
    error = refusal(grid_of([f"c{i}" for i in range(MAX_COLUMNS + 1)], []))
    assert error.code == "too_many_columns"


def test_too_many_rows_is_refused_and_exactly_the_limit_is_not() -> None:
    header = ["A"]
    assert len(build_table(grid_of(header, *[["x"]] * MAX_ROWS), OPTIONS).rows) == MAX_ROWS
    assert refusal(grid_of(header, *[["x"]] * (MAX_ROWS + 1))).code == "too_many_rows"


def test_a_cell_over_the_limit_refuses_the_file_and_names_the_row() -> None:
    assert build_table(grid_of(["A"], ["x" * MAX_CELL_CHARS]), OPTIONS).rows
    error = refusal(grid_of(["A"], ["ok"], ["x" * (MAX_CELL_CHARS + 1)]))
    assert (error.code, error.row) == ("cell_too_long", 2)
    assert "x" * 50 not in error.message


def test_too_many_cells_is_refused() -> None:
    columns = 100
    rows = MAX_CELLS // columns + 1
    grid = grid_of([f"c{i}" for i in range(columns)], *[["x"] * columns] * rows)
    assert refusal(grid).code == "too_many_cells"


def test_problems_are_listed_up_to_a_limit_and_the_rest_counted() -> None:
    grid = grid_of(["A"], *[["\x01"]] * (MAX_PROBLEMS + 5))
    table = build_table(grid, OPTIONS)
    assert len(table.problems) == MAX_PROBLEMS + 1
    assert (table.problems[-1].code, table.problems[-1].message) == (
        "more_problems",
        "5 more problem(s) are not listed",
    )


def test_profiles_count_non_empty_distinct_longest_and_five_samples() -> None:
    rows = [["CV"], ["CV"], ["HV"], [None], ["PSV"], ["XMTR"], ["CTRL"], ["PMP"]]
    table = build_table(grid_of(["TYPE"], *rows), OPTIONS)
    (profile,) = table.profiles
    assert profile.name == "TYPE"
    assert (profile.non_empty, profile.distinct, profile.max_length) == (7, 6, 4)
    assert profile.samples == ["CV", "HV", "PSV", "XMTR", "CTRL"]


def test_a_table_without_data_rows_says_so() -> None:
    table = build_table(grid_of(["A", "B"]), OPTIONS)
    assert table.rows == [] and table.notes == ["the table has no data rows"]
    assert [p.non_empty for p in table.profiles] == [0, 0]


def test_a_readers_notes_come_first() -> None:
    grid = grid_of(["A"], ["1"])
    grid.notes = ["delimiter detected: semicolon"]
    assert build_table(grid, OPTIONS).notes == ["delimiter detected: semicolon"]
