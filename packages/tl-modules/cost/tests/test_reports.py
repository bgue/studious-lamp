"""The cost reports: budget against forecast, and records with no cost code (P1-I4)."""

from __future__ import annotations

from typing import Any

import pytest
from sqlalchemy import text
from tl_adapters.db import open_uow
from tl_core.services.commands import CommandResult, CreateRecord, VoidRecord
from tl_core.services.links import AddLink, RetractLink, handle_add_link, handle_retract_link
from tl_core.services.records import handle_create_record, handle_void_record
from tl_mod_cost import reports
from tl_mod_cost.testing import BASE, CostWorld, row


def make_record(
    world: CostWorld, key: str, *, scope: str | None = None, kind: str = "core.Record"
) -> CommandResult:
    base = {**BASE, **({"scope": scope} if scope else {})}
    with open_uow(world.db) as uow:
        return handle_create_record(uow, CreateRecord(**base, record_type=kind, title=key, key=key))


def link(world: CostWorld, record_id: str, code: str, *, scope: str | None = None) -> str:
    code_id = world.code(code).id
    base = {**BASE, **({"scope": scope} if scope else {})}
    with open_uow(world.db) as uow:
        made = handle_add_link(
            uow, AddLink(**base, from_id=record_id, to_id=code_id, relation="references")
        )
    return made.stream_id


def report(world: CostWorld, **more: Any) -> list[reports.BudgetLine]:
    with open_uow(world.db, readonly=True) as uow:
        return reports.budget_report(uow.conn(), BASE["scope"], **more)


def retract(world: CostWorld, link_id: str) -> None:
    with open_uow(world.db) as uow:
        handle_retract_link(uow, RetractLink(**BASE, link_id=link_id, reason="wrong code"))


def uncoded(
    world: CostWorld, kind: str = "core.Record", scope: str | None = None
) -> list[reports.UncodedRecord]:
    with open_uow(world.db, readonly=True) as uow:
        return reports.records_without_cost_code(uow.conn(), scope or BASE["scope"], kind)


@pytest.fixture
def loaded(world: CostWorld) -> CostWorld:
    world.import_snapshot(
        [
            row("4210", "Piping", quantity_budget=1000, quantity_actual=400, quantity_eac=1100,
                quantity_ftc=700, hours_budget=50),
            row("4210-PIP", "Pipe installation", "4210", uom="in-dia", quantity_budget=600,
                quantity_actual=450, quantity_earned=420, quantity_eac=600),
            row("4210-WLD", "Welding", "4210", quantity_budget=0, quantity_actual=5),
            row("4220", "Supports"),
        ]
    )  # fmt: skip
    return world


def test_each_code_is_judged_on_the_figures_of_one_unit(loaded: CostWorld) -> None:
    lines = {x.code: x for x in report(loaded)}
    piping = lines["4210"]
    assert (piping.budget, piping.actual, piping.ftc, piping.eac) == (1000, 400, 700, 1100)
    assert piping.variance == -100 and piping.over_budget is True and piping.percent_spent == 40.0
    assert piping.earned is None and piping.uom is None
    pipe = lines["4210-PIP"]
    assert (pipe.variance, pipe.over_budget, pipe.percent_spent, pipe.earned) == (
        0,
        False,
        75.0,
        420,
    )
    assert pipe.uom == "in-dia" and pipe.level == 2 and pipe.period == "2026-07"
    hours = {x.code: x for x in report(loaded, unit="hours")}
    assert (hours["4210"].budget, hours["4210"].eac, hours["4210"].variance) == (50, None, None)
    assert hours["4210"].over_budget is False
    money = {x.code: x for x in report(loaded, unit="amount")}
    assert money["4210"].budget is None


def test_a_figure_the_snapshot_did_not_state_is_none_not_zero(loaded: CostWorld) -> None:
    lines = {x.code: x for x in report(loaded)}
    bare = lines["4220"]
    assert (bare.budget, bare.actual, bare.eac, bare.variance, bare.percent_spent) == (
        None,
        None,
        None,
        None,
        None,
    )
    assert bare.over_budget is False


def test_the_percentage_spent_has_one_decimal(world: CostWorld) -> None:
    world.import_snapshot([row("A", quantity_budget=3, quantity_actual=1, quantity_eac=3)])
    [line] = report(world)
    assert line.percent_spent == 33.3


def test_a_zero_budget_has_no_percent_spent(loaded: CostWorld) -> None:
    welding = {x.code: x for x in report(loaded)}["4210-WLD"]
    assert (welding.budget, welding.actual, welding.percent_spent) == (0, 5, None)


def test_the_codes_come_by_code_and_can_be_narrowed(loaded: CostWorld) -> None:
    assert [x.code for x in report(loaded)] == ["4210", "4210-PIP", "4210-WLD", "4220"]
    assert [x.code for x in report(loaded, parent="4210")] == ["4210-PIP", "4210-WLD"]
    assert [x.code for x in report(loaded, over_only=True)] == ["4210"]
    assert [x.code for x in report(loaded, limit=2)] == ["4210", "4210-PIP"]
    assert [x.code for x in report(loaded, limit=0)] == ["4210"]  # at least one


def test_another_unit_than_the_three_is_refused(loaded: CostWorld) -> None:
    with pytest.raises(ValueError, match="unit must be one of hours, quantity, amount"):
        report(loaded, unit="money")


def test_the_records_linked_to_a_code_are_counted_once_each_and_only_while_active(
    loaded: CostWorld,
) -> None:
    first = make_record(loaded, "WELD-1").stream_id
    second = make_record(loaded, "WELD-2").stream_id
    link(loaded, first, "4210-PIP")
    link(loaded, second, "4210-PIP")
    link(loaded, second, "4210")
    counts = {x.code: x.linked_records for x in report(loaded)}
    assert counts == {"4210": 1, "4210-PIP": 2, "4210-WLD": 0, "4220": 0}
    with open_uow(loaded.db) as uow:
        version = (
            uow.conn()
            .execute(
                text("SELECT version FROM cur_core_record WHERE id = :i"),
                {"i": second},
            )
            .scalar_one()
        )
        handle_void_record(
            uow, VoidRecord(**BASE, stream_id=second, expected_version=int(version), reason="x")
        )
    counts = {x.code: x.linked_records for x in report(loaded)}
    assert counts["4210-PIP"] == 1 and counts["4210"] == 0  # a void record is not counted


def test_a_record_with_a_cost_code_is_not_in_the_uncoded_list(loaded: CostWorld) -> None:
    coded = make_record(loaded, "WELD-1").stream_id
    make_record(loaded, "WELD-3")
    make_record(loaded, "WELD-2")
    link(loaded, coded, "4210-PIP")
    assert [r.key for r in uncoded(loaded)] == ["WELD-2", "WELD-3"]
    [first, _] = uncoded(loaded)
    assert (first.record_type, first.title) == ("core.Record", "WELD-2") and len(first.id) == 26


def test_only_the_asked_type_and_only_live_records_are_listed(loaded: CostWorld) -> None:
    make_record(loaded, "WELD-1")
    gone = make_record(loaded, "WELD-9").stream_id
    with open_uow(loaded.db) as uow:
        handle_void_record(
            uow, VoidRecord(**BASE, stream_id=gone, expected_version=1, reason="duplicate")
        )
    assert [r.key for r in uncoded(loaded)] == ["WELD-1"]
    assert uncoded(loaded, kind="core.Other") == []


def test_a_link_to_something_that_is_not_a_cost_code_does_not_code_a_record(
    loaded: CostWorld,
) -> None:
    one = make_record(loaded, "WELD-1").stream_id
    other = make_record(loaded, "NOTE-1").stream_id
    with open_uow(loaded.db) as uow:
        handle_add_link(uow, AddLink(**BASE, from_id=one, to_id=other, relation="references"))
    assert [r.key for r in uncoded(loaded)] == ["NOTE-1", "WELD-1"]


def test_another_project_sees_nothing_of_this_ones_codes_or_records(loaded: CostWorld) -> None:
    make_record(loaded, "WELD-1")
    elsewhere = "project:OTHER"
    make_record(loaded, "WELD-7", scope=elsewhere)
    assert [r.key for r in uncoded(loaded)] == ["WELD-1"]
    assert [r.key for r in uncoded(loaded, scope=elsewhere)] == ["WELD-7"]
    with open_uow(loaded.db, readonly=True) as uow:
        assert reports.budget_report(uow.conn(), elsewhere) == []


def test_a_retracted_link_no_longer_codes_a_record_or_counts(loaded: CostWorld) -> None:
    record = make_record(loaded, "WELD-1").stream_id
    made = link(loaded, record, "4210-PIP")
    assert [r.key for r in uncoded(loaded)] == []
    assert {x.code: x.linked_records for x in report(loaded)}["4210-PIP"] == 1
    retract(loaded, made)
    assert [r.key for r in uncoded(loaded)] == ["WELD-1"]
    assert {x.code: x.linked_records for x in report(loaded)}["4210-PIP"] == 0


def test_the_uncoded_list_is_cut_at_the_limit(loaded: CostWorld) -> None:
    for key in ("WELD-3", "WELD-1", "WELD-2"):
        make_record(loaded, key)
    with open_uow(loaded.db, readonly=True) as uow:
        two = reports.records_without_cost_code(uow.conn(), BASE["scope"], "core.Record", limit=2)
        one = reports.records_without_cost_code(uow.conn(), BASE["scope"], "core.Record", limit=0)
    assert [r.key for r in two] == ["WELD-1", "WELD-2"] and [r.key for r in one] == ["WELD-1"]
