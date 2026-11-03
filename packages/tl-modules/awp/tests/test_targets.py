"""The load targets awp_wbs and awp_cwa (T02): plans, parents first, create-only, reversals."""

from __future__ import annotations

import csv
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy import text
from tl_adapters.db import DbTarget, as_target, create_schema, open_uow
from tl_cli.main import app
from tl_core.auth import accounts
from tl_core.auth.password import prepare_password
from tl_mod_awp.targets import cwa_target, wbs_target
from tl_mod_cost.testing import CostWorld, row
from tl_mod_legacy.model import Grid, LoaderDef
from typer.testing import CliRunner

S = "project:P123"
PW = "correct horse battery"
LD = LoaderDef("l", "acc", "t", "x", "d", "")
WHO: dict[str, Any] = {"actor": "user:admin", "source": "legacy:acc"}
TREE = [("1", ""), ("2", ""), ("1.1", "1"), ("1.2", "1"), ("2.1", "2"), ("2.2", "2")]
LEAVES = [(f"{p}.{n}", p) for p in ("1.1", "1.2", "2.1") for n in (1, 2)]
WBS = [(c, c, p, "") for c, p in [*LEAVES, *TREE]]  # children first in the file
WBS[0], WBS[3] = ("1.1.1", "Weld", "1.1", "WLD:60;ERC:40"), ("1.2.2", "Test", "1.2", "TST:100")
BAD = [("B1", "Over", "1", "WLD:50;ERC:51"), ("B2", "Orphan", "NOPE", "")]


class Rig:
    def __init__(self, db: DbTarget, work: Path) -> None:
        self.db = db
        self.work = work

    def use(self, fn: Callable[[Any], Any]) -> Any:
        with open_uow(self.db) as u:
            return fn(u)

    def grid(self, name: str, rows: list[Any], *more: str) -> Grid:
        path = self.work / name
        with path.open("w", newline="") as f:
            csv.writer(f).writerows([["code", "title", "parent", "cost_codes", *more], *rows])
        with path.open() as f:
            got = list(csv.reader(f))
        cells: list[list[str | None]] = [list(r) for r in got[1:]]
        return Grid(got[0], cells)

    def plan(self, t: Any, g: Grid) -> Any:
        return self.use(lambda u: t.plan(u.conn(), S, LD, g))

    def apply(self, t: Any, g: Grid, cid: str = "load:1") -> Any:
        def go(u: Any) -> Any:
            return t.apply(
                u,
                S,
                LD,
                t.plan(u.conn(), S, LD, g),
                correlation_id=cid,
                **WHO,
                confidentiality=None,
            )

        return self.use(go)

    def reverse(self, t: Any, ids: list[str]) -> int:
        back = {"correlation_id": "comp:1", "reason": "test"}
        return self.use(lambda u: t.reverse(u, S, ids, **WHO, **back))

    def sql(self, q: str) -> list[Any]:
        return self.use(lambda u: u.conn().execute(text(q)).scalars().all())


@pytest.fixture
def rig(db: DbTarget, tmp_path: Path) -> Rig:
    CostWorld(db).import_snapshot([row(c, c) for c in ("WLD", "ERC", "TST")])
    return Rig(db, tmp_path)


def test_a_plan_marks_a_sum_off_100_and_an_unknown_parent_invalid(rig: Rig) -> None:
    plan = rig.plan(wbs_target(), rig.grid("wbs.csv", [*WBS, *BAD]))
    assert len(plan.rows) == 12
    assert [w for _, w in plan.invalid] == [
        "allocation sums to 101.00, not 100.00",
        "parent is unknown",
    ]


def test_a_sum_of_99_is_invalid_and_100_valid(rig: Rig) -> None:
    short = rig.plan(wbs_target(), rig.grid("a.csv", [("S1", "x", "", "WLD:50;ERC:49")]))
    assert short.invalid == [(2, "allocation sums to 99.00, not 100.00")]
    exact = rig.plan(wbs_target(), rig.grid("b.csv", [("S1", "x", "", "WLD:50;ERC:50")]))
    assert exact.invalid == []
    assert len(exact.rows) == 1


def test_depth_nine_is_invalid_and_no_problem_holds_a_cell(rig: Rig) -> None:
    chain = [(f"N{i}", "n", f"N{i - 1}" if i > 1 else "", "") for i in range(1, 10)]
    deep = rig.plan(wbs_target(), rig.grid("deep.csv", chain))
    assert len(deep.rows) == 8
    assert deep.invalid == [(10, "depth is over 8 levels")]
    bad = rig.plan(wbs_target(), rig.grid("bad.csv", [*WBS, *BAD]))
    problems = " ".join(w for _, w in [*bad.invalid, *deep.invalid])
    for cell in ("NOPE", "Over", "WLD"):
        assert cell not in problems


def test_nodes_load_parents_first_whatever_the_file_order(rig: Rig) -> None:
    made = rig.apply(wbs_target(), rig.grid("wbs.csv", [*WBS, *BAD]))
    keys = [c.key for c in made]
    assert len(made) == 12
    assert all(keys.index(c) > keys.index(par) for c, par in TREE if par)


def test_a_second_run_is_create_only_and_writes_nothing(rig: Rig) -> None:
    wbs = wbs_target()
    g = rig.grid("wbs.csv", [*WBS, *BAD])
    made = rig.apply(wbs, g)
    n = rig.sql("SELECT count(*) FROM events")
    assert len(rig.plan(wbs, g).existing) == 12
    assert rig.apply(wbs, g) == []
    assert rig.sql("SELECT count(*) FROM events") == n
    c = rig.use(lambda u: wbs.compare(u.conn(), S, LD, g, {m.key for m in made}))
    assert (c.valid, c.matched, c.invalid, c.missing, c.differs) == (12, 12, 2, [], [])


def test_a_code_held_by_a_node_is_found_through_resolve_code(rig: Rig) -> None:
    wbs = wbs_target()
    rig.apply(wbs, rig.grid("one.csv", [("7", "Seven", "", "")]))
    again = rig.plan(wbs, rig.grid("two.csv", [("7", "Seven", "", ""), ("8", "Eight", "", "")]))
    assert len(again.existing) == 1
    assert len(again.rows) == 1


def test_cwas_load_and_the_path_follows_the_sequence(rig: Rig) -> None:
    cwa = cwa_target()
    areas = rig.apply(
        cwa, rig.grid("c.csv", [("A2", "Two", "", "", 2), ("A1", "One", "", "", 1)], "sequence")
    )
    steps = rig.sql(
        "SELECT a.code FROM cur_awp_path_step s JOIN cur_awp_cwa a ON a.id = s.cwa_id "
        "ORDER BY s.position"
    )
    assert len(areas) == 3  # two areas and the path
    assert steps == ["A1", "A2"]


def test_a_path_in_place_is_left_alone_and_is_irreversible(rig: Rig) -> None:
    cwa = cwa_target()
    areas = rig.apply(
        cwa, rig.grid("c.csv", [("A2", "Two", "", "", 2), ("A1", "One", "", "", 1)], "sequence")
    )
    more = rig.grid("c2.csv", [("A3", "Three", "", "", 1)], "sequence")
    assert rig.plan(cwa, more).existing == ["P123-POC"]
    assert len(rig.apply(cwa, more, "load:2")) == 1
    ids = [a.record_id for a in areas]
    rev = rig.use(lambda u: cwa.reversals(u.conn(), S, ids, "load:1"))
    assert [r.reversible for r in rev] == [True, True, False]
    assert rev[2].problem is not None


def test_reverse_retires_children_before_parents_and_leaves_the_path(rig: Rig) -> None:
    wbs, cwa = wbs_target(), cwa_target()
    made = rig.apply(wbs, rig.grid("wbs.csv", [*WBS]))
    areas = rig.apply(cwa, rig.grid("c.csv", [("A1", "One", "", "", 1)], "sequence"))
    node_ids = [m.record_id for m in made]
    assert rig.reverse(wbs, node_ids) == 12
    retired = (
        "SELECT n.depth FROM events e JOIN cur_awp_wbs_node n ON n.id = e.stream_id "
        "WHERE e.event_type = 'WBSNode.Retired' ORDER BY e.seq"
    )
    depths = rig.sql(retired)
    assert len(depths) == 12
    assert depths == sorted(depths, reverse=True)
    states = {r.state for r in rig.use(lambda u: wbs.reversals(u.conn(), S, node_ids, "load:1"))}
    assert states == {"Retired"}
    ids = [a.record_id for a in areas]
    assert rig.reverse(cwa, ids) == 1  # the area; the path is left


def test_a_second_reverse_of_a_reversed_run_is_a_no_op(rig: Rig) -> None:
    """D17: the second reverse finds every node Retired and writes nothing."""
    wbs = wbs_target()
    made = rig.apply(wbs, rig.grid("wbs.csv", [*WBS]))
    ids = [m.record_id for m in made]
    assert rig.reverse(wbs, ids) == 12
    events = rig.sql("SELECT count(*) FROM events")
    assert rig.reverse(wbs, ids) == 0
    assert rig.sql("SELECT count(*) FROM events") == events


def test_a_node_changed_after_the_load_is_irreversible(rig: Rig) -> None:
    wbs = wbs_target()
    made = rig.apply(wbs, rig.grid("wbs.csv", [*WBS]))
    ids = [m.record_id for m in made]
    leaf = next(m.record_id for m in made if m.key == "1.1.1")
    from tl_mod_awp.commands import ReviseWbsNode

    def revise(u: Any) -> Any:
        from tl_mod_awp.handlers.wbs import handle_revise_wbs_node

        return handle_revise_wbs_node(
            u, ReviseWbsNode(actor="user:sue", source="test", scope=S, node=leaf, title="Changed")
        )

    rig.use(revise)
    rev = rig.use(lambda u: wbs.reversals(u.conn(), S, ids, "load:1"))
    flags = {r.record_id: r.reversible for r in rev}
    assert flags[leaf] is False


def test_the_admin_gate_refuses_a_user_and_a_document_controller(tmp_path: Path) -> None:
    db = as_target(str(tmp_path / "t.db"))
    create_schema(db)
    env = {
        "TL_DB": str(tmp_path / "t.db"),
        "TL_ENV": "dev",
        "TL_SESSION_FILE": str(tmp_path / "s.json"),
    }
    sample = tmp_path / "wbs.csv"
    sample.write_text("code,title,parent,cost_codes\n1,One,,\n", encoding="utf-8")
    for name, role in (("uma", "user"), ("dora", "document_controller")):
        word = prepare_password(PW, username=name)
        with open_uow(db) as u:
            accounts.create_account(
                u,
                username=name,
                display_name=name,
                kind="person",
                roles=[role],
                by="svc:a",
                password=word,
            )
        CliRunner().invoke(app, ["login", name, "--password-stdin"], env=env, input=PW)
        r = CliRunner().invoke(
            app,
            ["load", "open", str(sample), "--project", "P123", "--loader", "x"],
            env=env,
        )
        assert r.exit_code == 1
        assert "forbidden" in r.output
