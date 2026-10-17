"""The difference between two derived tables (P1-I3 T06). No database."""

from __future__ import annotations

from tl_mod_documents.derivation.diff import MAX_LISTED, DerivedDiff, diff_rows

COLS = ["tag", "service", "size"]


def table(*rows: tuple[str | None, str | None, str | None]) -> list[dict[str, str | None]]:
    return [dict(zip(COLS, r, strict=True)) for r in rows]


OLD = table(
    ("A-1", "Feed", "4"),
    ("A-2", "Return", "6"),
    ("A-3", "Vent", None),
)


def test_two_equal_tables_have_no_difference() -> None:
    result = diff_rows(COLS, OLD, COLS, [dict(r) for r in OLD], "tag")
    assert (result.added, result.removed, result.changed) == ([], [], [])
    assert (result.added_count, result.removed_count, result.changed_count) == (0, 0, 0)
    assert result.unchanged_count == 3 and result.key_column == "tag" and not result.truncated


def test_added_removed_and_changed_rows() -> None:
    new = table(("A-1", "Feed", "4"), ("A-2", "Return line", "8"), ("A-4", "Drain", "2"))
    result = diff_rows(COLS, OLD, COLS, new, "tag")
    assert result.added == ["A-4"] and result.removed == ["A-3"]
    (change,) = result.changed
    assert change.key == "A-2"
    assert [(f.column, f.old, f.new) for f in change.fields] == [
        ("service", "Return", "Return line"),
        ("size", "6", "8"),
    ]
    assert (result.added_count, result.removed_count, result.changed_count) == (1, 1, 1)
    assert result.unchanged_count == 1


def test_added_and_changed_follow_the_new_table_and_removed_the_old_one() -> None:
    old = table(("C", None, None), ("A", None, None), ("B", None, None))
    new = table(("Z", None, None), ("A", "x", None), ("Y", None, None), ("B", "y", None))
    result = diff_rows(COLS, old, COLS, new, "tag")
    assert result.added == ["Z", "Y"]
    assert [c.key for c in result.changed] == ["A", "B"]
    assert result.removed == ["C"]


def test_cells_are_compared_trimmed_and_an_empty_cell_equals_a_missing_one() -> None:
    old = [{"tag": "A", "service": "Feed ", "size": ""}]
    new = [{"tag": " A", "service": "Feed", "size": None}]
    result = diff_rows(COLS, old, COLS, new, "tag")
    assert result.changed_count == 0 and result.unchanged_count == 1


def test_a_value_that_appears_or_disappears_is_a_change_with_none() -> None:
    old = table(("A", "Feed", None))
    new = table(("A", None, "4"))
    (change,) = diff_rows(COLS, old, COLS, new, "tag").changed
    assert [(f.column, f.old, f.new) for f in change.fields] == [
        ("service", "Feed", None),
        ("size", None, "4"),
    ]


def test_columns_that_one_table_has_and_the_other_has_not() -> None:
    old = [{"tag": "A", "service": "Feed", "legacy": "x"}]
    new = [{"tag": "A", "service": "Feed", "size": "4"}]
    result = diff_rows(["tag", "service", "legacy"], old, ["tag", "service", "size"], new, "tag")
    assert result.columns_added == ["size"] and result.columns_removed == ["legacy"]
    (change,) = result.changed
    assert [(f.column, f.old, f.new) for f in change.fields] == [
        ("size", None, "4"),
        ("legacy", "x", None),
    ]


def test_a_repeated_key_is_judged_by_its_first_row_and_listed() -> None:
    old = table(("A", "Feed", None))
    new = table(("A", "Feed", None), ("A", "Other", None), ("B", None, None), ("B", None, None))
    result = diff_rows(COLS, old, COLS, new, "tag")
    assert result.duplicate_keys == ["A", "B"]
    assert result.changed_count == 0 and result.added == ["B"]


def test_rows_with_an_empty_key_take_no_part_and_are_counted() -> None:
    old = table((None, "x", None), ("A", None, None))
    new = table(("", "y", None), ("  ", "z", None), ("A", None, None))
    result = diff_rows(COLS, old, COLS, new, "tag")
    assert result.blank_key_rows == 3
    assert (result.added, result.removed, result.changed) == ([], [], [])
    assert result.unchanged_count == 1


def test_a_missing_key_column_means_no_row_has_a_key() -> None:
    result = diff_rows(["a"], [{"a": "1"}], ["a"], [{"a": "2"}], "tag")
    assert result.blank_key_rows == 2 and result.unchanged_count == 0


def test_the_lists_are_capped_and_the_counts_are_not() -> None:
    new = [{"tag": f"T{i:05d}"} for i in range(MAX_LISTED + 7)]
    result = diff_rows(["tag"], [], ["tag"], new, "tag")
    assert len(result.added) == MAX_LISTED and result.added_count == MAX_LISTED + 7
    assert result.truncated is True
    assert result.added[0] == "T00000"


def test_the_diff_round_trips_through_json_and_leaves_its_input_alone() -> None:
    old, new = [dict(r) for r in OLD], table(("A-1", "Feed", "5"))
    result = diff_rows(COLS, old, COLS, new, "tag")
    assert DerivedDiff.model_validate_json(result.model_dump_json()) == result
    assert old == OLD
    assert new == table(("A-1", "Feed", "5"))
