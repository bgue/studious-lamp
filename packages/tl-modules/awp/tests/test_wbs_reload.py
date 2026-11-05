"""Reinstating a WBS node and the reload after a compensated load (S7)."""

from __future__ import annotations

import csv
from pathlib import Path
from typing import Any

import pytest
import tl_mod_awp
from awp_world import SCOPE, World, hidden_record, refuses
from sqlalchemy import text
from tl_adapters.db import open_uow
from tl_core.auth.errors import ForbiddenError
from tl_core.services.errors import RecordNotFoundError
from tl_core.util import new_ulid
from tl_mod_awp.errors import InUseError, WbsRuleError
from tl_mod_awp.targets import wbs_target
from tl_mod_legacy.model import Grid, LoaderDef

LD = LoaderDef("l", "acc", "t", "x", "d", "")
WHO: dict[str, Any] = {"actor": "user:sue", "source": "legacy:acc"}
SAMPLE = Path(tl_mod_awp.__file__).parent / "samples" / "wbs-sample.csv"
TREE_SQL = (
    "SELECT n.code, n.parent_id, n.position, n.depth, n.retired, "
    "(SELECT group_concat(a.cost_code_id || '=' || a.percent) FROM cur_awp_wbs_allocation a "
    "WHERE a.node_id = n.id) AS lines FROM cur_awp_wbs_node n ORDER BY n.code"
)


@pytest.fixture
def loaded(world: World) -> World:
    world.cost_codes(("WLD", "Weld"), ("ERC", "Erect"), ("TST", "Test"))
    return world


def _grid() -> Grid:
    with SAMPLE.open() as f:
        got = list(csv.reader(f))
    return Grid(got[0], [list(r) for r in got[1:]])


def _run(w: World, fn: Any) -> Any:
    with open_uow(w.db) as u:
        return fn(u)


def _plan(w: World) -> Any:
    return _run(w, lambda u: wbs_target().plan(u.conn(), SCOPE, LD, _grid()))


def _load(w: World, cid: str) -> list[Any]:
    def go(u: Any) -> Any:
        t = wbs_target()
        plan = t.plan(u.conn(), SCOPE, LD, _grid())
        return t.apply(u, SCOPE, LD, plan, correlation_id=cid, confidentiality=None, **WHO)

    return _run(w, go)


def _compensate(w: World, ids: list[str], cid: str) -> int:
    back = {"correlation_id": cid, "reason": "undo", **WHO}
    return int(_run(w, lambda u: wbs_target().reverse(u, SCOPE, ids, **back)))


def _tree(w: World) -> list[dict[str, Any]]:
    return w.rows(TREE_SQL)


def test_reload_after_compensation_recreates_the_same_tree(loaded: World) -> None:
    made = _load(loaded, "load:1")
    ids = [c.record_id for c in made]
    first = _tree(loaded)
    records = loaded.scalar("SELECT COUNT(*) FROM cur_core_record")
    assert len(made) == 12 and _compensate(loaded, ids, "comp:1") == 12
    assert all(r["retired"] for r in _tree(loaded))
    plan = _plan(loaded)
    assert (len(plan.rows), len(plan.existing)) == (12, 0)
    again = _load(loaded, "load:2")
    assert sorted(c.record_id for c in again) == sorted(ids)
    assert _tree(loaded) == first
    assert loaded.scalar("SELECT COUNT(*) FROM cur_core_record") == records
    assert (
        loaded.scalar("SELECT COUNT(*) FROM events WHERE event_type = 'WBSNode.Reinstated'") == 12
    )
    assert _compensate(loaded, ids, "comp:2") == 12
    assert all(r["retired"] for r in _tree(loaded))


def test_a_live_node_stays_existing_and_a_reload_of_a_live_tree_writes_nothing(
    loaded: World,
) -> None:
    _load(loaded, "load:1")
    plan = _plan(loaded)
    assert (len(plan.rows), len(plan.existing)) == (0, 12)


def test_a_retired_node_of_another_parent_stays_existing(loaded: World) -> None:
    made = _load(loaded, "load:1")
    ids = [c.record_id for c in made]
    _compensate(loaded, ids, "comp:1")
    g = _grid()
    for r in g.rows:
        if r[0] == "1.1.2":
            r[2] = "2.2"
    plan = _run(loaded, lambda u: wbs_target().plan(u.conn(), SCOPE, LD, g))
    assert (len(plan.rows), plan.existing) == (11, ["1.1.2"])


def test_a_cwp_allocates_to_a_reinstated_leaf_and_blocks_its_retire(loaded: World) -> None:
    ids = [c.record_id for c in _load(loaded, "load:1")]
    _compensate(loaded, ids, "comp:1")
    _load(loaded, "load:2")
    loaded.areas_and_path(("A1",))
    cwp = loaded.new_cwp("PIP", "Rack", "A1")
    loaded.call(
        "uma",
        "AllocateCwpToWbs",
        cwp=cwp,
        allocations=[{"wbs_code": "1.1.1", "percent": "100.00"}],
    )
    with open_uow(loaded.db) as u:
        refuses(
            InUseError,
            lambda: wbs_target().reverse(u, SCOPE, ids, correlation_id="c3", reason="r", **WHO),
        )


def test_reinstate_guards(loaded: World) -> None:
    for code, parent in (("1", None), ("1.1", "1")):
        loaded.call("sue", "DefineWbsNode", code=code, title=code, parent_code=parent)
    parent, leaf = loaded.id_of("1"), loaded.id_of("1.1")
    refuses(WbsRuleError, lambda: loaded.call("sue", "ReinstateWbsNode", node=leaf, reason="x"))
    loaded.call("sue", "RetireWbsNode", node=leaf, reason="x")
    loaded.call("sue", "RetireWbsNode", node=parent, reason="x")
    refuses(WbsRuleError, lambda: loaded.call("sue", "ReinstateWbsNode", node=leaf, reason="x"))
    loaded.call("sue", "ReinstateWbsNode", node=parent, reason="x")
    loaded.call("sue", "ReinstateWbsNode", node=leaf, reason="x")
    assert not any(r["retired"] for r in _tree(loaded))
    refuses(ForbiddenError, lambda: loaded.call("uma", "ReinstateWbsNode", node=leaf, reason="x"))


def test_a_hidden_record_answers_as_a_missing_one(loaded: World) -> None:
    hidden, absent = hidden_record(loaded), new_ulid()
    a = refuses(
        RecordNotFoundError,
        lambda: loaded.call("sue", "ReinstateWbsNode", node=hidden, reason="x"),
    )
    b = refuses(
        RecordNotFoundError,
        lambda: loaded.call("sue", "ReinstateWbsNode", node=absent, reason="x"),
    )
    assert str(a).replace(hidden, "ID") == str(b).replace(absent, "ID")


def test_a_reinstatement_asks_for_a_rollup(loaded: World) -> None:
    loaded.call("sue", "DefineWbsNode", code="1", title="One")
    node = loaded.id_of("1")
    loaded.call("sue", "RetireWbsNode", node=node, reason="x")
    with open_uow(loaded.db) as u:
        u.conn().execute(text("UPDATE job_queue SET state = 'done'"))
    state = "SELECT state FROM job_queue WHERE kind = 'awp.rollup'"
    assert loaded.scalar(state) == "done"
    loaded.call("sue", "ReinstateWbsNode", node=node, reason="x")
    assert loaded.scalar(state) == "queued"
