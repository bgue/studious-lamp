"""The progress rollup and its CSV (P2-I5 S3): arithmetic, filter, formula safety, rebuild."""

from __future__ import annotations

import csv
import io
from collections.abc import Callable
from decimal import Decimal

import pytest
from awp_world import SCOPE, World
from progress_world import ProgressWorld, RollRig, roll_on
from tl_adapters.db import DbTarget, create_schema, rebuild_projections
from tl_core import confidentiality as cf
from tl_mod_awp.names import CWP
from tl_mod_awp.progress.export import ExportError, csv_cell

LOWEST = cf.Viewer()
D = Decimal


def rows_of(text: str) -> list[list[str]]:
    return list(csv.reader(io.StringIO(text)))


@pytest.fixture
def rr(world: World) -> RollRig:
    return roll_on(ProgressWorld(world))


def test_the_worked_example_gives_twenty_of_forty(rr: RollRig) -> None:
    found = rr.read()
    cwp = next(c for c in found.cwps if c.cwp_id == rr.ids["a"])
    assert (cwp.iwps, cwp.earned_hours, cwp.hours) == (3, D("20.0"), D("40.0"))


def test_parts_of_one_total_split_by_largest_remainder(rr: RollRig) -> None:
    found = rr.read()
    parts = sorted(
        n.earned_hours
        for n in found.nodes
        if n.node_id in {rr.w.id_of(c) for c in ("1.2.1", "1.2.2", "1.2.3")}
    )
    assert parts == [D("3.3"), D("3.3"), D("3.4")]
    parent = next(n for n in found.nodes if n.node_id == rr.w.id_of("1.2"))
    assert parent.earned_hours == D("10.0") == sum(parts)


def test_a_node_with_descendants_includes_them(rr: RollRig) -> None:
    found = {n.node_id: n for n in rr.read().nodes}
    # 1.1 holds 1.1.1 (20.0 of package A) and 1.1.2 (10.0 of package C); the root holds all
    assert found[rr.w.id_of("1.1")].earned_hours == D("30.0")
    assert found[rr.w.id_of("1")].earned_hours == D("40.0")


def test_cost_code_lines_of_a_node_sum_to_the_node_total(rr: RollRig) -> None:
    found = rr.read()
    by_code = {ln.code: ln.earned_hours for ln in found.lines}
    assert by_code["4210-PIP-WLD"] == D("12.0")
    assert by_code["4210-PIP-ERC"] == D("8.0")
    root = next(n for n in found.nodes if n.node_id == rr.w.id_of("1"))
    assert sum(ln.earned_hours for ln in found.lines) == root.earned_hours
    assert found.lines[-1].code == "Unallocated"  # one such line, last
    assert [ln.code for ln in found.lines].count("Unallocated") == 1


def test_an_iwp_with_null_hours_weighs_the_mean(rr: RollRig) -> None:
    # items 10.0 and none: the null weighs 10.0, so 20 h at 50.0 percent earns 10.0
    cwp = next(c for c in rr.read().cwps if c.cwp_id == rr.ids["c"])
    assert (cwp.hours, cwp.earned_hours) == (D("20.0"), D("10.0"))


def test_no_hours_set_weighs_one_each(rr: RollRig) -> None:
    extra = rr.cwp("5.0", [("1.2.3", "100.00")])
    rr.iwp(extra, [None, None], "50.0")
    cwp = next(c for c in rr.read().cwps if c.cwp_id == extra)
    assert (cwp.hours, cwp.earned_hours) == (D("2.0"), D("1.0"))


def test_an_iwp_without_a_stored_row_earns_zero_and_counts_its_hours(rr: RollRig) -> None:
    extra = rr.cwp("5.0", [("1.2.3", "100.00")])
    rr.iwp(extra, ["8.0"], None)
    cwp = next(c for c in rr.read().cwps if c.cwp_id == extra)
    assert (cwp.iwps, cwp.hours, cwp.earned_hours) == (1, D("8.0"), D("0.0"))


@pytest.mark.parametrize("state", ["Cancelled", "Split"])
def test_a_cancelled_or_split_iwp_is_out(rr: RollRig, state: str) -> None:
    before = rr.read()
    rr.w.set_status(rr.ids["a3"], state)
    after = rr.read()
    cwp = next(c for c in after.cwps if c.cwp_id == rr.ids["a"])
    assert (cwp.iwps, cwp.earned_hours, cwp.hours) == (2, D("15.0"), D("20.0"))
    assert after.cwps != before.cwps


def test_earned_hours_are_not_capped_to_the_package_budget(rr: RollRig) -> None:
    extra = rr.cwp("1.0", [("1.2.3", "100.00")])
    rr.iwp(extra, ["10.0"], "100.0")
    cwp = next(c for c in rr.read().cwps if c.cwp_id == extra)
    assert cwp.earned_hours == D("10.0")


def test_rounding_is_half_up_at_the_output(rr: RollRig) -> None:
    extra = rr.cwp("5.0", [("1.2.3", "100.00")])
    rr.iwp(extra, ["0.5"], "50.0")  # 0.25 exact
    cwp = next(c for c in rr.read().cwps if c.cwp_id == extra)
    assert cwp.earned_hours == D("0.3")
    assert cwp.hours == D("0.5")


def test_a_hidden_cwp_is_absent_for_the_viewer_and_the_note_shows(rr: RollRig) -> None:
    full = rr.read()
    with rr.hidden(rr.ids["b"], record_type=CWP):
        seen = rr.read(viewer=LOWEST)
        assert rr.ids["b"] not in {c.cwp_id for c in seen.cwps}
        assert seen.notes == ["no budget rollup yet"] or not seen.notes
        unfiltered = rr.read(viewer=cf.Viewer(actor="user:x", level=1, account="user:x"))
    assert rr.ids["b"] in {c.cwp_id for c in full.cwps}
    assert unfiltered.cwps == full.cwps  # a reader who may open it sees the unfiltered figure
    a_full = next(c for c in full.cwps if c.cwp_id == rr.ids["a"])
    a_seen = next(c for c in seen.cwps if c.cwp_id == rr.ids["a"])
    assert a_seen == a_full


def test_a_hidden_item_inside_a_visible_iwp_changes_no_figure(rr: RollRig) -> None:
    item = rr.w.rows("SELECT id FROM cur_awp_scope_item LIMIT 1")[0]["id"]
    with rr.pw.hidden(item):
        assert rr.read(viewer=LOWEST).cwps == rr.read().cwps


def test_a_hidden_package_leaves_no_note_and_no_trace_in_the_budget(rr: RollRig) -> None:
    with rr.hidden(rr.ids["b"], record_type=CWP):
        seen = rr.read(viewer=LOWEST)
    assert seen.notes == []
    assert all("hidden" not in n and "shown" not in n for n in seen.notes)


def test_a_viewer_gets_exactly_what_a_world_without_the_package_gives(
    rr: RollRig, new_db: Callable[[], DbTarget]
) -> None:
    other = new_db()
    create_schema(other)
    w2 = World(other)
    w2.people()
    w2.editions()
    missing = roll_on(ProgressWorld(w2), without_b=True)
    for run in (True, False):
        if run:
            rr.run_rollup()  # the stored rows now add the hidden package; they are not read
            missing.run_rollup()
        with rr.hidden(rr.ids["b"], record_type=CWP):
            got = rr.read(viewer=LOWEST)
            data = rr.export(viewer=LOWEST)
        want = missing.read(viewer=LOWEST)
        assert [(ln.code, ln.earned_hours, ln.budget_hours) for ln in got.lines] == [
            (ln.code, ln.earned_hours, ln.budget_hours) for ln in want.lines
        ]
        assert [c.key for c in got.cwps] != []
        assert got.notes == want.notes
        assert [(n.earned_hours, n.budget_hours, n.pct) for n in got.nodes] == [
            (n.earned_hours, n.budget_hours, n.pct) for n in want.nodes
        ]

        # the as_of_seq column (the ledger head) is the one cell that differs between two ledgers
        def strip(text: str) -> list[list[str]]:
            return [r[:-1] for r in rows_of(text)]

        assert strip(data) == strip(missing.export(viewer=LOWEST))
        assert any(r[4] for r in rows_of(data)[1:])  # budgets are shown, computed on read


def test_a_hidden_node_or_cost_code_is_absent_like_a_missing_one(rr: RollRig) -> None:
    ids = rr.w.rows("SELECT id FROM cur_cost_costcode WHERE code = '4210-PIP-WLD'")
    with rr.hidden(ids[0]["id"], record_type="cost.CostCode"):
        seen = rr.read(viewer=LOWEST)
    assert "4210-PIP-WLD" not in {ln.code for ln in seen.lines}
    node = rr.w.id_of("1.1.1")
    with rr.hidden(node, record_type="awp.WBSNode"):
        seen = rr.read(viewer=LOWEST)
    assert node not in {n.node_id for n in seen.nodes}


def test_earned_hours_that_reach_no_node_join_the_one_unallocated_line(rr: RollRig) -> None:
    extra = rr.cwp("5.0", [])  # no allocation: the earned hours reach no node
    rr.iwp(extra, ["10.0"], "100.0")
    found = rr.read()
    last = found.lines[-1]
    # 20.0 sit on unmapped nodes (packages B and C) and 10.0 reach none: one line, last
    assert (last.code, last.cost_code_id, last.earned_hours) == ("Unallocated", None, D("30.0"))
    assert [ln.code for ln in found.lines].count("Unallocated") == 1
    assert rows_of(rr.export())[-1][2] == "Unallocated"


def test_the_lines_add_up_to_the_rounded_total_on_a_tie(rr: RollRig) -> None:
    for allocs in ([], [("1.1.1", "100.00")]):
        extra = rr.cwp("5.0", allocs)
        rr.iwp(extra, ["0.5"], "50.0")  # 0.25 exact each
    found = rr.read()
    assert sum(ln.earned_hours for ln in found.lines) == D("40.5")  # 40.0 + 0.5, rounded once
    assert found.lines[-1].code == "Unallocated"
    assert [ln.code for ln in found.lines].count("Unallocated") == 1


def test_a_longer_export_than_the_cap_is_refused(
    rr: RollRig, monkeypatch: pytest.MonkeyPatch
) -> None:
    from tl_mod_awp.progress import export

    monkeypatch.setattr(export, "MAX_ROWS", 1)
    with pytest.raises(ExportError, match="^export: too many rows$"):
        rr.export()


def test_a_node_without_a_stored_budget_exports_an_empty_cell_and_the_note(rr: RollRig) -> None:
    found = rr.read()
    assert "no budget rollup yet" in found.notes
    assert all(n.budget_hours is None and n.pct is None for n in found.nodes)
    rows = list(csv.reader(io.StringIO(rr.export())))
    assert rows[0] == [
        "period",
        "scope",
        "cost_code",
        "earned_hours",
        "budget_hours",
        "earned_pct",
        "as_of_seq",
    ]
    assert all(r[4] == "" and r[5] == "" for r in rows[1:])


def test_a_stored_budget_gives_the_budget_and_the_percent(rr: RollRig) -> None:
    rr.run_rollup()
    found = rr.read()
    node = next(n for n in found.nodes if n.node_id == rr.w.id_of("1.1.1"))
    assert (node.earned_hours, node.budget_hours, node.pct) == (D("20.0"), D("40.0"), D("50.0"))
    assert "no budget rollup yet" not in found.notes
    rows = list(csv.reader(io.StringIO(rr.export())))
    wld = next(r for r in rows if r[2] == "4210-PIP-WLD")
    assert wld[:2] == ["2026-W45", SCOPE]
    assert (wld[3], wld[4], wld[5]) == ("12.0", "24.0", "50.0")
    assert rows[-1][2] == "Unallocated"


@pytest.mark.parametrize("title", ["=cmd|' /C calc'!A0", "+1", "-1", "@SUM(A1)"])
def test_a_cost_code_that_starts_like_a_formula_reads_back_with_an_apostrophe(
    rr: RollRig, title: str
) -> None:
    from sqlalchemy import text
    from tl_adapters.db import open_uow

    with open_uow(rr.w.db) as uow:
        uow.conn().execute(
            text("UPDATE cur_cost_costcode SET code = :c WHERE code = '4210-PIP-WLD'"), {"c": title}
        )
    rows = list(csv.reader(io.StringIO(rr.export())))
    assert f"'{title}" in [r[2] for r in rows]
    assert all(not r[2].startswith(("=", "+", "-", "@")) for r in rows[1:])


def test_csv_cell_guards_the_first_character_only() -> None:
    for first in "=+-@\t\r":
        assert csv_cell(f"{first}x") == f"'{first}x"
    assert csv_cell("a=b") == "a=b"
    assert csv_cell(None) == ""
    assert csv_cell(12) == "12"


def test_every_cell_is_quoted(rr: RollRig) -> None:
    text = rr.export()
    assert text.splitlines()[0].startswith('"period","scope"')


@pytest.mark.parametrize(
    "period", ["2026-W00", "2026-W54", "2026W45", "26-W45", "2026-W5", "", "2026-W45\n"]
)
def test_a_bad_period_is_refused_with_the_fixed_text(rr: RollRig, period: str) -> None:
    with pytest.raises(ExportError, match="^period: expected YYYY-Www$"):
        rr.export(period)


def test_an_export_changes_no_cost_row_no_stored_row_and_not_the_ledger(rr: RollRig) -> None:
    rr.run_rollup()
    before = rr.counts()
    rr.export()
    rr.read(viewer=LOWEST)
    assert rr.counts() == before


def test_the_same_call_twice_returns_equal_output(rr: RollRig) -> None:
    rr.run_rollup()
    assert rr.read() == rr.read()
    assert rr.export() == rr.export()


def test_the_figures_come_from_the_ledger_a_rebuild_changes_nothing(
    world: World, db: DbTarget
) -> None:
    rig = RollRig(ProgressWorld(world))
    rig.map_codes("1.1.1", ("4210-PIP-WLD", "60.00"), ("4210-PIP-ERC", "40.00"))
    cwp = rig.cwp("40.0", [("1.1.1", "100.00")])
    iwp, items = rig.pw.package(["10.0", "30.0"], cwp_id=cwp)
    rig.pw.move("InstallScopeItem", items[0])
    rig.pw.manual(iwp, items[1])
    rig.run_rollup()
    before = rig.read()
    assert any(c.earned_hours > 0 for c in before.cwps)
    rebuild_projections(db)
    assert rig.read() == before


def test_a_scope_with_no_ledger_content_has_no_packages_and_no_earned_hours(
    world: World,
) -> None:
    found = RollRig(ProgressWorld(world)).read()
    assert found.cwps == []
    assert all(ln.earned_hours == 0 for ln in found.lines)
