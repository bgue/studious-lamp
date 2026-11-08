"""S4: the readiness engine, job, hooks and reads (P2-I2-S4, with the S4 review F1 to F3 notes).

The harness is ``dev/accept/P2-I2/s4_world.py`` (stand-in checks, a clock, hand-written constraint
rows); each test builds its own SQLite world. The twin and the scanned-stream rule are asserted at
the end of the file.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

import pytest

ACCEPT = Path(__file__).resolve().parents[5] / "dev" / "accept" / "P2-I2"
sys.path.insert(0, str(ACCEPT))
import s4_world as sw  # noqa: E402  # pyright: ignore[reportMissingImports]
from awp_world import SCOPE, World, hidden_record  # noqa: E402
from sqlalchemy import text  # noqa: E402
from tl_adapters.db import make_uow_factory, open_uow, rebuild_projections  # noqa: E402
from tl_adapters.queue import job_queue_for  # noqa: E402
from tl_core import constraints  # noqa: E402
from tl_core.jobs import JobRunner  # noqa: E402
from tl_core.readiness.types import RecordRef  # noqa: E402
from tl_core.services.feed_queries import list_feed  # noqa: E402
from tl_core.services.link_queries import links_of  # noqa: E402
from tl_core.services.queries import get_record_by_id, record_history  # noqa: E402
from tl_core.util import new_ulid  # noqa: E402
from tl_mod_awp import readiness as rd  # noqa: E402
from tl_mod_awp.readiness import engine, hooks, views  # noqa: E402
from tl_mod_awp.readiness.job import ReadinessKind  # noqa: E402
from tl_mod_awp.worker import build_worker  # noqa: E402

EVAL = "IWP.ReadinessEvaluated"
READY = "IWP.Ready"


@pytest.fixture
def w(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> World:
    import tl_adapters.sqlite.uow as sqlite_uow

    world = sw.build(tmp_path / "s4.db")
    monkeypatch.setattr(sqlite_uow, "default_registry", lambda: sw.registry())
    return world


def ev(w: World, iwp: str, cs: Any, **kw: Any) -> Any:
    return sw.run(w, rd.evaluate_now, iwp, sw.TODAY, cs, **kw)


def sql(w: World, statement: str, **params: Any) -> None:
    with open_uow(w.db) as uow:
        uow.conn().execute(text(statement), params)


def one_check(view: Any, name: str) -> Any:
    return {c.name: c for c in view.checks}[name]


def in_check(w: World, title: str = "Rack secret") -> str:
    i = w.iwp(title=title)
    w.set_status(i, "Constraint check")
    return i


# --- evaluation, ready true / false / unknown, the moves ---------------------------------------


def test_one_event_and_rows_equal_the_view(w: World) -> None:
    cs = sw.checks(sw.Stand("zz_doc"), sw.Stand("zz_odd", "n_a"))
    i = in_check(w)
    first = ev(w, i, cs)
    key = w.column("cur_core_record", "key", i)
    with open_uow(w.db, readonly=True) as u:
        assert views.readiness(u.conn(), SCOPE, key) == first
    assert first.ready and sw.count(w, i, EVAL) == 1


def test_nine_checks_and_n_a_counts_as_passing(w: World) -> None:
    i = in_check(w)
    view = ev(w, i, None)  # the real registry
    assert len(view.checks) == 9
    assert {c.name for c in view.checks} >= {
        "constraints_cleared",
        "documents_current",
        "rfis_answered",
    }
    assert [c.name for c in view.checks] == sorted(c.name for c in view.checks)
    only_na = ev(w, in_check(w), sw.checks(sw.Stand("zz_odd", "n_a")))
    assert only_na.ready  # n_a passes, and so does the constraints check with no constraints


@pytest.mark.parametrize("state", ["blocked", "pending", "unknown"])
def test_not_ok_states_make_ready_false(w: World, state: str) -> None:
    i = in_check(w)
    assert not ev(w, i, sw.checks(sw.Stand("zz_doc", state))).ready
    assert w.state(i) == "Constraint check"


def test_ready_turns_true_once_and_event_fires_once(w: World) -> None:
    stand = sw.Stand("zz_doc", "blocked")
    cs = sw.checks(stand)
    i = in_check(w)
    assert not ev(w, i, cs).ready and sw.count(w, i, READY) == 0
    stand.state = "n_a"
    assert ev(w, i, cs).ready and sw.count(w, i, READY) == 1
    assert ev(w, i, cs).ready and sw.count(w, i, READY) == 1  # still ready: no new event


def test_constraint_check_and_ready_moves_both_ways(w: World) -> None:
    stand = sw.Stand("zz_doc", "ok")
    cs = sw.checks(stand)
    i = in_check(w)
    assert ev(w, i, cs).ready and w.state(i) == "Ready"
    stand.state = "blocked"
    assert not ev(w, i, cs).ready and w.state(i) == "Constraint check"


def test_other_states_do_not_move_and_get_no_ready_event(w: World) -> None:
    stand = sw.Stand("zz_doc", "blocked")
    cs = sw.checks(stand)
    i = in_check(w)
    w.set_status(i, "Issued")
    assert not ev(w, i, cs).ready and w.state(i) == "Issued"
    stand.state = "ok"
    draft = ev(w, w.iwp(), cs)
    assert draft.ready and sw.count(w, draft.iwp_id, READY) == 0  # S4 review F2


def test_ready_event_only_when_ready_after_the_move(w: World) -> None:
    cs = sw.checks(sw.Stand("zz_doc", "ok"))
    i = in_check(w)
    assert ev(w, i, cs).ready
    assert sw.count(w, i, READY) == 1 and w.state(i) == "Ready"


# --- bounds -------------------------------------------------------------------------------------


@pytest.mark.parametrize("mode", ["raise", "slow", "many", "over"])
def test_a_check_out_of_bounds_is_unknown_with_a_fixed_detail(w: World, mode: str) -> None:
    clock = sw.Clock()
    stand = sw.Stand("zz_doc", "blocked", mode=mode)
    stand.clock = clock
    i = in_check(w)
    view = ev(w, i, sw.checks(stand), clock=clock)
    got = one_check(view, "zz_doc")
    assert got.state == "unknown"
    assert "secret" not in got.detail and "boom" not in got.detail
    assert not view.ready


# --- constraints_cleared and the guard ---------------------------------------------------------


def test_constraints_cleared_counts_open_blocking_ready_constraints_only(w: World) -> None:
    z = w.iwp()
    open_id = sw.constraint_row(w, z, "ready", "blocking", None)
    sw.constraint_row(w, z, "ready", "blocking", "Cleared")
    sw.constraint_row(w, z, "start", "blocking", None)
    sw.constraint_row(w, z, "ready", "advisory", None)
    got = one_check(ev(w, z, sw.checks()), "constraints_cleared")
    assert got.state == "blocked" and got.detail == "1 open blocking constraints"
    assert (got.count_ok, got.count_total) == (1, 2)
    assert [r.record_id for r in got.resolve_via] == [open_id]
    sql(w, "UPDATE cur_core_record SET status = 'Cleared' WHERE id = :i", i=open_id)
    last = one_check(ev(w, z, sw.checks()), "constraints_cleared")
    assert last.state == "ok" and last.count_ok == 2


def test_guard_refusal_is_recorded_as_the_constraints_cleared_detail(w: World) -> None:
    cs = sw.checks(sw.Stand("zz_doc", "ok"))
    i = in_check(w)
    with open_uow(w.db, readonly=True) as u:
        evaluation = engine.evaluate(u.conn(), i, sw.TODAY, cs)
    assert evaluation.results and all(r.state == "ok" for r in evaluation.results)
    # a blocking constraint arrives between the read and the write: the guard refuses the move
    sw.run(
        w,
        constraints.raise_constraint,
        subject_id=i,
        phase="ready",
        severity="blocking",
        category="other",
        source="rule",
        check_name=None,
        facts_hash=None,
        by_module="awp",
    )
    view = sw.run(w, engine.record, evaluation, cs)
    got = one_check(view, "constraints_cleared")
    assert not view.ready and got.state == "blocked" and got.detail
    assert w.state(i) == "Constraint check"
    assert sw.count(w, i, READY) == 0


def test_check_sourced_constraints_raise_and_clear(w: World) -> None:
    stand = sw.Stand("zz_doc", "blocked")
    cs = sw.checks(stand)
    i = in_check(w)
    view = ev(w, i, cs)
    raised = w.rows("SELECT check_name, source FROM cur_core_constraint WHERE subject_id = :i", i=i)
    assert [(r["check_name"], r["source"]) for r in raised] == [("zz_doc", "check")]
    assert not view.ready
    stand.state = "ok"
    again = ev(w, i, cs)
    open_now = w.scalar(
        "SELECT COUNT(*) FROM cur_core_constraint c JOIN cur_core_record r ON r.id = c.id "
        "WHERE c.subject_id = :i AND r.status = 'Cleared'",
        i=i,
    )
    assert open_now == 1 and again.ready and w.state(i) == "Ready"


# --- hooks and jobs ----------------------------------------------------------------------------


@pytest.fixture
def line(w: World, monkeypatch: pytest.MonkeyPatch) -> tuple[str, Any]:
    cs = sw.checks(sw.Stand("zz_line", watches=("zz.Line", "zz.Other", "awp.IWP")))
    two = in_check(w, "x")
    sql(w, "DELETE FROM job_queue")
    sql(w, "CREATE TABLE zz_line (id TEXT, work_package_id TEXT)")
    sql(w, "INSERT INTO zz_line VALUES ('L1', :wp)", wp=two)
    monkeypatch.setitem(hooks.WORK_PACKAGE_TABLES, "zz.Line", "zz_line")
    return two, cs


def on(w: World, cs: Any, t: str, i: str, s: str = "test") -> int:
    return sw.run(w, hooks.on_event, sw.fake_event(t, i, s), cs)


def test_request_is_idempotent_and_skips_non_iwps(w: World) -> None:
    two = w.iwp()
    assert sw.run(w, rd.request, [two, two, "nope"], reason="t") == 1
    assert sw.run(w, rd.request, [two], reason="t") == 0


def test_event_maps_by_work_package_id(w: World, line: tuple[str, Any]) -> None:
    _, cs = line
    assert on(w, cs, "zz.Line", "L1") == 1
    assert on(w, cs, "zz.Line", "L1") == 0  # already queued


def test_own_events_are_ignored(w: World, line: tuple[str, Any]) -> None:
    two, cs = line
    assert on(w, cs, "awp.IWP", two, "job:awp.readiness") == 0


def test_event_without_a_mapping_falls_back_to_check_and_ready_iwps(
    w: World, line: tuple[str, Any]
) -> None:
    _, cs = line
    other = w.iwp()  # a Draft: not in the fallback
    assert on(w, cs, "zz.Other", "X") == 1
    assert other


def test_job_runs_once_and_rebuild_equals_incremental(w: World, line: tuple[str, Any]) -> None:
    two, cs = line
    assert on(w, cs, "zz.Line", "L1") == 1
    factory = make_uow_factory(w.db, registry=sw.registry())
    with factory() as uow:
        queue = job_queue_for(uow.conn())
    runner = JobRunner(factory, queue, [ReadinessKind(lambda: cs, lambda: sw.TODAY)])
    assert len(runner.run_until_idle()) == 1
    assert sw.count(w, two, EVAL) == 1
    before = sw.tables(w)
    rebuild_projections(w.db)
    assert sw.tables(w) == before


def test_worker_serves_the_readiness_kind(w: World) -> None:
    assert "awp.readiness" in build_worker(w.db).runner.kinds


def queue_rows(w: World, job: str) -> list[dict[str, Any]]:
    return w.rows("SELECT * FROM job_queue WHERE job_id = :j", j=job)


def test_requeue_one_queued_run_per_iwp_and_the_lease_is_respected(w: World) -> None:
    """S4 review F3: the raw requeue UPDATE keeps one row per IWP and never touches a leased run."""
    i = w.iwp()
    job = f"ready:{i}"
    assert sw.run(w, rd.request, [i], reason="t") == 1
    assert sw.run(w, rd.request, [i], reason="t") == 0  # queued: not queued twice
    sql(
        w,
        "UPDATE job_queue SET state = 'running', lease_owner = 'w1', "
        "lease_until = '2999-01-01T00:00:00Z' WHERE job_id = :j",
        j=job,
    )
    assert sw.run(w, rd.request, [i], reason="t") == 0  # running under a lease: left alone
    held = queue_rows(w, job)
    assert len(held) == 1 and held[0]["lease_owner"] == "w1" and held[0]["state"] == "running"
    sql(
        w,
        "UPDATE job_queue SET state = 'done', lease_owner = NULL, lease_until = NULL "
        "WHERE job_id = :j",
        j=job,
    )
    assert sw.run(w, rd.request, [i], reason="t") == 1  # finished: queued again, same row
    again = queue_rows(w, job)
    assert len(again) == 1 and again[0]["state"] == "queued" and again[0]["attempt"] == 0


# --- no text, the twin and the scanned-stream rule ---------------------------------------------


def test_events_carry_ids_only_and_no_record_text(w: World) -> None:
    stand = sw.Stand("zz_doc", "blocked")
    i = in_check(w)
    ev(w, i, sw.checks(stand))
    rows = w.rows("SELECT payload FROM events WHERE event_type = :t", t=EVAL)
    found = [c for r in rows for c in json.loads(r["payload"])["checks"]]
    assert found
    assert all(all(x["key"] == x["record_id"] for x in c["resolve_via"]) for c in found)
    assert all("Rack secret" not in r["payload"] for r in rows)


def test_hidden_and_missing_refs_are_dropped_and_no_hidden_id_or_key_is_readable(
    w: World,
) -> None:
    hidden = hidden_record(w)
    hidden_key = w.column("cur_core_record", "key", hidden)
    stand = sw.Stand("zz_rfi", "blocked")
    stand.refs = [
        RecordRef(record_id=hidden, record_type="x.Rfi", key=hidden_key or "RFI-0001"),
        RecordRef(record_id=new_ulid(), record_type="x.Rfi", key="RFI-9999"),  # not a record
    ]
    iwp = w.iwp()
    shown = one_check(ev(w, iwp, sw.checks(stand)), "zz_rfi")
    assert shown.detail.endswith("1 reference not found") and len(shown.resolve_via) == 1
    with open_uow(w.db, readonly=True) as u:  # the lowest-clearance viewer
        reads = [
            str([e.payload for e in record_history(u, iwp)]),
            str(list_feed(u, SCOPE, record_id=iwp, include_linked=True)),
            str(get_record_by_id(u, iwp)),
            str(get_record_by_id(u, hidden)),
            str(links_of(u, iwp)),
            str(list_feed(u, SCOPE, limit=200)),
        ]
    leaks = [t for t in reads if hidden in t or (hidden_key and hidden_key in t) or "RFI-9999" in t]
    assert not leaks and reads[3] == "None"


def test_readiness_event_naming_a_hidden_record_is_hidden_whole(w: World) -> None:
    """ADR-0016 scanned-stream rule: no per-viewer redaction, the whole event is hidden."""
    hidden = hidden_record(w)
    stand = sw.Stand("zz_rfi", "blocked")
    stand.refs = [RecordRef(record_id=hidden, record_type="x.Rfi", key=hidden)]
    iwp = w.iwp()
    sw.run(w, rd.evaluate_now, iwp, sw.TODAY, sw.checks(stand))
    with open_uow(w.db, readonly=True) as u:
        types = [e.event_type for e in record_history(u, iwp)]
    assert EVAL not in types
