"""Acceptance for P2-I1-S5: the awp.rollup run, projector and worker (SQLite, then TL_PG_URL).

CWPs have no commands until S4, so this script inserts ``cur_awp_cwp``, ``cur_awp_cwp_allocation``
and ``cur_core_record`` rows by SQL (a fixture of the script only; it also creates the two tables).
Run: ``uv run python dev/accept/P2-I1/S5.py``. One ``PASS`` per check, then ``S5 ok``.
"""

from __future__ import annotations

import os
import random
import sys
import tempfile
import time
from pathlib import Path
from typing import Any

from sqlalchemy import text
from tl_adapters import queue
from tl_adapters.db import (
    as_target,
    create_schema,
    dialect_of,
    make_uow_factory,
    open_uow,
    rebuild_projections,
)
from tl_adapters.postgres import admin
from tl_core.jobs import JobRunner
from tl_core.util import new_ulid
from tl_mod_awp import rollup
from tl_mod_awp.commands import AWP_COMMANDS
from tl_mod_awp.worker import RollupKind, build_worker
from tl_mod_cost.testing import CostWorld, row
from tl_schema.ddl_loader import statements

SCOPE = "project:P123"
SPEC = {c.model.__name__: c for c in AWP_COMMANDS}
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


def check(ok: bool, what: str) -> None:
    if not ok:
        sys.exit(f"FAIL {what}")
    print(f"PASS {what}")


class W:
    def __init__(self, db: Any) -> None:
        self.db = db
        create_schema(db)
        for table in ("cur_awp_cwp", "cur_awp_cwp_allocation"):  # S4's projector will own these
            for ddl in statements(table, dialect_of(db)):
                self.sql(ddl)

    def call(self, name: str, scope: str = SCOPE, **f: Any) -> Any:
        c = SPEC[name]
        with open_uow(self.db) as uow:
            return c.handler(uow, c.model(actor="user:sue", source="accept", scope=scope, **f))

    def sql(self, q: str, **p: Any) -> list[Any]:
        with open_uow(self.db) as uow:
            r = uow.conn().execute(text(q), p)
            return list(r.mappings()) if r.returns_rows else []

    def one(self, q: str, **p: Any) -> Any:
        return self.sql(q, **p)[0]["v"]

    def id_of(self, code: str, scope: str = SCOPE) -> str:
        q = "SELECT id AS v FROM cur_core_record WHERE scope = :s AND key = :k"
        return str(self.one(q, s=scope, k=code))

    def cwp(
        self, hours: str, allocs: dict[str, str], *, state: str = "Planned", void: bool = False,
        scope: str = SCOPE,
    ) -> None:  # fmt: skip
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
        q = "SELECT state AS v FROM job_queue WHERE job_id = :j"
        return str(self.one(q, j=rollup.job_id(scope)))


def main_scope(w: W) -> None:
    CostWorld(w.db).import_snapshot(
        [row("WLD", "Welding"), row("ERC", "Erection"), row("TST", "T")]
    )
    tree = [("1", None), ("1.1", "1"), ("1.1.1", "1.1"), ("1.1.2", "1.1")]
    for code, parent in (*tree, *((f"1.{k}", "1") for k in range(2, 7))):
        w.call("DefineWbsNode", code=code, title=f"N{code}", parent_code=parent)

    def lines(*p: tuple[str, str]) -> list[dict[str, str]]:
        return [{"cost_code": c, "percent": x} for c, x in p]

    w.call(
        "MapWbsToCostCodes",
        node=w.id_of("1.1.1"),
        allocations=lines(("WLD", "60.00"), ("ERC", "40.00")),
    )
    three = lines(("WLD", "33.33"), ("ERC", "33.33"), ("TST", "33.34"))
    w.call("MapWbsToCostCodes", node=w.id_of("1.2"), allocations=three)
    n = {c: w.id_of(c) for c in ("1.1.1", "1.1.2", "1.2", "1.3", "1.4", "1.5", "1.6")}
    w.cwp("100.0", {n["1.1.1"]: "100.00"})
    w.cwp("999.0", {n["1.1.1"]: "100.00"}, void=True)
    w.cwp("25.0", {n["1.1.2"]: "100.00"})
    w.cwp("10.0", {n["1.2"]: "100.00"})
    w.cwp("5.0", {n["1.3"]: "5.00"})  # 0.25 h
    w.cwp("7.0", {n["1.4"]: "5.00"})  # 0.35 h
    w.cwp("1.0", {n["1.6"]: "5.00"})  # 0.05 h
    for s in STATES:
        w.cwp("10.0", {n["1.5"]: "100.00"}, state=s)
    w.cwp("500.0", {n["1.5"]: "100.00"}, void=True)
    check(w.run_once() == "done", "first run done")
    f = w.figs()
    check(f["1.1.1"] == {"total": "100.0", "WLD": "60.0", "ERC": "40.0"}, "60/40 leaf of 100.0 h")
    check(f["1.1"]["total"] == "125.0" and f["1.1"]["unallocated"] == "25.0", "parent sums leaves")
    root = {"total": "195.6", "WLD": "63.3", "ERC": "43.3", "TST": "3.3", "unallocated": "85.7"}
    check(f["1"] == root, "root: exact sum 195.65 -> 195.6, parts sum to it")
    check(
        f["1.2"] == {"total": "10.0", "WLD": "3.3", "ERC": "3.3", "TST": "3.4"},
        "33.33/33.33/33.34 largest remainder",
    )
    check(f["1.3"]["total"] == "0.2" and f["1.4"]["total"] == "0.4", "0.25 -> 0.2 and 0.35 -> 0.4")
    check("1.6" not in f, "0.05 -> 0.0 (tie to even): no row")
    check(
        f["1.1.2"] == {"total": "25.0", "unallocated": "25.0"},
        "leaf without cost codes: unallocated",
    )
    check(f["1.5"]["total"] == "60.0", "void CWPs excluded, six states counted")
    before = w.events()
    w.request()
    check(
        w.run_once() == "done" and w.events() == before,
        "a second run with no change appends nothing",
    )


def later(w: W) -> None:
    before = w.events()
    q = "UPDATE cur_awp_cwp SET budget_hours = '9.0' WHERE id IN "
    q += "(SELECT cwp_id FROM cur_awp_cwp_allocation WHERE wbs_node_id = :n)"
    w.sql(q, n=w.id_of("1.3"))  # 0.45 h -> 0.4
    w.request()
    w.run_once()
    changed = w.events() - before == 2 and w.figs()["1.3"]["total"] == "0.4"
    check(changed, "a changed figure appends only the nodes that differ (the leaf and the root)")

    class Midway(RollupKind):  # two requests arrive while the run is `running` (D-c)
        def run(self, work: Any) -> Any:
            for a, b in (("70.00", "30.00"), ("20.00", "80.00")):
                lines = [{"cost_code": "WLD", "percent": a}, {"cost_code": "ERC", "percent": b}]
                w.call("MapWbsToCostCodes", node=w.id_of("1.2"), allocations=lines)
            check(w.state() == "running", "a request leaves a running row alone")
            return super().run(work)

    w.request()
    factory = make_uow_factory(w.db)
    with factory() as uow:
        runner = JobRunner(factory, queue.job_queue_for(uow.conn()), [Midway()])
    runner.run_once()
    factory.dispose()
    n = w.one("SELECT COUNT(*) AS v FROM job_queue WHERE kind = 'awp.rollup'")
    check(w.state() == "queued" and n == 1, "D-c: two requests while running queue one new run")
    w.run_once()
    want = {"total": "10.0", "WLD": "2.0", "ERC": "8.0"}
    check(
        w.figs()["1.2"] == want and w.state() == "done",
        "the new run applies the late change, no third",
    )
    mine = w.sql(ROWS)
    rebuild_projections(w.db)
    check(w.sql(ROWS) == mine, "rebuild of projections equals the incremental table")
    ev = w.sql(
        "SELECT correlation_id, source, payload FROM events WHERE event_type LIKE '%RolledUp'"
    )
    ok = all(
        e["source"] == "job:awp.rollup" and e["correlation_id"].startswith("rollup:")
        and e["correlation_id"][7:] in e["payload"]
        for e in ev
    )  # fmt: skip
    check(bool(ev) and ok, "correlation id rollup:<run id> and source job:awp.rollup on the events")
    feed = "SELECT COUNT(*) AS v FROM cur_feed_items WHERE event_type LIKE '%RolledUp'"
    check(w.one(feed) == 0, "the event makes no feed card")


def bound(w: W) -> None:
    scope = "project:P124"
    w.call("DefineWbsNode", scope, code="R", title="R")
    for k in range(500):
        w.call("DefineWbsNode", scope, code=f"L{k}", title="L", parent_code="R")
        w.cwp("1.0", {w.id_of(f"L{k}", scope): "100.00"}, scope=scope)
    before = w.events()
    w.request(scope)
    w.run_once()
    first, left = w.events() - before, w.state(scope)
    check(first == 500 and left == "queued", "501 changed nodes: 500 appended, a re-queue left")
    w.run_once()
    check(
        w.events() - before == 501 and w.state(scope) == "done",
        "the re-queued run appends the last",
    )


def bench(w: W) -> None:
    scope, rnd = "project:P125", random.Random(5)
    for k in range(5000):
        parent = None if k == 0 else f"B{(k - 1) // 6}"
        w.call("DefineWbsNode", scope, code=f"B{k}", title="B", parent_code=parent)
    q = "SELECT id FROM cur_awp_wbs_node WHERE scope = :s AND id NOT IN "
    q += "(SELECT parent_id FROM cur_awp_wbs_node WHERE parent_id IS NOT NULL)"
    leaves = [r["id"] for r in w.sql(q, s=scope)]
    for _ in range(2000):
        hours = f"{rnd.randint(1, 9999)}.{rnd.randint(0, 9)}"
        w.cwp(hours, {n: "50.00" for n in rnd.sample(leaves, 2)}, scope=scope)
    w.request(scope)
    t = time.perf_counter()
    w.run_once()
    one, runs = time.perf_counter() - t, 1
    while w.state(scope) == "queued":
        w.run_once()
        runs += 1
    total = time.perf_counter() - t
    print(f"BENCH 5000 nodes x 2000 CWPs: first run {one:.2f} s (500 nodes appended); "
          f"{runs} runs to settle all in {total:.2f} s")  # fmt: skip


def one_backend(db: Any) -> dict[str, dict[str, str]]:
    w = W(db)
    main_scope(w)
    later(w)
    bound(w)
    bench(w)
    return w.figs()


def main() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        sqlite = one_backend(as_target(str(Path(tmp) / "s5.db")))
        pg = os.environ.get("TL_PG_URL")
        if pg and admin.reachable(pg):
            schema = "tl_s5_" + new_ulid()[-10:].lower()
            admin.create_schema_namespace(pg, schema)
            try:
                same = one_backend(as_target(admin.schema_url(pg, schema))) == sqlite
            finally:
                admin.drop_schema_namespace(pg, schema)
            check(same, "Postgres figures equal SQLite figures")
    print("S5 ok")


main()
