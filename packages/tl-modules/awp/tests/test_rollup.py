"""The rollup run, projector and worker (S5): rounding, buckets, the bound, D-c, rebuild."""

from __future__ import annotations

from collections.abc import Callable
from decimal import Decimal
from typing import Any

import pytest
from awp_world import SCOPE, SPEC, World
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st
from sqlalchemy import text
from tl_adapters import queue
from tl_adapters.db import DbTarget, create_schema, make_uow_factory, open_uow, rebuild_projections
from tl_core.jobs import JobRunner
from tl_core.util import new_ulid
from tl_mod_awp import rollup
from tl_mod_awp.targets import wbs_target
from tl_mod_awp.worker import RollupKind, build_worker, requeue_orphans
from tl_mod_legacy.model import Grid, LoaderDef

STATES = (
    "Planned",
    "In development",
    "Released for IWP development",
    "Executing",
    "Complete",
    "Closed",
)
REC = (
    "INSERT INTO cur_core_record (id, key, type, scope, title, status, voided, version, last_seq, "
    "created_at, updated_at) VALUES (:i, :k, 'awp.CWP', :s, 'fixture', :st, :v, 1, 1, "
    "'2026-01-01T00:00:00Z', '2026-01-01T00:00:00Z')"
)
CWP = (
    "INSERT INTO cur_awp_cwp (id, scope, discipline, budget_hours, last_seq) "
    "VALUES (:i, :s, 'PIP', :h, 1)"
)
ALLOC = (
    "INSERT INTO cur_awp_cwp_allocation (row_id, scope, cwp_id, wbs_node_id, percent, last_seq) "
    "VALUES (:r, :s, :c, :n, :p, 1)"
)
FIGS = (
    "SELECT n.code, r.line, c.key AS cc, r.value FROM cur_awp_rollup r "
    "JOIN cur_awp_wbs_node n ON n.id = r.subject_id "
    "LEFT JOIN cur_core_record c ON c.id = r.cost_code_id WHERE r.scope = :s"
)
ROWS = "SELECT row_id, value, as_of_seq, run_id FROM cur_awp_rollup ORDER BY row_id"
EVENTS = "SELECT COUNT(*) AS v FROM events WHERE event_type = 'WBSNode.BudgetRolledUp'"


class Rig:
    """The ledger of one test with CWP rows put in by SQL (their states are not the point here)."""

    def __init__(self, db: DbTarget) -> None:
        self.db = db

    def call(self, name: str, scope: str = SCOPE, **f: Any) -> Any:
        c = SPEC[name]
        with open_uow(self.db) as uow:
            return c.handler(uow, c.model(actor="user:sue", source="test", scope=scope, **f))

    def sql(self, q: str, **p: Any) -> list[Any]:
        with open_uow(self.db) as uow:
            r = uow.conn().execute(text(q), p)
            return list(r.mappings()) if r.returns_rows else []

    def one(self, q: str, **p: Any) -> Any:
        return self.sql(q, **p)[0]["v"]

    def id_of(self, code: str, scope: str = SCOPE) -> str:
        key = f"awp.wbs@{code}"
        return str(
            self.one(
                "SELECT id AS v FROM cur_core_record WHERE scope = :s AND key = :k", s=scope, k=key
            )
        )

    def cwp(
        self,
        hours: str,
        allocs: dict[str, str],
        *,
        state: str = "Planned",
        void: bool = False,
        scope: str = SCOPE,
    ) -> None:
        i = new_ulid()
        self.sql(REC, i=i, k=f"C{i}", s=scope, st=state, v=void)
        self.sql(CWP, i=i, s=scope, h=hours)
        for node, pct in allocs.items():
            self.sql(ALLOC, r=f"{i}:{node}", s=scope, c=i, n=node, p=pct)

    def figs(self, scope: str = SCOPE) -> dict[str, dict[str, str]]:
        out: dict[str, dict[str, str]] = {}
        for r in self.sql(FIGS, s=scope):
            out.setdefault(r["code"], {})[r["cc"] or r["line"]] = r["value"]
        return out

    def request(self, scope: str = SCOPE) -> None:
        with open_uow(self.db) as uow:
            rollup.request(uow, scope)

    def events(self) -> int:
        return int(self.one(EVENTS))

    def run_once(self) -> str:
        with build_worker(self.db) as wk:
            res = wk.runner.run_once()
        return res.outcome if res else "none"

    def state(self, scope: str = SCOPE) -> str:
        return str(
            self.one("SELECT state AS v FROM job_queue WHERE job_id = :j", j=rollup.job_id(scope))
        )


@pytest.fixture
def rig(db: DbTarget) -> Rig:
    return Rig(db)


def _lines(*p: tuple[str, str]) -> list[dict[str, str]]:
    return [{"cost_code": c, "percent": x} for c, x in p]


@pytest.fixture
def main_scope(rig: Rig, db: DbTarget) -> Rig:
    w = World(db)
    w.cost_codes(("WLD", "Welding"), ("ERC", "Erection"), ("TST", "T"))
    tree = [("1", None), ("1.1", "1"), ("1.1.1", "1.1"), ("1.1.2", "1.1")]
    for code, parent in (*tree, *((f"1.{k}", "1") for k in range(2, 7))):
        rig.call("DefineWbsNode", code=code, title=f"N{code}", parent_code=parent)
    rig.call(
        "MapWbsToCostCodes",
        node=rig.id_of("1.1.1"),
        allocations=_lines(("WLD", "60.00"), ("ERC", "40.00")),
    )
    three = _lines(("WLD", "33.33"), ("ERC", "33.33"), ("TST", "33.34"))
    rig.call("MapWbsToCostCodes", node=rig.id_of("1.2"), allocations=three)
    n = {c: rig.id_of(c) for c in ("1.1.1", "1.1.2", "1.2", "1.3", "1.4", "1.5", "1.6")}
    rig.cwp("100.0", {n["1.1.1"]: "100.00"})
    rig.cwp("999.0", {n["1.1.1"]: "100.00"}, void=True)
    rig.cwp("25.0", {n["1.1.2"]: "100.00"})
    rig.cwp("10.0", {n["1.2"]: "100.00"})
    rig.cwp("5.0", {n["1.3"]: "5.00"})  # 0.25 h
    rig.cwp("7.0", {n["1.4"]: "5.00"})  # 0.35 h
    rig.cwp("1.0", {n["1.6"]: "5.00"})  # 0.05 h
    for s in STATES:
        rig.cwp("10.0", {n["1.5"]: "100.00"}, state=s)
    rig.cwp("500.0", {n["1.5"]: "100.00"}, void=True)
    return rig


def test_the_first_run_rounds_by_largest_remainder(main_scope: Rig) -> None:
    assert main_scope.run_once() == "done"
    f = main_scope.figs()
    assert f["1.1.1"] == {"total": "100.0", "WLD": "60.0", "ERC": "40.0"}
    assert f["1.1"]["total"] == "125.0"
    root = {"total": "195.6", "WLD": "63.3", "ERC": "43.3", "TST": "3.3", "unallocated": "85.7"}
    assert f["1"] == root  # exact sum 195.65 -> 195.6 and the parts sum to it
    assert f["1.2"] == {"total": "10.0", "WLD": "3.3", "ERC": "3.3", "TST": "3.4"}


def test_ties_round_to_even_and_a_zero_figure_has_no_row(main_scope: Rig) -> None:
    main_scope.run_once()
    f = main_scope.figs()
    assert f["1.3"]["total"] == "0.2"  # 0.25 -> 0.2
    assert f["1.4"]["total"] == "0.4"  # 0.35 -> 0.4
    assert "1.6" not in f  # 0.05 -> 0.0 (tie to even): no row


def test_a_leaf_without_cost_codes_is_unallocated(main_scope: Rig) -> None:
    main_scope.run_once()
    f = main_scope.figs()
    assert f["1.1.2"] == {"total": "25.0", "unallocated": "25.0"}
    assert f["1.1"]["unallocated"] == "25.0"


def test_void_packages_are_excluded_and_every_other_state_counts(main_scope: Rig) -> None:
    main_scope.run_once()
    assert main_scope.figs()["1.5"]["total"] == "60.0"  # six states, the 500 h void left out


def test_a_second_run_with_no_change_appends_nothing(main_scope: Rig) -> None:
    main_scope.run_once()
    before = main_scope.events()
    main_scope.request()
    assert main_scope.run_once() == "done"
    assert main_scope.events() == before


def test_a_changed_figure_appends_only_the_nodes_that_differ(main_scope: Rig) -> None:
    main_scope.run_once()
    before = main_scope.events()
    q = "UPDATE cur_awp_cwp SET budget_hours = '9.0' WHERE id IN "
    q += "(SELECT cwp_id FROM cur_awp_cwp_allocation WHERE wbs_node_id = :n)"
    main_scope.sql(q, n=main_scope.id_of("1.3"))  # 0.45 h -> 0.4
    main_scope.request()
    main_scope.run_once()
    assert main_scope.events() - before == 2  # the leaf and the root
    assert main_scope.figs()["1.3"]["total"] == "0.4"


def test_a_request_while_running_queues_exactly_one_new_run(main_scope: Rig) -> None:
    """D-c: two requests arrive while the run is ``running``; the settle queues one more run."""
    main_scope.run_once()
    seen: list[str] = []

    class Midway(RollupKind):
        def run(self, work: Any) -> Any:
            for a, b in (("70.00", "30.00"), ("20.00", "80.00")):
                main_scope.call(
                    "MapWbsToCostCodes",
                    node=main_scope.id_of("1.2"),
                    allocations=_lines(("WLD", a), ("ERC", b)),
                )
            seen.append(main_scope.state())
            return super().run(work)

    main_scope.request()
    factory = make_uow_factory(main_scope.db)
    with factory() as uow:
        runner = JobRunner(factory, queue.job_queue_for(uow.conn()), [Midway()])
    runner.run_once()
    factory.dispose()
    assert seen == ["running"]  # a request leaves a running row alone
    n = main_scope.one("SELECT COUNT(*) AS v FROM job_queue WHERE kind = 'awp.rollup'")
    assert main_scope.state() == "queued"
    assert n == 1
    main_scope.run_once()
    assert main_scope.figs()["1.2"] == {"total": "10.0", "WLD": "2.0", "ERC": "8.0"}
    assert main_scope.state() == "done"  # the new run applies the late change, no third


def test_the_events_carry_the_run_in_the_correlation_id_and_make_no_card(main_scope: Rig) -> None:
    main_scope.run_once()
    ev = main_scope.sql(
        "SELECT correlation_id, source, payload FROM events WHERE event_type LIKE '%RolledUp'"
    )
    assert ev
    for e in ev:
        assert e["source"] == "job:awp.rollup"
        assert e["correlation_id"].startswith("rollup:")
        assert e["correlation_id"][len("rollup:") :] in e["payload"]
    cards = main_scope.one(
        "SELECT COUNT(*) AS v FROM cur_feed_items WHERE event_type LIKE '%RolledUp'"
    )
    assert cards == 0


def test_a_rebuild_of_the_projections_equals_the_incremental_table(main_scope: Rig) -> None:
    main_scope.run_once()
    mine = main_scope.sql(ROWS)
    assert mine
    rebuild_projections(main_scope.db)
    assert main_scope.sql(ROWS) == mine


def test_at_most_500_nodes_are_written_per_run_and_the_rest_is_requeued(rig: Rig) -> None:
    scope = "project:P124"
    grid = Grid(
        ["code", "title", "parent", "cost_codes"],
        [["R", "R", "", ""], *([f"L{k}", "L", "R", ""] for k in range(500))],
    )
    target = wbs_target()
    with open_uow(rig.db) as uow:  # one unit of work: 501 DefineWbsNode calls, one commit
        loader = LoaderDef("l", "acc", "t", "x", "d", "")
        target.apply(
            uow,
            scope,
            loader,
            target.plan(uow.conn(), scope, loader, grid),
            correlation_id="load:1",
            actor="user:admin",
            source="legacy:acc",
            confidentiality=None,
        )
        leaves = [
            str(r[0])
            for r in uow.conn().execute(
                text("SELECT id FROM cur_awp_wbs_node WHERE scope = :s AND code <> 'R'"),
                {"s": scope},
            )
        ]
        for node in leaves:
            i = new_ulid()
            uow.conn().execute(
                text(REC), {"i": i, "k": f"C{i}", "s": scope, "st": "Planned", "v": False}
            )
            uow.conn().execute(text(CWP), {"i": i, "s": scope, "h": "1.0"})
            uow.conn().execute(
                text(ALLOC), {"r": f"{i}:{node}", "s": scope, "c": i, "n": node, "p": "100.00"}
            )
    before = rig.events()
    rig.request(scope)
    rig.run_once()
    assert rig.events() - before == 500  # 501 changed nodes: 500 appended
    assert rig.state(scope) == "queued"  # a re-queue left
    rig.run_once()
    assert rig.events() - before == 501
    assert rig.state(scope) == "done"


def test_requeue_orphans_queues_a_project_whose_ledger_moved_past_its_last_run(
    main_scope: Rig,
) -> None:
    main_scope.run_once()
    assert requeue_orphans(main_scope.db) == 0  # nothing moved since the run
    main_scope.call("ReviseWbsNode", node=main_scope.id_of("1.1.2"), title="Renamed again")
    # WBSNode.Revised is a figure event (a move is one): a rename queues a run, which writes nothing
    assert requeue_orphans(main_scope.db) == 1
    assert requeue_orphans(main_scope.db) == 0  # already queued: not queued twice
    before = main_scope.events()
    assert main_scope.run_once() == "done"
    assert main_scope.events() == before
    main_scope.call(
        "MapWbsToCostCodes", node=main_scope.id_of("1.1.2"), allocations=_lines(("WLD", "100.00"))
    )
    main_scope.sql("DELETE FROM job_queue WHERE kind = 'awp.rollup'")  # a restore empties the queue
    assert requeue_orphans(main_scope.db) == 1
    assert main_scope.state() == "queued"


# --- the arithmetic as properties ------------------------------------------------------------

hours = st.decimals(min_value=0, max_value=100000, places=3)


@given(st.dictionaries(st.sampled_from(["a", "b", "c", None]), hours, min_size=1, max_size=4))
def test_split_parts_sum_to_the_rounded_total(parts: dict[str | None, Decimal]) -> None:
    figure = rollup.split(parts)
    total = Decimal(figure.total)
    assert sum((Decimal(v) for _, v in figure.lines), Decimal(0)) == total
    exact = sum(parts.values(), Decimal(0))
    assert abs(total - exact) <= Decimal("0.05")
    for key, value in figure.lines:
        assert abs(Decimal(value) - parts[key]) < Decimal("0.1") + Decimal("0.0001")


def test_split_known_cases() -> None:
    a = Decimal("10") * Decimal("33.33") / 100
    b = Decimal("10") * Decimal("33.34") / 100
    assert rollup.split({"w": a, "e": a, "t": b}) == rollup.Figure(
        "10.0", (("e", "3.3"), ("t", "3.4"), ("w", "3.3"))
    )
    assert rollup.split({None: Decimal("0.05")}).total == "0.0"  # tie to even
    assert rollup.split({None: Decimal("0.15")}).total == "0.2"
    assert rollup.split({"a": Decimal("0.25"), None: Decimal("0.25")}).total == "0.5"


_NODES = st.lists(st.integers(0, 20), min_size=1, max_size=8)


@given(
    shape=st.lists(st.integers(0, 6), min_size=1, max_size=7),
    hours_list=st.lists(st.integers(0, 5000), min_size=0, max_size=6),
)
def test_a_parent_is_the_rounded_sum_of_its_exact_children(
    shape: list[int], hours_list: list[int]
) -> None:
    # node k hangs under node shape[k] % k (a tree); CWPs allocate to the leaves
    parents: dict[str, str | None] = {"n0": None}
    for k, s in enumerate(shape, start=1):
        parents[f"n{k}"] = f"n{s % k}"
    leaves = [n for n in parents if n not in set(parents.values())]
    budgets = {f"c{i}": Decimal(h) / 10 for i, h in enumerate(hours_list)}
    allocations = [(f"c{i}", leaves[i % len(leaves)], Decimal(100)) for i in range(len(hours_list))]
    figures = rollup.compute(parents, {}, budgets, allocations)
    exact = sum(budgets.values(), Decimal(0))
    assert Decimal(figures["n0"].total) == exact.quantize(Decimal("0.1"))
    for node in parents:
        figure = figures[node]
        assert sum((Decimal(v) for _, v in figure.lines), Decimal(0)) == Decimal(figure.total)


# --- rebuild = incremental, over random small projects ----------------------------------------


@settings(
    max_examples=4,
    deadline=None,
    suppress_health_check=[HealthCheck.function_scoped_fixture],
)
@given(
    leaves=st.integers(2, 4),
    picks=st.lists(
        st.tuples(st.integers(0, 3), st.integers(1, 9999), st.integers(1, 100)),
        min_size=1,
        max_size=4,
    ),
    split_cost=st.booleans(),
)
def test_rebuild_equals_incremental_over_random_projects(
    new_db: Callable[[], DbTarget], leaves: int, picks: list[tuple[int, int, int]], split_cost: bool
) -> None:
    db = new_db()
    create_schema(db)
    w = World(db)
    w.people()
    w.editions()
    w.cost_codes(("WLD", "Welding"), ("ERC", "Erection"))
    w.call("sue", "DefineWbsNode", code="1", title="Root")
    for k in range(leaves):
        w.call("sue", "DefineWbsNode", code=f"1.{k + 1}", title="Leaf", parent_code="1")
    if split_cost:
        w.call(
            "sue",
            "MapWbsToCostCodes",
            node=w.id_of("1.1"),
            allocations=_lines(("WLD", "35.50"), ("ERC", "64.50")),
        )
    w.call("sue", "DefineCwa", code="A1", title="Area")
    for leaf, tenths, pct in picks:
        first, second = leaf % leaves + 1, (leaf + 1) % leaves + 1
        cwp = w.new_cwp("PIP", "P", "A1", budget_hours=f"{tenths // 10}.{tenths % 10}")
        lines = [{"wbs_code": f"1.{first}", "percent": f"{pct}.00"}]
        if pct < 100:
            lines.append({"wbs_code": f"1.{second}", "percent": f"{100 - pct}.00"})
        w.call("uma", "AllocateCwpToWbs", cwp=cwp, allocations=lines)
    rig = Rig(db)
    rig.run_once()
    mine = rig.sql(ROWS)
    assert mine
    rebuild_projections(db)
    assert rig.sql(ROWS) == mine
    # a second request with no change appends nothing
    events = rig.events()
    rig.request()
    rig.run_once()
    assert rig.events() == events
