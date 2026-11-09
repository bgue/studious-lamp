"""P2-I5-S4b: the hold rule (D9). A blocking constraint raised on an Issued IWP puts it On hold.

The rule is a follower of the outbox: Issued only, the state and the constraint re-read when the
event is applied, idempotent on replay, never inside the raise. No new event type and no new
payload key: the move is the existing ``IWP.Held`` and the ``hold`` transition.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from awp_world import SCOPE, World
from progress_world import ProgressWorld
from tl_adapters.db import make_uow_factory, rebuild_projections
from tl_core.constraints.commands import ClearConstraint
from tl_core.constraints.handlers import handle_clear_constraint
from tl_core.constraints.handlers import handle_raise_constraint
from tl_core.constraints.commands import RaiseConstraint
from tl_mod_awp.readiness import hold_rule
from tl_mod_awp.readiness.hold_rule import HoldFollower
from tl_adapters.db import open_uow


@pytest.fixture
def pw(world: World) -> ProgressWorld:
    return ProgressWorld(world)


@pytest.fixture
def follower(pw: ProgressWorld) -> HoldFollower:
    f = HoldFollower(make_uow_factory(pw.w.db))
    assert f.poll() == 0  # a new follower starts at the head of the outbox
    return f


def issued(pw: ProgressWorld) -> str:
    iwp = pw.w.iwp(planned_start="2026-12-01", foreman="user:uma")
    pw.w.set_status(iwp, "Issued")
    return iwp


def count(w: World, sql: str, **p: object) -> int:
    return int(w.scalar(sql, **p))


def events(w: World) -> int:
    return count(w, "SELECT COUNT(*) FROM events")


def constraint_of(w: World, iwp: str) -> str:
    return str(w.rows("SELECT id FROM cur_core_constraint WHERE subject_id = :i", i=iwp)[0]["id"])


def raise_severity(pw: ProgressWorld, iwp: str, severity: str) -> None:
    cmd = RaiseConstraint(
        actor="user:sue",
        source="test",
        scope=SCOPE,
        subject=iwp,
        phase="complete",
        severity=severity,
        category="other",
        owner="user:uma",
    )
    with open_uow(pw.w.db) as uow:
        handle_raise_constraint(uow, cmd)


def test_a_blocking_constraint_holds_an_issued_iwp(pw: ProgressWorld, follower: HoldFollower) -> None:
    w = pw.w
    iwp = issued(pw)
    pw.raise_blocking(iwp, "complete")
    assert w.state(iwp) == "Issued"  # the raise itself holds nothing
    assert follower.poll() == 1
    assert w.state(iwp) == "On hold"
    key = w.rows("SELECT key FROM cur_core_record WHERE id = :i", i=constraint_of(w, iwp))[0]["key"]
    held = w.rows(
        "SELECT actor, source, payload FROM events WHERE stream_id = :i AND event_type = 'IWP.Held'",
        i=iwp,
    )
    assert len(held) == 1
    assert held[0]["actor"] == "svc:awp.hold" and held[0]["source"] == "job:awp.hold"
    assert f"blocking constraint raised: {key}" in str(held[0]["payload"])


def test_a_second_poll_and_a_replay_change_nothing(pw: ProgressWorld, follower: HoldFollower) -> None:
    w = pw.w
    iwp = issued(pw)
    pw.raise_blocking(iwp, "complete")
    assert follower.poll() == 1
    before = events(w)
    assert follower.poll() == 0
    with open_uow(w.db) as uow:  # replay: the cursor goes back to the start of the ledger
        from sqlalchemy import text

        uow.conn().execute(text("UPDATE rule_cursor SET last_seq = 0 WHERE name = 'awp.hold'"))
    again = HoldFollower(make_uow_factory(w.db))
    assert again.poll() == 0
    assert events(w) == before
    assert count(w, "SELECT COUNT(*) FROM events WHERE event_type = 'IWP.Held'") == 1
    assert w.state(iwp) == "On hold"


@pytest.mark.parametrize("state", ["Ready", "In progress", "On hold"])
def test_other_states_are_untouched(pw: ProgressWorld, follower: HoldFollower, state: str) -> None:
    w = pw.w
    iwp = issued(pw)
    w.set_status(iwp, state)
    pw.raise_blocking(iwp, "complete")
    before = events(w)
    assert follower.poll() == 0
    assert w.state(iwp) == state
    assert events(w) == before + 0


def test_a_constraint_cleared_before_the_poll_holds_nothing(
    pw: ProgressWorld, follower: HoldFollower
) -> None:
    w = pw.w
    iwp = issued(pw)
    pw.raise_blocking(iwp, "complete")
    clear = ClearConstraint(
        actor="user:sue", source="test", scope=SCOPE, constraint=constraint_of(w, iwp), reason="r"
    )
    with open_uow(w.db) as uow:
        handle_clear_constraint(uow, clear)
    assert follower.poll() == 0
    assert w.state(iwp) == "Issued"


def test_a_non_blocking_severity_holds_nothing(pw: ProgressWorld, follower: HoldFollower) -> None:
    iwp = issued(pw)
    raise_severity(pw, iwp, "advisory")
    assert follower.poll() == 0
    assert pw.w.state(iwp) == "Issued"


def test_the_hold_raises_nothing_and_does_not_loop(pw: ProgressWorld, follower: HoldFollower) -> None:
    w = pw.w
    iwp = issued(pw)
    pw.raise_blocking(iwp, "complete")
    constraints = count(w, "SELECT COUNT(*) FROM cur_core_constraint")
    follower.poll()
    settled = events(w)
    for _ in range(3):
        assert follower.poll() == 0
    assert events(w) == settled
    assert count(w, "SELECT COUNT(*) FROM cur_core_constraint") == constraints


def test_rebuild_equality_after_a_hold(pw: ProgressWorld, follower: HoldFollower) -> None:
    w = pw.w
    iwp = issued(pw)
    pw.raise_blocking(iwp, "complete")
    follower.poll()
    tables = ("cur_awp_iwp", "cur_core_record")
    before = [w.rows(f"SELECT * FROM {t} ORDER BY 1") for t in tables]
    rebuild_projections(w.db)
    assert before == [w.rows(f"SELECT * FROM {t} ORDER BY 1") for t in tables]


def test_the_rule_never_raises_a_constraint_and_copies_no_predicate() -> None:
    source = Path(hold_rule.__file__).read_text()
    assert "raise_by_module" not in source and "raise_constraint" not in source
    assert "open_blocking" in source  # the guard's own predicate
    assert "'blocking'" not in source and '"blocking"' not in source
