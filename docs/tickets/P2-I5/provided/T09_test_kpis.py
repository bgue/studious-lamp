"""P2-I5-T09: the PPC and constraint-free tiles, each checked against a ledger recount."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from decimal import Decimal

import pytest
from awp_world import SCOPE, World
from progress_world import WeekWorld, build_week_world
from sqlalchemy import text
from tl_adapters.db import open_uow
from tl_core import confidentiality as cf
from tl_core import modules as core_modules
from tl_core.modules import ConfidentialSource
from tl_core.services.commands import Command
from tl_mod_awp.common import move
from tl_mod_awp.kpis import KPI_NAMES, KpiTile, constraint_free_tile, kpi_rows, ppc_tile
from tl_mod_awp.names import IWP

LOWEST = cf.Viewer(actor="user:nobody", level=0, account="user:nobody")
#: The workflow moves from Draft to each state (schema/fixtures/workflows/awp-iwp.yaml). The first
#: two are awp commands; the rest are the module's own transitions (``common.move``, the call the
#: readiness engine makes for ``ready``), since IssueIwp needs two sign-offs and no command closes.
STEPS: dict[str, tuple[str, ...]] = {
    "Draft": (),
    "In development": ("develop",),
    "Constraint check": ("develop", "check_constraints"),
    "Ready": ("develop", "check_constraints", "ready"),
    "Issued": ("develop", "check_constraints", "ready", "issue"),
    "Closed": ("develop", "check_constraints", "ready", "issue", "start", "complete", "close"),
}


def move_iwp(w: World, iwp: str, step: str) -> None:
    if step == "develop":
        w.call("uma", "StartIwpDevelopment", iwp=iwp)
    elif step == "check_constraints":
        w.call("uma", "SendIwpToConstraintCheck", iwp=iwp)
    else:
        with open_uow(w.db) as uow:
            move(uow, Command(actor="user:uma", source="test", scope=SCOPE), iwp, step)


@contextmanager
def hidden_iwp(ww: WeekWorld, iwp: str) -> Iterator[None]:
    """The IWP is restricted: the lowest viewer cannot open it (a test source, as the look-ahead
    test does), so its commitments are left out of the plan."""
    ids = [str(r["id"]) for r in ww.w.rows("SELECT id FROM cur_awp_iwp")]
    with open_uow(ww.w.db) as uow:
        conn = uow.conn()
        conn.execute(
            text("CREATE TABLE IF NOT EXISTS kpi_iwp_class (id TEXT PRIMARY KEY, cls TEXT)")
        )
        conn.execute(text("DELETE FROM kpi_iwp_class"))
        for row_id in ids:
            cls = "restricted" if row_id == iwp else "internal"
            conn.execute(text("INSERT INTO kpi_iwp_class VALUES (:i, :c)"), {"i": row_id, "c": cls})
    source = ConfidentialSource(
        record_types=frozenset({IWP}),
        table="kpi_iwp_class",
        id_column="id",
        class_column="cls",
    )
    real = core_modules.confidential_sources
    cf.confidential_sources = lambda: [*real(), source]  # type: ignore[attr-defined]
    try:
        yield
    finally:
        cf.confidential_sources = real  # type: ignore[attr-defined]


class KpiWeekWorld(WeekWorld):
    """The week world whose IWPs reach their state along the real workflow, not by a write."""

    def issued(self, state: str = "Issued", foreman: str | None = "user:uma") -> str:
        iwp = self.w.iwp(planned_start="2026-12-01", foreman=foreman) if foreman else self.w.iwp()
        for step in STEPS[state]:
            move_iwp(self.w, iwp, step)
        return iwp


@pytest.fixture
def ww(world: World) -> WeekWorld:
    return KpiWeekWorld(build_week_world(world).pw)


def tile(ww: WeekWorld, name: str, viewer: cf.Viewer = LOWEST, **more: int) -> KpiTile:
    with open_uow(ww.w.db, readonly=True) as uow:
        conn = uow.conn()
        if name == "ppc":
            return ppc_tile(conn, SCOPE, viewer, **more)
        return constraint_free_tile(conn, SCOPE, viewer)


def closed_week(ww: WeekWorld, day: str, results: list[str]) -> str:
    """A closed plan for the week of ``day``: one Issued IWP per result, 'done' or 'missed'."""
    plan = ww.open(day)
    for n, result in enumerate(results):
        iwp = ww.issued()
        ww.commit(plan, iwp, hours=f"{10 + n}.0")
        ww.outcome(plan, iwp, result, None if result == "done" else "Weather")
    ww.close(plan)
    return plan


def recount(ww: WeekWorld, last: int) -> tuple[int, int]:
    """done and committed over the last ``last`` closed plans, straight from the tables."""
    plans = [
        r["id"]
        for r in ww.w.rows(
            "SELECT p.id FROM cur_awp_weekly_plan p JOIN cur_core_record r ON r.id = p.id "
            "WHERE r.status = 'Closed' ORDER BY p.week DESC LIMIT :n",
            n=last,
        )
    ]
    done = committed = 0
    for plan in plans:
        for c in ww.commitments(plan):
            committed += 1
            done += 1 if c["outcome"] == "done" else 0
    return done, committed


def test_ppc_is_pooled_over_closed_weeks_by_count(ww: WeekWorld) -> None:
    closed_week(ww, "2026-10-26", ["done", "done", "missed"])  # 2 of 3
    closed_week(ww, "2026-11-02", ["done", "done"])  # 2 of 2
    t = tile(ww, "ppc")
    assert (t.name, t.value, t.numerator, t.denominator) == ("kpi_ppc", Decimal("80.0"), 4, 5)
    assert recount(ww, 4) == (t.numerator, t.denominator)  # pooled 80.0, not the mean 83.4


def test_ppc_takes_only_the_last_weeks_asked_for(ww: WeekWorld) -> None:
    closed_week(ww, "2026-10-19", ["missed", "missed"])
    closed_week(ww, "2026-10-26", ["done", "done", "missed"])
    closed_week(ww, "2026-11-02", ["done"])
    last_two = tile(ww, "ppc", weeks=2)
    assert (last_two.numerator, last_two.denominator) == recount(ww, 2) == (3, 4)
    assert last_two.value == Decimal("75.0")
    assert tile(ww, "ppc", weeks=3).value == Decimal("50.0")  # 3 of 6


def test_open_and_draft_plans_do_not_count_and_nothing_closed_is_none(ww: WeekWorld) -> None:
    plan = ww.open("2026-11-09")
    ww.commit(plan, ww.issued())
    empty = tile(ww, "ppc")
    assert empty.value is None
    assert (empty.numerator, empty.denominator) == (0, 0)
    assert "closed" in empty.detail.lower()
    # CloseWeek refuses a plan with nothing committed, so a closed week that holds nothing the
    # viewer may read is one whose only commitment is of a hidden IWP.
    closed = ww.open("2026-10-26")
    held = ww.issued()
    ww.commit(closed, held)
    ww.outcome(closed, held, "missed", "Weather")
    ww.close(closed)
    with hidden_iwp(ww, held):
        nothing = tile(ww, "ppc")
    assert (nothing.value, nothing.detail) == (None, "nothing committed in closed weeks")


def test_a_hidden_plan_is_left_out_of_the_pool(ww: WeekWorld) -> None:
    plan = ww.open("2026-11-02")
    shown, hidden = ww.issued(), ww.issued()
    for iwp, result in ((shown, "done"), (hidden, "missed")):
        ww.commit(plan, iwp)
        ww.outcome(plan, iwp, result, None if result == "done" else "Weather")
    ww.close(plan)
    both = tile(ww, "ppc")
    assert (both.numerator, both.denominator) == (1, 2)
    with ww.hidden_plan(plan):
        gone = tile(ww, "ppc")
    assert gone.value is None
    assert ww.w.scalar("SELECT COUNT(*) FROM cur_awp_week_commitment") == 2  # still in the ledger


def live_states(ww: WeekWorld, free: int, blocked: int) -> list[str]:
    ids = [ww.issued() for _ in range(free + blocked)]
    for iwp in ids[free:]:
        ww.pw.raise_blocking(iwp, "start")
    return ids


def test_constraint_free_counts_live_iwps_without_an_open_blocking_constraint(
    ww: WeekWorld,
) -> None:
    live_states(ww, free=3, blocked=1)
    done = ww.issued(state="Closed")  # not live: left out of both numbers
    assert done
    t = tile(ww, "free")
    assert (t.name, t.value, t.numerator, t.denominator) == (
        "kpi_constraint_free",
        Decimal("75.0"),
        3,
        4,
    )
    live = ww.w.rows(
        "SELECT COUNT(*) AS n FROM cur_core_record WHERE type = 'awp.IWP' AND status = 'Issued'"
    )[0]["n"]
    blocked = ww.w.rows(
        "SELECT COUNT(DISTINCT c.subject_id) AS n FROM cur_core_constraint c "
        "JOIN cur_core_record r ON r.id = c.id WHERE c.severity = 'blocking' "
        "AND COALESCE(r.status, 'Open') IN ('Open', 'Assigned')"
    )[0]["n"]
    assert (t.denominator, t.denominator - t.numerator) == (live, blocked)


def test_a_cleared_constraint_frees_the_iwp_and_no_live_iwp_is_none(ww: WeekWorld) -> None:
    assert tile(ww, "free").value is None
    [iwp] = live_states(ww, free=0, blocked=1)
    assert tile(ww, "free").value == Decimal("0.0")
    [constraint] = ww.w.rows("SELECT id FROM cur_core_constraint WHERE subject_id = :i", i=iwp)
    ww.w.set_status(str(constraint["id"]), "Cleared")  # a projection write, as the S2 checks do
    assert tile(ww, "free").value == Decimal("100.0")


def test_kpi_rows_are_both_tiles_in_name_order_and_equal_the_single_calls(ww: WeekWorld) -> None:
    closed_week(ww, "2026-11-02", ["done", "missed"])
    live_states(ww, free=1, blocked=1)
    with open_uow(ww.w.db, readonly=True) as uow:
        rows = kpi_rows(uow.conn(), SCOPE, LOWEST)
    assert [r.name for r in rows] == list(KPI_NAMES)
    assert rows == [tile(ww, "ppc"), tile(ww, "free")]
