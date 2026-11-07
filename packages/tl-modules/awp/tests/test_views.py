"""The read views (T10, T10b, T10c, T05g): fields, filters, the requires-link path, hidden refs."""

from __future__ import annotations

from collections.abc import Callable, Iterator
from contextlib import contextmanager
from decimal import Decimal
from typing import Any

import pytest
from awp_world import SCOPE, World
from sqlalchemy import Connection
from tl_adapters.db import open_uow
from tl_core.services.links import AddLink, handle_add_link
from tl_mod_awp import views

WLD, ERC, CON = "4210-PIP-WLD", "4210-PIP-ERC", "4210-CIV-CON"
NUMBERS = [
    "P123-CWP-CIV-0001",
    "P123-CWP-CIV-0002",
    "P123-CWP-PIP-0001",
    "P123-CWP-PIP-0002",
    "P123-CWP-PIP-0003",
    "P123-CWP-PIP-0004",
]


def read(w: World, fn: Callable[..., Any], *args: Any, **kw: Any) -> Any:
    with open_uow(w.db, readonly=True) as uow:
        return fn(uow.conn(), SCOPE, *args, **kw)


@contextmanager
def hiding(*ids: str) -> Iterator[None]:
    """Patch ``views._hidden`` so the given record ids read as hidden (D22: no awp or cost record
    has a class, so a hidden one is simulated here)."""
    real = views._hidden

    def patched(conn: Connection, found: set[str]) -> set[str]:
        return set(real(conn, found)) | (set(found) & set(ids))

    views._hidden = patched
    try:
        yield
    finally:
        views._hidden = real


# --- cwp_list and cwp_detail --------------------------------------------------------------------


def test_cwp_list_has_the_six_packages_by_number_with_their_fields(seeded: World) -> None:
    rows = read(seeded, views.cwp_list)
    assert [r.number for r in rows] == NUMBERS
    first = next(r for r in rows if r.title == "Rack 12 piping")
    assert (first.state, first.discipline, first.cwa) == (
        "Released for IWP development",
        "PIP",
        "A1",
    )
    assert first.budget_hours == Decimal("4200.0")
    assert (first.planned_start, first.planned_finish) == ("2026-11-02", "2027-01-29")
    assert all(r.allocated for r in rows)


def test_cwp_list_filters_by_state_discipline_and_area(seeded: World) -> None:
    assert [r.number for r in read(seeded, views.cwp_list, state="Planned")] == [
        "P123-CWP-CIV-0002",
        "P123-CWP-PIP-0004",
    ]
    assert len(read(seeded, views.cwp_list, discipline="CIV")) == 2
    assert [r.number for r in read(seeded, views.cwp_list, cwa="A2")] == ["P123-CWP-PIP-0003"]
    assert read(seeded, views.cwp_list, cwa="NOPE") == []
    assert read(seeded, views.cwp_list, state="Closed") == []


def test_a_void_package_is_left_out_and_an_unallocated_one_says_so(seeded: World) -> None:
    ids = {r.number: r.id for r in read(seeded, views.cwp_list)}
    seeded.call("sue", "VoidCwp", id=ids["P123-CWP-PIP-0004"], reason="gone")
    extra = seeded.new_cwp("PIP", "Unallocated", "A1")
    rows = {r.id: r for r in read(seeded, views.cwp_list)}
    assert ids["P123-CWP-PIP-0004"] not in rows
    assert len(rows) == 6
    assert rows[extra].allocated is False
    assert rows[ids["P123-CWP-PIP-0001"]].allocated is True


def test_cwp_detail_has_allocations_packages_and_activities(seeded: World) -> None:
    detail = read(seeded, views.cwp_detail, "P123-CWP-PIP-0001")
    assert detail.title == "Rack 12 piping"
    assert [(a.wbs_code, a.percent) for a in detail.allocations] == [("1.1.1", Decimal("100.00"))]
    assert detail.packages == []
    assert detail.activities == []
    assert detail.contractor_text is None
    assert detail.allocated is True


@pytest.mark.parametrize("number", ["NOPE", "P123-CWP-PIP-9999", ""])
def test_cwp_detail_of_a_missing_number_is_none(seeded: World, number: str) -> None:
    assert read(seeded, views.cwp_detail, number) is None


def test_a_void_package_and_another_project_answer_none(seeded: World) -> None:
    ids = {r.number: r.id for r in read(seeded, views.cwp_list)}
    seeded.call("sue", "VoidCwp", id=ids["P123-CWP-PIP-0004"], reason="gone")
    assert read(seeded, views.cwp_detail, "P123-CWP-PIP-0004") is None
    with open_uow(seeded.db, readonly=True) as uow:
        assert views.cwp_detail(uow.conn(), "project:P999", "P123-CWP-PIP-0001") is None


def _require(w: World, cwp: str, package: str) -> None:
    with open_uow(w.db) as uow:
        handle_add_link(
            uow,
            AddLink(
                actor="user:uma",
                source="test",
                scope=SCOPE,
                from_id=cwp,
                to_id=package,
                relation="requires",
            ),
        )


def test_the_requires_link_path_shows_the_package_on_the_cwp_and_the_cwp_on_the_package(
    seeded: World,
) -> None:
    cwp = read(seeded, views.cwp_detail, "P123-CWP-PIP-0001").id
    for kind, number in (("ewp", "EWP-1"), ("pwp", "PWP-1")):
        seeded.call(
            "uma",
            "RecordExternalPackage",
            package_type=kind,
            package_no=number,
            title=f"Package {number}",
            status_text="In review",
            constraint_source=True,
        )
    ewp = seeded.id_of("EWP-1", "awp.EWPRef")
    _require(seeded, cwp, ewp)
    detail = read(seeded, views.cwp_detail, "P123-CWP-PIP-0001")
    assert [(p.kind, p.package_no, p.title, p.cwps) for p in detail.packages] == [
        ("EWP", "EWP-1", "Package EWP-1", ["P123-CWP-PIP-0001"])
    ]
    packages = read(seeded, views.package_list)
    assert [(p.kind, p.package_no, p.cwps) for p in packages] == [
        ("EWP", "EWP-1", ["P123-CWP-PIP-0001"]),
        ("PWP", "PWP-1", []),
    ]
    assert [p.package_no for p in read(seeded, views.package_list, kind="PWP")] == ["PWP-1"]
    assert [p.package_no for p in read(seeded, views.package_list, kind="EWP")] == ["EWP-1"]
    with pytest.raises(ValueError, match="unknown package kind"):
        read(seeded, views.package_list, kind="XWP")
    assert packages[0].constraint_source is True


def test_cwa_list_has_the_four_areas_by_code_and_flags_a_retired_one(seeded: World) -> None:
    assert [(a.code, a.retired) for a in read(seeded, views.cwa_list)] == [
        ("A1", False),
        ("A2", False),
        ("A3", False),
        ("A4", False),
    ]
    seeded.call("sue", "DefineCwa", code="A5", title="Spare")
    seeded.call("sue", "RetireCwa", cwa=seeded.id_of("A5", "awp.CWA"), reason="not needed")
    rows = read(seeded, views.cwa_list)
    assert [(a.code, a.retired) for a in rows][-1] == ("A5", True)
    assert rows[0].location_text == "North"


# --- the WBS --------------------------------------------------------------------------------


def test_wbs_tree_is_depth_first_with_cwp_counts_up_the_chain(seeded: World) -> None:
    rows = read(seeded, views.wbs_tree)
    assert [r.code for r in rows] == [
        "1",
        "1.1",
        "1.1.1",
        "1.1.2",
        "1.1.3",
        "1.2",
        "1.2.1",
        "1.2.2",
        "1.2.3",
    ]
    by = {r.code: r for r in rows}
    assert (by["1"].parent_code, by["1.1"].parent_code, by["1.1.1"].parent_code) == (
        None,
        "1",
        "1.1",
    )
    assert (by["1"].cwp_count, by["1.1"].cwp_count, by["1.2"].cwp_count) == (6, 3, 3)
    assert by["1.1.1"].cwp_count == 1
    assert all(r.cwps == [] for r in rows)  # the tree lists no CWPs; a leaf's detail does


def test_wbs_tree_depth_keeps_the_levels_below_n_and_not_the_counts(seeded: World) -> None:
    one = read(seeded, views.wbs_tree, depth=1)
    assert [r.code for r in one] == ["1"]
    assert one[0].cwp_count == 6
    two = read(seeded, views.wbs_tree, depth=2)
    assert [r.code for r in two] == ["1", "1.1", "1.2"]


def test_wbs_detail_lists_a_leaf_s_cwps_with_hours_and_a_parent_none(seeded: World) -> None:
    leaf = read(seeded, views.wbs_detail, "1.1.1")
    assert [(c.number, c.percent, c.hours) for c in leaf.cwps] == [
        ("P123-CWP-PIP-0001", Decimal("100.00"), Decimal("4200.00"))
    ]
    assert read(seeded, views.wbs_detail, "1.1").cwps == []
    assert read(seeded, views.wbs_detail, "9.9") is None


def test_wbs_cwp_hours_are_budget_times_percent_to_two_places(seeded: World) -> None:
    # a package on two leaves 33.33 / 66.67 of 100.1 hours
    other = seeded.new_cwp("PIP", "Split", "A1", budget_hours="100.1")
    seeded.call(
        "uma",
        "AllocateCwpToWbs",
        cwp=other,
        allocations=[
            {"wbs_code": "1.2.2", "percent": "33.33"},
            {"wbs_code": "1.2.3", "percent": "66.67"},
        ],
    )
    first = read(seeded, views.wbs_detail, "1.2.2")
    second = read(seeded, views.wbs_detail, "1.2.3")
    assert [c.hours for c in first.cwps if c.title == "Split"] == [Decimal("33.36")]
    assert [c.hours for c in second.cwps if c.title == "Split"] == [Decimal("66.74")]


def test_without_rollup_rows_the_totals_are_null(seeded: World) -> None:
    for r in read(seeded, views.wbs_tree):
        assert r.total_hours is None
        assert r.by_cost_code == {}


def test_with_rollup_rows_the_totals_and_cost_code_lines_follow_the_packages(rolled: World) -> None:
    by = {r.code: r for r in read(rolled, views.wbs_tree)}
    assert by["1.1.1"].total_hours == Decimal("4200.0")
    assert by["1.1.1"].by_cost_code == {WLD: Decimal("2520.0"), ERC: Decimal("1680.0")}
    assert by["1.1.2"].total_hours == Decimal("1800.0")
    assert by["1.1.2"].by_cost_code == {}  # unallocated: a total, no cost code line
    assert by["1.1"].total_hours == Decimal("6950.0")
    assert by["1.2.1"].by_cost_code == {CON: Decimal("3100.0")}
    assert by["1"].total_hours == Decimal("11090.0")  # 6950 + 4140
    assert by["1"].by_cost_code == {
        WLD: Decimal("2520.0"),
        ERC: Decimal("1680.0"),
        CON: Decimal("3100.0"),
    }
    detail = read(rolled, views.wbs_detail, "1.1.1")
    assert detail.total_hours == Decimal("4200.0")


def test_a_later_rollup_row_replaces_an_earlier_one(rolled: World) -> None:
    cwp = read(rolled, views.cwp_detail, "P123-CWP-PIP-0001").id
    # PIP-0001 is Released: return it, revise its hours, run again
    rolled.call("sue", "ReturnCwp", cwp=cwp, reason="more hours")
    rolled.call("uma", "ReviseCwp", cwp=cwp, budget_hours="5000")
    from tl_mod_awp.worker import build_worker

    with build_worker(rolled.db) as worker:
        worker.runner.run_until_idle()
    assert read(rolled, views.wbs_detail, "1.1.1").total_hours == Decimal("5000.0")
    assert read(rolled, views.wbs_detail, "1").total_hours == Decimal("11890.0")


# --- the path --------------------------------------------------------------------------------


def test_the_path_reads_by_version_and_unknown_versions_are_none(seeded: World) -> None:
    now = read(seeded, views.path)
    assert (now.key, now.version, now.current_version) == ("P123-POC", 1, 1)
    assert [(s.position, s.cwa) for s in now.steps] == [(1, "A1"), (2, "A2"), (3, "A3"), (4, "A4")]
    assert read(seeded, views.path, 2) is None
    assert read(seeded, views.path, 0) is None


def test_no_path_reads_none_and_no_versions(world: World) -> None:
    assert read(world, views.path) is None
    assert read(world, views.path_versions) == []


def _move(w: World, cwa: str, to: int, version: int, reason: str = "Access") -> None:
    w.call(
        "sue",
        "MoveCwaInPath",
        cwa_code=cwa,
        to_position=to,
        reason_code=reason,
        expected_version=version,
    )


def test_path_versions_newest_first_with_the_reason_of_the_resequencing(seeded: World) -> None:
    _move(seeded, "A4", 1, 1)
    _move(seeded, "A3", 1, 2, "Access")
    rows = read(seeded, views.path_versions)
    assert [(v.version, v.step_count, v.is_current, v.reason_code) for v in rows] == [
        (3, 4, True, "Access"),
        (2, 4, False, "Access"),
        (1, 4, False, None),
    ]
    assert read(seeded, views.path, 2).steps[0].cwa == "A4"
    assert read(seeded, views.path).steps[0].cwa == "A3"


def test_version_one_has_no_reason_even_when_a_step_carries_one(world: World) -> None:
    for code in ("A1", "A2"):
        world.call("sue", "DefineCwa", code=code, title=code)
    world.call(
        "sue",
        "DefinePathOfConstruction",
        steps=[{"cwa_code": "A1", "reason_code": "Access"}, {"cwa_code": "A2"}],
    )
    [v1] = read(world, views.path_versions)
    assert v1.reason_code is None
    assert read(world, views.path).steps[0].reason_code == "Access"


def test_the_reason_of_a_version_is_the_first_non_null_step_reason_in_position_order(
    seeded: World,
) -> None:
    _move(seeded, "A2", 4, 1, "Access")
    rows = read(seeded, views.path_versions)
    assert rows[0].reason_code == "Access"


def test_a_hidden_area_s_step_contributes_nothing_to_a_version_reason(seeded: World) -> None:
    _move(seeded, "A2", 4, 1, "Access")
    a2 = seeded.id_of("A2", "awp.CWA")
    with hiding(a2):
        rows = read(seeded, views.path_versions)
        assert rows[0].version == 2
        assert rows[0].step_count == 3
        assert rows[0].reason_code is None  # the one step with a reason is the hidden area's
        assert [s.cwa for s in read(seeded, views.path).steps] == ["A1", "A3", "A4"]


# --- hidden references (D22: patch views._hidden) ---------------------------------------------


def test_a_hidden_area_is_left_off_the_cwp_row_and_the_area_list(seeded: World) -> None:
    a1 = seeded.id_of("A1", "awp.CWA")
    with hiding(a1):
        rows = {r.number: r for r in read(seeded, views.cwp_list)}
        assert rows["P123-CWP-PIP-0001"].cwa is None
        assert rows["P123-CWP-PIP-0003"].cwa == "A2"
        assert read(seeded, views.cwp_detail, "P123-CWP-PIP-0001").cwa is None


def test_a_hidden_cwp_vanishes_from_the_counts_and_the_allocation_reads(seeded: World) -> None:
    cwp = read(seeded, views.cwp_detail, "P123-CWP-PIP-0001").id
    with hiding(cwp):
        by = {r.code: r for r in read(seeded, views.wbs_tree)}
        assert by["1.1.1"].cwp_count == 0
        assert by["1"].cwp_count == 5
        assert read(seeded, views.wbs_detail, "1.1.1").cwps == []
        listed = {r.number: r for r in read(seeded, views.cwp_list)}
        # the SQL clause decides the row (no class on an awp record); the patched ids drop out of
        # everything that goes through _hidden: the allocated flag included
        assert listed["P123-CWP-PIP-0001"].allocated is False
        assert listed["P123-CWP-PIP-0002"].allocated is True


def test_a_hidden_cwp_is_not_named_on_the_package(seeded: World) -> None:
    cwp = read(seeded, views.cwp_detail, "P123-CWP-PIP-0001").id
    seeded.call("uma", "RecordExternalPackage", package_type="ewp", package_no="EWP-9", title="T",
                constraint_source=False)  # fmt: skip
    ewp = seeded.id_of("EWP-9", "awp.EWPRef")
    _require(seeded, cwp, ewp)
    assert len(read(seeded, views.cwp_detail, "P123-CWP-PIP-0001").packages) == 1
    with hiding(cwp):
        [pkg] = read(seeded, views.package_list)
        assert pkg.cwps == []  # a hidden CWP is not named on the package


def test_total_hours_never_includes_a_hidden_cost_code_s_hours(rolled: World) -> None:
    """T10F1: total = the visible lines + the unallocated line."""
    erc = rolled.id_of(ERC, "cost.CostCode")
    plain = {r.code: r for r in read(rolled, views.wbs_tree)}
    with hiding(erc):
        patched = {r.code: r for r in read(rolled, views.wbs_tree)}
    assert plain["1.1.1"].total_hours == Decimal("4200.0")
    assert patched["1.1.1"].total_hours == Decimal("2520.0")  # the Welding line only
    assert ERC not in patched["1.1.1"].by_cost_code
    assert patched["1.1.1"].total_hours == sum(patched["1.1.1"].by_cost_code.values(), Decimal(0))
    # the ancestors that hold the hidden code's line follow; a node without it keeps its total
    assert patched["1"].total_hours == Decimal("2520.0") + Decimal("3100.0") + Decimal(
        "1800.0"
    ) + Decimal("950.0") + Decimal("640.0") + Decimal("400.0")
    assert patched["1.2.1"].total_hours == plain["1.2.1"].total_hours
    assert patched["1.1.2"].total_hours == plain["1.1.2"].total_hours
    assert all(ERC not in r.model_dump_json() for r in patched.values())


def test_an_unallocated_line_stays_in_the_total_when_a_cost_code_is_hidden(rolled: World) -> None:
    """A node with a hidden cost code and an unallocated part: visible lines + unallocated."""
    rolled.call("sue", "DefineWbsNode", code="1.3", title="Mixed", parent_code="1")
    rolled.call(
        "sue",
        "MapWbsToCostCodes",
        node=rolled.id_of("1.3"),
        allocations=[
            {"cost_code": WLD, "percent": "50.00"},
            {"cost_code": ERC, "percent": "50.00"},
        ],
    )
    # the parent 1 mixes mapped leaves and unallocated leaves
    from tl_mod_awp.worker import build_worker

    cwp = rolled.new_cwp("PIP", "Mixed", "A1", budget_hours="100")
    rolled.call(
        "uma", "AllocateCwpToWbs", cwp=cwp, allocations=[{"wbs_code": "1.3", "percent": "100.00"}]
    )
    with build_worker(rolled.db) as worker:
        worker.runner.run_until_idle()
    erc = rolled.id_of(ERC, "cost.CostCode")
    with hiding(erc):
        root = read(rolled, views.wbs_detail, "1")
    visible = sum(root.by_cost_code.values(), Decimal(0))
    unallocated = Decimal("1800.0") + Decimal("950.0") + Decimal("640.0") + Decimal("400.0")
    assert root.total_hours == visible + unallocated
    assert root.total_hours is not None
    assert root.total_hours < Decimal("11190.0")  # the full figure would be 11190


def test_a_hidden_node_starts_its_children_at_the_top_and_loses_their_parent_code(
    seeded: World,
) -> None:
    node = seeded.id_of("1.1")
    with hiding(node):
        rows = read(seeded, views.wbs_tree)
        by = {r.code: r for r in rows}
        assert "1.1" in by  # the SQL clause decides the node itself; the patch affects references
        assert by["1.1.1"].parent_code is None
        assert by["1.2.1"].parent_code == "1.2"
