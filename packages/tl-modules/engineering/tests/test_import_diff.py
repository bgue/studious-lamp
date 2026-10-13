"""Comparing a tag list with the project's tags: ``plan_import`` (P1-I1-T10b)."""

from __future__ import annotations

from typing import Any

import pytest
from tl_mod_engineering.imports.diff import plan_import, row_changes, same_value
from tl_mod_engineering.imports.model import ExistingTag, FieldChange, ImportPlan, ImportRow


def tag(number: str, **more: Any) -> ExistingTag:
    fields: dict[str, Any] = {
        "id": f"id-{number}",
        "number": number,
        "class_code": "ControlValve",
        "service": "Feed gas",
        "psets": {"valve_data": {"size_in": 4, "manufacturer": "Acme", "x": {"fat_by": "Jo"}}},
        "version": 2,
    }
    fields.update(more)
    return ExistingTag(**fields)


def row(number: str, line: int = 2, **more: Any) -> ImportRow:
    fields: dict[str, Any] = {
        "line": line,
        "number": number,
        "class_code": None,
        "service": None,
        "psets": {},
    }
    fields.update(more)
    return ImportRow(**fields)


# --- same_value ----------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("old", "new", "expected"),
    [
        (4, 4.0, True),
        (4, 4.5, False),
        ("a", "a", True),
        ("4", 4, False),
        (True, True, True),
        (True, 1, False),
        (0, False, False),
        (False, False, True),
        ([1, 2], [1, 2], True),
        ({"a": 1}, {"a": 2}, False),
    ],
)
def test_same_value(old: Any, new: Any, expected: bool) -> None:
    assert same_value(old, new) is expected


# --- one row against one tag ---------------------------------------------------------------------


def test_a_row_that_states_nothing_new_changes_nothing() -> None:
    same = row(
        "T-1",
        class_code="ControlValve",
        service="Feed gas",
        psets={"valve_data": {"size_in": 4.0, "manufacturer": "Acme", "x.fat_by": "Jo"}},
    )
    assert row_changes(same, tag("T-1")) == []


def test_unset_fields_of_the_row_leave_the_tag_alone() -> None:
    assert row_changes(row("T-1"), tag("T-1")) == []


def test_changes_come_in_a_fixed_order_with_old_and_new() -> None:
    changed = row(
        "T-1",
        class_code="ManualValve",
        service="Fuel gas",
        psets={
            "valve_data": {"size_in": 6.0, "manufacturer": "Acme", "x.fat_by": "Al"},
            "safety_data": {"sil_rating": 2},
        },
    )
    assert row_changes(changed, tag("T-1")) == [
        FieldChange("class", "ControlValve", "ManualValve"),
        FieldChange("service", "Feed gas", "Fuel gas"),
        FieldChange("psets.safety_data.sil_rating", None, 2),
        FieldChange("psets.valve_data.size_in", 4, 6.0),
        FieldChange("psets.valve_data.x.fat_by", "Jo", "Al"),
    ]


def test_a_value_the_tag_lacks_is_a_change_even_when_it_is_falsy() -> None:
    changes = row_changes(
        row("T-1", psets={"valve_data": {"vendor": 0, "flag": False}}), tag("T-1")
    )
    assert changes == [
        FieldChange("psets.valve_data.flag", None, False),
        FieldChange("psets.valve_data.vendor", None, 0),
    ]


def test_a_tag_without_a_class_gets_the_class_from_the_row() -> None:
    changes = row_changes(row("T-1", class_code="Pump"), tag("T-1", class_code=None))
    assert changes == [FieldChange("class", None, "Pump")]


# --- the whole plan ------------------------------------------------------------------------------


def test_new_changed_unchanged_and_removed_are_told_apart() -> None:
    existing = [tag("T-1"), tag("T-2"), tag("T-9"), tag("T-3")]
    rows = [
        row("T-2", 2, service="Fuel gas"),
        row("T-1", 3),
        row("T-4", 4, class_code="Pump"),
        row("T-3", 5, class_code="ControlValve"),
    ]
    plan = plan_import(rows, existing)
    assert [r.number for r in plan.new] == ["T-4"]
    assert [(c.line, c.number, c.tag_id) for c in plan.changed] == [(2, "T-2", "id-T-2")]
    assert plan.changed[0].changes == [FieldChange("service", "Feed gas", "Fuel gas")]
    assert plan.unchanged == ["T-1", "T-3"]
    assert [t.number for t in plan.removed] == ["T-9"]
    assert plan.invalid == []
    assert plan.counts() == {"new": 1, "changed": 1, "unchanged": 2, "removed": 1, "invalid": 0}


def test_an_empty_file_removes_everything_and_an_empty_project_gets_everything() -> None:
    assert [t.number for t in plan_import([], [tag("B"), tag("A")]).removed] == ["A", "B"]
    plan = plan_import([row("A"), row("B", 3)], [])
    assert [r.number for r in plan.new] == ["A", "B"] and plan.removed == []


def test_a_row_with_problems_is_invalid_and_its_tag_is_not_removed() -> None:
    bad = row("T-1", 2, problems=["SIZE (IN): 'wide' is not a valid decimal"])
    plan = plan_import([bad], [tag("T-1")])
    assert plan.invalid == [bad]
    assert plan.new == [] and plan.changed == [] and plan.unchanged == []
    assert plan.removed == []  # the file does mention it


def test_a_row_without_a_number_is_invalid_and_removes_nothing() -> None:
    blank = row("", 2, problems=["the tag number is blank"])
    plan = plan_import([blank], [tag("T-1")])
    assert plan.invalid == [blank]
    assert [t.number for t in plan.removed] == ["T-1"]


def test_a_repeated_number_is_invalid_from_its_second_row() -> None:
    first, second, third = row("T-4", 2), row("T-4", 7, service="again"), row("T-4", 9)
    plan = plan_import([first, second, third], [])
    assert plan.new == [first]
    assert [(r.line, r.problems) for r in plan.invalid] == [
        (7, ["duplicate of row 2"]),
        (9, ["duplicate of row 2"]),
    ]
    assert plan.invalid[0].service == "again"


def test_a_repeated_existing_number_is_judged_on_its_first_row() -> None:
    plan = plan_import([row("T-1", 2, service="Fuel gas"), row("T-1", 3)], [tag("T-1")])
    assert [c.number for c in plan.changed] == ["T-1"] and len(plan.invalid) == 1


def test_a_plan_reports_its_counts_and_starts_empty() -> None:
    assert ImportPlan().counts() == {
        "new": 0,
        "changed": 0,
        "unchanged": 0,
        "removed": 0,
        "invalid": 0,
    }


def test_a_number_an_ended_tag_holds_is_invalid_not_new() -> None:
    plan = plan_import(
        [row("47-FV-1001"), row("47-FV-1002", line=3), row("47-FV-1003", line=4)],
        [tag("47-FV-1002")],
        ended={"47-FV-1001": "Superseded", "47-FV-1003": "Deleted"},
    )
    assert [(r.number, r.problems) for r in plan.invalid] == [
        ("47-FV-1001", ["key '47-FV-1001' is already used by a superseded tag"]),
        ("47-FV-1003", ["key '47-FV-1003' is already used by a deleted tag"]),
    ]
    assert plan.new == [] and plan.unchanged == ["47-FV-1002"]
    # a number in service wins over a stale ended entry, and no ``ended`` is the old behaviour
    assert (
        plan_import(
            [row("47-FV-1002")], [tag("47-FV-1002")], ended={"47-FV-1002": "Deleted"}
        ).invalid
        == []
    )
    assert [r.number for r in plan_import([row("47-FV-1001")], []).new] == ["47-FV-1001"]
