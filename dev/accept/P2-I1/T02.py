"""Acceptance for P2-I1-T02: load targets awp.wbs and awp.cwa (SQLite).

Run: ``uv run python dev/accept/P2-I1/T02.py``. The targets are driven through their methods.
"""

from __future__ import annotations

import csv
import tempfile
from pathlib import Path
from typing import Any

from sqlalchemy import text
from tl_adapters.db import as_target, create_schema, open_uow
from tl_cli.main import app
from tl_core.auth import accounts
from tl_core.auth.password import prepare_password
from tl_mod_awp.targets import cwa_target, wbs_target
from tl_mod_cost.testing import CostWorld, row
from tl_mod_legacy.model import Grid, LoaderDef
from typer.testing import CliRunner

S, PW, LD = "project:P123", "correct horse battery", LoaderDef("l", "acc", "t", "x", "d", "")
WHO: dict[str, Any] = {"actor": "user:admin", "source": "legacy:acc"}
TREE = [("1", ""), ("2", ""), ("1.1", "1"), ("1.2", "1"), ("2.1", "2"), ("2.2", "2")]
LEAVES = [(f"{p}.{n}", p) for p in ("1.1", "1.2", "2.1") for n in (1, 2)]
WBS = [(c, c, p, "") for c, p in [*LEAVES, *TREE]]  # children first in the file
WBS[0], WBS[3] = ("1.1.1", "Weld", "1.1", "WLD:60;ERC:40"), ("1.2.2", "Test", "1.2", "TST:100")
BAD = [("B1", "Over", "1", "WLD:50;ERC:51"), ("B2", "Orphan", "NOPE", "")]


def ok(good: bool, what: str) -> None:
    assert good, what
    print("PASS", what)


def main(work: Path) -> None:
    db = as_target(str(work / "t.db"))
    create_schema(db)
    CostWorld(db).import_snapshot([row(c, c) for c in ("WLD", "ERC", "TST")])

    def use(fn: Any) -> Any:
        with open_uow(db) as u:
            return fn(u)

    def grid(name: str, rows: list[Any], *more: str) -> Grid:
        with (work / name).open("w", newline="") as f:
            csv.writer(f).writerows([["code", "title", "parent", "cost_codes", *more], *rows])
        got = list(csv.reader((work / name).open()))
        return Grid(got[0], got[1:])

    def plan(t: Any, g: Grid) -> Any:
        return use(lambda u: t.plan(u.conn(), S, LD, g))

    def apply(t: Any, g: Grid, cid: str = "load:1") -> Any:
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

        return use(go)

    def reverse(t: Any, ids: list[str]) -> int:
        back = {"correlation_id": "comp:1", "reason": "acceptance"}
        return use(lambda u: t.reverse(u, S, ids, **WHO, **back))

    def sql(q: str) -> list[Any]:
        return use(lambda u: u.conn().execute(text(q)).scalars().all())

    wbs, g = wbs_target(), grid("wbs.csv", [*WBS, *BAD])
    p = plan(wbs, g)
    why = [w for _, w in p.invalid]
    ok(
        len(p.rows) == 12 and why == ["allocation sums to 101.00, not 100.00", "parent is unknown"],
        "101 and unknown parent invalid",
    )
    chain = [(f"N{i}", "n", f"N{i - 1}" if i > 1 else "", "") for i in range(1, 10)]
    deep = plan(wbs, grid("deep.csv", chain))
    ok(len(deep.rows) == 8 and deep.invalid == [(10, "depth is over 8 levels")], "depth 9 invalid")
    ok(
        not any(s in w for w in [*why, deep.invalid[0][1]] for s in ("NOPE", "Over", "WLD")),
        "no cell text in a problem",
    )
    made = apply(wbs, g)
    keys = [c.key for c in made]
    ok(
        len(made) == 12 and all(keys.index(c) > keys.index(par) for c, par in TREE if par),
        "12 nodes load parents first",
    )
    n = sql("SELECT count(*) FROM events")
    ok(
        len(plan(wbs, g).existing) == 12
        and apply(wbs, g) == []
        and sql("SELECT count(*) FROM events") == n,
        "second run: 12 existing, nothing written",
    )
    c = use(lambda u: wbs.compare(u.conn(), S, LD, g, set(keys)))
    ok(
        (c.valid, c.matched, c.invalid, c.missing, c.differs) == (12, 12, 2, [], []),
        "compare matches",
    )
    cwa = cwa_target()
    areas = apply(
        cwa, grid("c.csv", [("A2", "Two", "", "", 2), ("A1", "One", "", "", 1)], "sequence")
    )
    steps = sql(
        "SELECT a.code FROM cur_awp_path_step s JOIN cur_awp_cwa a ON a.id = s.cwa_id "
        "ORDER BY s.position"
    )
    ok(len(areas) == 3 and steps == ["A1", "A2"], "CWAs load and path v1 follows sequence")
    more = grid("c2.csv", [("A3", "Three", "", "", 1)], "sequence")
    ok(
        plan(cwa, more).existing == ["P123-POC"] and len(apply(cwa, more, "load:2")) == 1,
        "a path in place is left alone",
    )
    ids = [a.record_id for a in areas]
    rev = use(lambda u: cwa.reversals(u.conn(), S, ids, "load:1"))
    ok(
        [r.reversible for r in rev] == [True, True, False] and rev[2].problem is not None,
        "the path is irreversible",
    )
    node_ids = [m.record_id for m in made]
    ok(reverse(wbs, node_ids) == 12, "reverse retires the run's 12 nodes")
    retired = (
        "SELECT n.depth FROM events e JOIN cur_awp_wbs_node n ON n.id = e.stream_id "
        "WHERE e.event_type = 'WBSNode.Retired' ORDER BY e.seq"
    )
    ok(sql(retired) == sorted(sql(retired), reverse=True), "children before parents")
    states = {r.state for r in use(lambda u: wbs.reversals(u.conn(), S, node_ids, "load:1"))}
    ok(
        states == {"Retired"} and reverse(cwa, ids) == 2,
        "a node reverses to Retired; the path is left",
    )
    env = {"TL_DB": str(work / "t.db"), "TL_ENV": "dev", "TL_SESSION_FILE": str(work / "s.json")}
    for name, role in (("uma", "user"), ("dora", "document_controller")):
        word = prepare_password(PW, username=name)
        new = dict(username=name, display_name=name, kind="person", roles=[role], by="svc:a")
        use(lambda u: accounts.create_account(u, password=word, **new))  # noqa: B023
        CliRunner().invoke(app, ["login", name, "--password-stdin"], env=env, input=PW)
        r = CliRunner().invoke(
            app,
            ["load", "open", str(work / "wbs.csv"), "--project", "P123", "--loader", "x"],
            env=env,
        )
        ok(r.exit_code == 1 and "forbidden" in r.output, f"{name} cannot start a load")
    print("T02 ok")


with tempfile.TemporaryDirectory() as tmp:
    main(Path(tmp))
