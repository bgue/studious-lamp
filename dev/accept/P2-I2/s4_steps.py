"""The steps of dev/accept/P2-I2/S4.py (each prints ``PASS <name>`` or exits)."""

from __future__ import annotations

import json
import sys
from typing import Any

import s4_world as sw
from sqlalchemy import text
from tl_adapters.db import make_uow_factory, open_uow, rebuild_projections
from tl_adapters.queue import job_queue_for
from tl_core.jobs import JobRunner
from tl_core.readiness.types import RecordRef
from tl_core.services.queries import record_history
from tl_core.util import new_ulid
from tl_mod_awp import readiness as rd
from tl_mod_awp.readiness import hooks, views
from tl_mod_awp.readiness.job import ReadinessKind
from tl_mod_awp.worker import build_worker

EVAL = "IWP.ReadinessEvaluated"


def ok(name: str, cond: Any = True) -> None:
    sys.exit(f"FAIL {name}") if not cond else print(f"PASS {name}")


def ev(w: Any, iwp: str, cs: Any, **kw: Any) -> Any:
    return sw.run(w, rd.evaluate_now, iwp, sw.TODAY, cs, **kw)


def sql(w: Any, statement: str, **params: Any) -> None:
    with open_uow(w.db) as uow:
        uow.conn().execute(text(statement), params)


def evaluation(w: Any, c2: bool, seen: list[Any]) -> str:
    a, b = sw.Stand("zz_doc"), sw.Stand("zz_odd", "n_a")
    cs = sw.checks(a, b)
    one = w.iwp(title="Rack secret")
    key, first = w.column("cur_core_record", "key", one), ev(w, one, cs)
    with open_uow(w.db, readonly=True) as u:
        same = views.readiness(u.conn(), sw.SCOPE, key) == first
    ok("one event, rows equal the view", sw.count(w, one, EVAL) == 1 and same and first.ready)
    a.state = "blocked"
    ok("blocked stand-in: not ready", not ev(w, one, cs).ready and (c2 or seen))
    a.state = "n_a"
    turned = ev(w, one, cs).ready
    ok("turn to ready: IWP.Ready again", turned and sw.count(w, one, "IWP.Ready") == 2)
    ok("still ready: no new IWP.Ready", ev(w, one, cs).ready and sw.count(w, one, "IWP.Ready") == 2)
    w.set_status(one, "Constraint check")
    ok("Constraint check -> Ready", ev(w, one, cs).ready and w.state(one) == "Ready")
    a.state = "blocked"
    ok("Ready -> Constraint check", not ev(w, one, cs).ready and w.state(one) == "Constraint check")
    w.set_status(one, "Issued")
    ok("other state: no move", not ev(w, one, cs).ready and w.state(one) == "Issued")
    print("SKIP needs C2 (guard refusal)" if not c2 else "guard refusal: see rerun after C2")
    return one


def bounds(w: Any, one: str) -> None:
    clock, a = sw.Clock(), sw.Stand("zz_doc", "blocked")
    cs = sw.checks(a)
    for mode in ("raise", "slow", "many", "over"):
        a.mode, a.clock = mode, clock
        view = ev(w, one, cs, clock=clock)
        got = {c.name: c for c in view.checks}["zz_doc"]
        ok(
            f"{mode}: unknown, fixed detail, not ready",
            got.state == "unknown" and "secret" not in got.detail and not view.ready,
        )


def hooks_and_jobs(w: Any) -> None:
    two = w.iwp()
    cs = sw.checks(sw.Stand("zz_line", watches=("zz.Line", "zz.Other", "awp.IWP")))
    ok(
        "request idempotent",
        rd.request.__name__ == "request"
        and sw.run(w, rd.request, [two, two, "nope"], reason="t") == 1
        and sw.run(w, rd.request, [two], reason="t") == 0,
    )
    w.set_status(two, "Constraint check")
    sql(w, "DELETE FROM job_queue")
    sql(w, "CREATE TABLE zz_line (id TEXT, work_package_id TEXT)")
    sql(w, "INSERT INTO zz_line VALUES ('L1', :wp)", wp=two)
    hooks.WORK_PACKAGE_TABLES["zz.Line"] = "zz_line"
    on = lambda t, i, s="test": sw.run(w, hooks.on_event, sw.fake_event(t, i, s), cs)  # noqa: E731
    ok("work_package_id maps", on("zz.Line", "L1") == 1 and on("zz.Line", "L1") == 0)
    sql(w, "DELETE FROM job_queue")
    ok("own event ignored", on("awp.IWP", two, "job:awp.readiness") == 0)
    ok("no mapping: fallback to Constraint check and Ready IWPs", on("zz.Other", "X") == 1)
    factory = make_uow_factory(w.db, registry=sw.registry())
    with factory() as uow:
        queue = job_queue_for(uow.conn())
    runner = JobRunner(factory, queue, [ReadinessKind(lambda: cs, lambda: sw.TODAY)])
    ok("the job ran", len(runner.run_until_idle()) == 1 and sw.count(w, two, EVAL) == 1)
    before = sw.tables(w)
    rebuild_projections(w.db)
    after = sw.tables(w)
    ok("rebuild equals incremental", after == before)
    ok("worker serves the kind", "awp.readiness" in build_worker(w.db).runner.kinds)


def no_text(w: Any, one: str, hidden: str) -> None:
    rows = w.rows("SELECT payload FROM events WHERE event_type = :t", t=EVAL)
    found = [c for r in rows for c in json.loads(r["payload"])["checks"]]
    ok(
        "ids only, no record text",
        found
        and all(
            all(x["key"] == x["record_id"] for x in c["resolve_via"]) and "Rack" not in c["detail"]
            for c in found
        )
        and all("Rack secret" not in r["payload"] for r in rows),
    )
    twin = []
    for ref in (hidden, new_ulid()):  # a restricted blocker, a missing one
        stand = sw.Stand("zz_rfi", "blocked")
        stand.refs = [RecordRef(record_id=ref, record_type="x.Rfi", key="RFI-0001")]
        iwp = w.iwp()
        ev(w, iwp, sw.checks(stand))
        with open_uow(w.db, readonly=True) as u:
            twin.append(" ".join(str(e.payload) for e in record_history(u, iwp)))
    ok(
        "low-clearance history names no hidden record, no key",
        all(hidden not in t and "RFI-0001" not in t for t in twin) and "zz_rfi" not in twin[0],
    )


def constraint_check(w: Any) -> None:
    z = w.iwp()
    open_id = sw.constraint_row(w, z, "ready", "blocking", None)
    sw.constraint_row(w, z, "ready", "blocking", "Cleared")
    sw.constraint_row(w, z, "start", "blocking", None)
    sw.constraint_row(w, z, "ready", "advisory", None)
    first = [c for c in ev(w, z, sw.checks()).checks if c.name == "constraints_cleared"][0]
    ok(
        "constraints_cleared: open blocking ready ones only",
        first.state == "blocked"
        and first.detail == "1 open blocking constraints"
        and (first.count_ok, first.count_total) == (1, 2)
        and [r.record_id for r in first.resolve_via] == [open_id],
    )
    sql(w, "UPDATE cur_core_record SET status = 'Cleared' WHERE id = :i", i=open_id)
    last = [c for c in ev(w, z, sw.checks()).checks if c.name == "constraints_cleared"][0]
    ok("constraints_cleared: none open is ok", last.state == "ok" and last.count_ok == 2)
