"""ImportCostSnapshot: the snapshot, its codes, the matrix and the history (P1-I4-T02, ADR-0015)."""

from __future__ import annotations

from typing import Any

import pytest
from pydantic import ValidationError
from tl_adapters.db import open_uow
from tl_core.services.errors import ServiceError
from tl_mod_cost.errors import CostImportRefusedError, CostScopeError, InvalidCostSnapshotError
from tl_mod_cost.handlers.snapshots import ImportCostSnapshot, handle_import_cost_snapshot
from tl_mod_cost.imports.model import CostRow
from tl_mod_cost.imports.plan import plan_import
from tl_mod_cost.limits import MAX_DEPTH
from tl_mod_cost.testing import BASE, CostWorld, row


def september() -> list[CostRow]:
    return [
        row("4210", "Piping", hours_budget=1000, hours_actual=400, amount_budget=80000),
        row("4210-PIP", "Pipe installation", "4210", uom="in-dia", hours_budget=600),
        row(
            "4210-PIP-WLD",
            "Pipe welding",
            "4210-PIP",
            uom="in-dia",
            hours_budget=300,
            hours_actual=120.5,
        ),
        row("4300", "Electrical", hours_budget=500),
    ]


def test_a_first_snapshot_creates_the_snapshot_and_every_code(world: CostWorld) -> None:
    result = world.import_snapshot(september(), currency="USD", source_name="cost-2026-07.csv")
    assert result.key == "2026-07@1"
    [snap] = world.snapshots()
    assert (snap.period, snap.revision, snap.as_of, snap.currency) == (
        "2026-07",
        1,
        "2026-07-31",
        "USD",
    )
    assert (snap.row_count, snap.new_code_count, snap.revised_code_count) == (4, 4, 0)
    assert snap.source_name == "cost-2026-07.csv"
    welding = world.code("4210-PIP-WLD")
    assert (welding.parent_code, welding.level, welding.uom, welding.title) == (
        "4210-PIP",
        3,
        "in-dia",
        "Pipe welding",
    )
    assert welding.figures["hours_budget"] == 300.0 and welding.figures["hours_actual"] == 120.5
    assert welding.figures["hours_earned"] is None  # not stated: null, never zero
    assert (welding.period, welding.as_of, welding.snapshot_id) == (
        "2026-07",
        "2026-07-31",
        result.stream_id,
    )
    assert world.code("4210").level == 1 and world.code("4300").parent_code is None


def test_a_code_without_a_description_is_titled_with_its_code(world: CostWorld) -> None:
    world.import_snapshot([row("9000")])
    assert world.code("9000").title == "9000"


def test_every_event_of_an_import_carries_one_correlation_id(world: CostWorld) -> None:
    result = world.import_snapshot(september())
    assert len({e.correlation_id for e in result.events}) == 1
    types = [e.event_type for e in result.events]
    assert types.count("Record.Created") == 5 and types.count("CostCode.MeasuresRecorded") == 4
    assert types.count("CostCode.Defined") == 4 and types.count("CostSnapshot.Defined") == 1


def test_the_next_period_replaces_the_matrix_and_keeps_the_history(world: CostWorld) -> None:
    world.import_snapshot(september())
    world.import_snapshot(
        [row("4210-PIP-WLD", hours_budget=320, hours_actual=200)],
        period="2026-08",
        as_of="2026-08-31",
    )
    welding = world.code("4210-PIP-WLD")
    assert (welding.period, welding.as_of) == ("2026-08", "2026-08-31")
    assert welding.figures["hours_budget"] == 320.0 and welding.figures["hours_actual"] == 200.0
    assert welding.figures["amount_budget"] is None  # the later snapshot stated no amount
    history = world.history("4210-PIP-WLD")
    assert [(h.period, h.figures["hours_actual"]) for h in history] == [
        ("2026-07", 120.5),
        ("2026-08", 200.0),
    ]
    assert world.code("4300").period == "2026-07"  # a code the file did not name keeps its matrix


def test_a_snapshot_imported_late_adds_history_and_leaves_the_matrix(world: CostWorld) -> None:
    world.import_snapshot(september(), period="2026-07", as_of="2026-07-31")
    world.import_snapshot([row("4300", hours_budget=111)], period="2026-05", as_of="2026-05-31")
    assert (
        world.code("4300").period == "2026-07"
        and world.code("4300").figures["hours_budget"] == 500.0
    )
    assert [h.period for h in world.history("4300")] == ["2026-05", "2026-07"]


def test_a_second_import_of_a_period_is_the_next_revision(world: CostWorld) -> None:
    world.import_snapshot(september())
    again = world.import_snapshot([row("4300", hours_budget=510)])
    assert again.key == "2026-07@2"
    assert [(s.period, s.revision) for s in world.snapshots()] == [("2026-07", 2), ("2026-07", 1)]
    assert world.code("4300").figures["hours_budget"] == 510.0  # the same as-of: the later wins


def test_a_changed_description_or_unit_is_a_revision_of_the_code(world: CostWorld) -> None:
    world.import_snapshot(september())
    second = world.import_snapshot(
        [row("4210-PIP", "Pipe installation, shop and field", uom="m"), row("4300", "Electrical")],
        period="2026-08",
        as_of="2026-08-31",
    )
    pipe = world.code("4210-PIP")
    assert (pipe.title, pipe.uom) == ("Pipe installation, shop and field", "m")
    types = [e.event_type for e in second.events]
    assert types.count("CostCode.Revised") == 1 and types.count("Record.Updated") == 1
    [snap] = [s for s in world.snapshots() if s.period == "2026-08"]
    assert (snap.new_code_count, snap.revised_code_count, snap.row_count) == (0, 1, 2)
    assert world.code("4300").title == "Electrical"


def test_a_row_that_states_nothing_new_changes_no_code(world: CostWorld) -> None:
    world.import_snapshot(september())
    again = world.import_snapshot(
        [row("4210-PIP", "Pipe installation", "4210", uom="in-dia")],
        period="2026-08",
        as_of="2026-08-31",
    )
    assert "CostCode.Revised" not in [e.event_type for e in again.events]


def test_the_figures_of_a_code_are_kept_exactly(world: CostWorld) -> None:
    world.import_snapshot([row("1", amount_budget=1234567.89, hours_ftc=-12.5, quantity_eac=0)])
    figures = world.code("1").figures
    assert figures["amount_budget"] == 1234567.89 and figures["hours_ftc"] == -12.5
    assert figures["quantity_eac"] == 0.0  # a stated zero is a zero


# --- refusals ------------------------------------------------------------------------------


def refused(world: CostWorld, rows: list[CostRow], **more: Any) -> CostImportRefusedError:
    with pytest.raises(CostImportRefusedError) as caught:
        world.import_snapshot(rows, **more)
    return caught.value


def test_a_code_that_appears_twice_is_refused_naming_it(world: CostWorld) -> None:
    error = refused(world, [row("1"), row("1")])
    assert any("1: the code appears twice" in i for i in error.issues)


def test_a_parent_that_is_nowhere_is_refused(world: CostWorld) -> None:
    error = refused(world, [row("1", parent="nope")])
    assert any("parent nope is neither in the file nor a known code" in i for i in error.issues)


def test_a_parent_may_come_later_in_the_file_or_be_known_already(world: CostWorld) -> None:
    world.import_snapshot([row("child", parent="top"), row("top")])
    assert world.code("child").level == 2
    world.import_snapshot([row("grandchild", parent="child")], period="2026-08", as_of="2026-08-31")
    assert world.code("grandchild").level == 3


def test_a_loop_and_a_code_that_is_its_own_parent_are_refused(world: CostWorld) -> None:
    assert any("own parent" in i for i in refused(world, [row("a", parent="a")]).issues)
    loop = refused(world, [row("a", parent="b"), row("b", parent="a")])
    assert any("loops" in i for i in loop.issues)


def test_a_hierarchy_deeper_than_the_limit_is_refused(world: CostWorld) -> None:
    chain = [row("c0")] + [row(f"c{i}", parent=f"c{i - 1}") for i in range(1, MAX_DEPTH + 2)]
    assert any("deeper" in i for i in refused(world, chain).issues)


def test_moving_a_mirrored_code_is_refused(world: CostWorld) -> None:
    world.import_snapshot(september())
    error = refused(world, [row("4210-PIP", parent="4300")], period="2026-08", as_of="2026-08-31")
    assert any("moving a mirrored code is not supported" in i for i in error.issues)


def test_a_refused_import_leaves_nothing_behind(world: CostWorld) -> None:
    before = world.scalar("SELECT COUNT(*) FROM cur_core_record")
    refused(world, [row("ok"), row("bad", parent="missing")])
    assert world.scalar("SELECT COUNT(*) FROM cur_core_record") == before
    assert world.scalar("SELECT COUNT(*) FROM cur_cost_snapshot_value") == 0


@pytest.mark.parametrize(
    "as_of", ["2999-01-01", "2026-13-01", "26-09-30", "2026-07-3x", "1900-01-01"]
)
def test_an_as_of_date_that_is_not_usable_is_refused(world: CostWorld, as_of: str) -> None:
    with pytest.raises((InvalidCostSnapshotError, ValidationError)):
        world.import_snapshot([row("1")], as_of=as_of)


@pytest.mark.parametrize("period", ["2026-9", "2026-13", "2026-00", "202609", "2026-07-01"])
def test_a_period_must_be_a_year_and_a_month(world: CostWorld, period: str) -> None:
    with pytest.raises(ValidationError):
        world.import_snapshot([row("1")], period=period)


def test_the_company_scope_cannot_hold_cost_codes(world: CostWorld) -> None:
    command = ImportCostSnapshot(
        actor="user:u",
        source="test",
        scope="company",
        period="2026-07",
        as_of="2026-07-31",
        rows=[row("1")],
    )
    with open_uow(world.db) as uow, pytest.raises(CostScopeError):
        handle_import_cost_snapshot(uow, command)


def test_the_command_bounds_its_input() -> None:
    base: dict[str, Any] = {**BASE, "period": "2026-07", "as_of": "2026-07-31"}
    with pytest.raises(ValidationError):
        ImportCostSnapshot(**base, rows=[])
    with pytest.raises(ValidationError):
        ImportCostSnapshot(**base, rows=[row("1")], currency="usd")
    with pytest.raises(ValidationError):
        ImportCostSnapshot(**base, rows=[row("1")], source_sha256="XYZ" * 22)
    with pytest.raises(ValidationError):
        ImportCostSnapshot(**base, rows=[row("1")], source_name="a\x07b")
    with pytest.raises(ValidationError):
        ImportCostSnapshot(**{**base, "surprise": 1}, rows=[row("1")])
    with pytest.raises(ValidationError):
        ImportCostSnapshot(**base, rows=[row("1\x00")])


@pytest.mark.parametrize(
    "bad",
    [
        {"code": "a@b"},
        {"code": " a"},
        {"code": ""},
        {"code": "a" * 65},
        {"code": "a", "uom": "u" * 21},
        {"code": "a", "description": "d" * 501},
        {"code": "a", "figures": {"hours_budget": float("inf")}},
        {"code": "a", "figures": {"hours_budget": float("nan")}},
        {"code": "a", "figures": {"hours_budget": 1e16}},
        {"code": "a", "figures": {"hours_nonsense": 1.0}},
        {"code": "a", "surprise": 1},
    ],
)
def test_a_row_is_bounded(bad: dict[str, Any]) -> None:
    with pytest.raises(ValidationError):
        CostRow(**bad)


def test_generic_commands_cannot_change_a_cost_code(world: CostWorld) -> None:
    from tl_core.services.commands import UpdateRecord
    from tl_core.services.records import handle_update_record

    world.import_snapshot(september())
    code = world.code("4210")
    command = UpdateRecord(**BASE, stream_id=code.id, expected_version=3, changes={"title": "Mine"})
    with open_uow(world.db) as uow, pytest.raises(ServiceError, match="UpdateRecord"):
        handle_update_record(uow, command)


# --- the plan ------------------------------------------------------------------------------


def test_the_plan_reads_and_writes_nothing(world: CostWorld) -> None:
    world.import_snapshot(september())
    count = world.scalar("SELECT COUNT(*) FROM cur_core_record")
    with open_uow(world.db, readonly=True) as uow:
        plan = plan_import(
            uow.conn(),
            BASE["scope"],
            [row("4300", "Electrical works"), row("5000", "Civil"), row("4210")],
        )
    assert [c.row.code for c in plan.new] == ["5000"]
    assert [(c.row.code, sorted(c.changes)) for c in plan.revised] == [("4300", ["title"])]
    assert plan.unchanged == 1 and plan.issues == ()
    assert world.scalar("SELECT COUNT(*) FROM cur_core_record") == count


def test_the_plan_puts_parents_before_children() -> None:
    from sqlalchemy import create_engine

    engine = create_engine("sqlite://")
    with engine.begin() as conn:
        conn.exec_driver_sql(
            "CREATE TABLE cur_cost_costcode "
            "(id TEXT, scope TEXT, code TEXT, parent_code TEXT, level INTEGER, uom TEXT)"
        )
        conn.exec_driver_sql("CREATE TABLE cur_core_record (id TEXT, title TEXT)")
        plan = plan_import(
            conn, "project:P", [row("c", parent="b"), row("b", parent="a"), row("a"), row("z")]
        )
    assert [c.row.code for c in plan.codes] == ["a", "z", "b", "c"]
    assert [c.level for c in plan.codes] == [1, 1, 2, 3]
