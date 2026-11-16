"""``issue_guards``: the one function Issue, Resume and Revalidate share."""

from __future__ import annotations

import json
from datetime import timedelta

from permit_world import World
from tl_adapters.db import open_uow
from tl_mod_permits import guards
from tl_mod_permits.guards import issue_guards


def blockers(world: World, permit: str, ticks: list[str] | None = None) -> list[str]:
    row = world.row(permit)
    if ticks is not None:
        row = {**row, "precautions_json": json.dumps([{"id": t, "text": t} for t in ticks])}
    with open_uow(world.db, readonly=True) as uow:
        return issue_guards(uow.conn(), row, world.at)


HOT = ["fire_watch", "extinguisher", "combustibles_cleared", "spark_containment"]


def test_a_type_that_needs_nothing_is_clean_with_its_ticks(world: World) -> None:
    permit = world.approved("general")
    assert blockers(world, permit, ["jha_attached"]) == []
    assert blockers(world, permit, []) == ["precaution_unticked:jha_attached"]


def test_the_gas_blockers_are_missing_failed_and_stale(world: World) -> None:
    permit = world.approved("hot_work")
    assert blockers(world, permit, HOT) == ["gas_test_missing"]
    world.gas_test(permit, result="fail")
    assert blockers(world, permit, HOT) == ["gas_test_failed"]
    world.at += timedelta(minutes=5)
    world.gas_test(permit)
    assert blockers(world, permit, HOT) == []
    world.at += timedelta(minutes=240)
    assert blockers(world, permit, HOT) == []
    world.at += timedelta(minutes=1)
    assert blockers(world, permit, HOT) == ["gas_test_stale"]


def test_a_gas_test_of_another_permit_does_not_count(world: World) -> None:
    mine, other = world.approved("hot_work"), world.approved("hot_work")
    world.gas_test(other)
    assert blockers(world, mine, HOT) == ["gas_test_missing"]


def test_the_isolation_blockers_follow_the_linked_isolations(world: World) -> None:
    permit = world.approved("isolation")
    ticks = ["points_listed", "locks_tags_applied", "zero_energy_proven"]
    assert blockers(world, permit, ticks) == ["isolation_missing"]
    applied = world.isolation(permit)
    assert blockers(world, permit, ticks) == ["isolation_unverified"]
    world.verify_isolation(applied)
    assert blockers(world, permit, ticks) == []
    world.isolation(permit)
    assert blockers(world, permit, ticks) == ["isolation_unverified"]


def test_an_isolation_linked_to_another_permit_is_not_this_permits(world: World) -> None:
    mine, other = world.approved("isolation"), world.approved("isolation")
    world.isolation(other, verified=True)
    ticks = ["points_listed", "locks_tags_applied", "zero_energy_proven"]
    assert blockers(world, mine, ticks) == ["isolation_missing"]


def test_linked_isolations_read_the_permits_own_events_in_order(world: World) -> None:
    permit = world.approved("isolation")
    first, second = world.isolation(permit), world.isolation(permit)
    world.link(permit, first, unlink=True)
    with open_uow(world.db, readonly=True) as uow:
        assert guards.linked_isolations(uow.conn(), permit) == [second]


def test_the_blockers_come_in_the_rules_order(world: World) -> None:
    permit = world.approved("confined_space")
    assert blockers(world, permit, ["ventilation"]) == [
        "gas_test_missing",
        "isolation_missing",
        "precaution_unticked:attendant",
        "precaution_unticked:rescue_plan",
        "precaution_unticked:entry_log",
    ]


def test_a_gas_test_dated_after_now_is_not_evidence(world: World) -> None:
    permit = world.approved("hot_work")
    world.gas_test(permit, at=world.at + timedelta(hours=1))
    assert blockers(world, permit, HOT) == ["gas_test_missing"]


def test_a_link_to_a_record_that_is_not_an_isolation_counts_for_nothing(world: World) -> None:
    permit = world.approved("isolation")
    ticks = ["points_listed", "locks_tags_applied", "zero_energy_proven"]
    world.link(permit, world.record("awp.IWP", "IWP-1"))
    world.link(permit, "01JXXXXXXXXXXXXXXXXXXXXXXX")
    assert blockers(world, permit, ticks) == ["isolation_missing"]
    world.isolation(permit)  # applied, never verified: not Verified
    assert blockers(world, permit, ticks) == ["isolation_unverified"]
