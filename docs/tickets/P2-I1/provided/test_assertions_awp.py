"""``sim_assert`` excuses the awp setup an operator makes by hand (P2-I1-T14)."""

from __future__ import annotations

from datetime import date
from typing import Any

from tl_sim.actors.base import Recorder
from tl_sim.assertions import AssertionReport, Expected, run_assertions
from tl_sim.testing import OPERATOR, REAL_TIME, FakeWorld, make_context


PLAYED = {date(2026, 11, 2)}
OPERATORS = frozenset({OPERATOR})


def awp_world() -> tuple[FakeWorld, Any]:
    """One intended record, then an operator defines an area and the path by hand."""
    world = FakeWorld("r1", "project:sim-r1")
    world.keys.counters.clear()
    rec = Recorder(make_context(world, "user:sim-crew"), "user:sim-crew")
    rec.create("Line 6-CS-1001")
    for ident, key, kind, event in (
        ("id-cwa", "CWA-1", "awp.CWA", "CWA.Defined"),
        ("id-path", "path", "awp.PathOfConstruction", "PathOfConstruction.Defined"),
    ):
        world.record_rows.append(world._row(ident, key, kind, key, None))
        world.emit("Record.Created", OPERATOR, "cli", REAL_TIME, ident)
        world.emit(event, OPERATOR, "cli", REAL_TIME, ident)
    return world, rec.truth


def check(world: FakeWorld, truth: Any, operators: frozenset[str]) -> AssertionReport:
    return run_assertions(
        truth, world, run_id="r1", played=PLAYED, expected=Expected(operators=operators)
    )


def failed(report: AssertionReport) -> set[str]:
    return {f.check for f in report.failures}


def test_operator_awp_setup_is_excused() -> None:
    world, truth = awp_world()
    report = check(world, truth, OPERATORS)
    assert report.ok, [f.line() for f in report.failures]
    assert report.excused >= 4  # two Record.Created, CWA.Defined, PathOfConstruction.Defined


def test_awp_setup_is_judged_when_the_actor_is_no_operator() -> None:
    world, truth = awp_world()
    assert {"unexpected_record", "event_actor"} <= failed(check(world, truth, frozenset()))


def test_operator_is_excused_only_for_awp_and_not_for_other_records() -> None:
    world, truth = awp_world()
    world.record_rows.append(world._row("id-x", "X-1", "doc.Document", "X", None))
    world.emit("Record.Created", OPERATOR, "cli", REAL_TIME, "id-x")
    assert {"unexpected_record", "event_actor"} <= failed(check(world, truth, OPERATORS))


def test_a_simulated_actor_event_on_an_awp_record_is_still_judged() -> None:
    world, truth = awp_world()
    world.emit("CWA.Defined", "user:sim-crew", "cli", REAL_TIME, "id-cwa")
    assert not check(world, truth, OPERATORS).ok
