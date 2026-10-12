"""The tag clerk on an in-memory world (``tl_sim.testing``) (P1-I1-T12)."""

from __future__ import annotations

import re
from typing import Any

import pytest
from tl_sim import groundtruth as gt
from tl_sim.actors.tag_clerk import AREAS, KINDS, TagClerk, next_number
from tl_sim.scenario import CountRange, TagClerkParams
from tl_sim.testing import FakeWorld, make_context
from tl_sim.types import GroundTruth

IDENTITY = "user:sim-tag_clerk"
NUMBER = re.compile(r"^(\d{2})-([A-Z]+)-(\d{4})$")
CLASSES = {mnemonic: (class_code, noun) for mnemonic, class_code, noun in KINDS}


def step(world: FakeWorld, *, seed: int = 1, day: int = 0, **params: Any) -> list[GroundTruth]:
    actor = TagClerk(TagClerkParams(**params))
    return actor.step(make_context(world, actor.identity, seed=seed, day=day))


def world_with(*numbers: str) -> FakeWorld:
    """A world that already holds tags, made by another hand (the orchestrator)."""
    world = FakeWorld("r1", "project:sim-r1")
    client = world.client("user:sim-orchestrator", make_context(world, "x").client.clock)  # type: ignore[attr-defined]
    for number in numbers:
        client.create_tag(number, "ControlValve", f"Seeded {number}")
    return world


def tags(world: FakeWorld) -> list[dict[str, Any]]:
    return sorted(
        (r for r in world.records() if r["type"] == "engineering.Tag"), key=lambda r: r["key"]
    )


def test_identity_and_name_follow_the_contract() -> None:
    actor = TagClerk(TagClerkParams())
    assert (actor.name, actor.identity) == ("tag_clerk", IDENTITY)


def test_next_number_is_one_more_than_the_largest_for_that_area_and_mnemonic() -> None:
    known = ["47-FV-0007", "47-FV-0003", "47-HV-0020", "10-FV-0099", "47-FV-old", "47-FV-"]
    assert next_number(known, "47", "FV") == "47-FV-0008"
    assert next_number(known, "47", "HV") == "47-HV-0021"
    assert next_number(known, "47", "PT") == "47-PT-0001"
    assert next_number([], "10", "P") == "10-P-0001"


def test_each_new_tag_has_a_number_a_class_and_a_service_the_registry_would_accept() -> None:
    world = FakeWorld("r1", "project:sim-r1")
    truth = step(world, tags_per_day=3, rename_rate=0.0)
    made = tags(world)
    assert len(made) == 3
    for tag in made:
        area, mnemonic, seq = NUMBER.fullmatch(tag["key"]).groups()  # type: ignore[union-attr]
        assert area in AREAS and mnemonic in CLASSES and int(seq) >= 1
        assert tag["title"] == f"{CLASSES[mnemonic][1]} {tag['key']}"
    assert [t.intent for t in truth] == [gt.RECORD_CREATED] * 3
    assert all(t.actor == IDENTITY for t in truth)
    assert {t.ref for t in truth} == {tag["key"] for tag in made}
    assert all(
        t.expect["record_type"] == "engineering.Tag" and t.expect["voided"] is False for t in truth
    )


def test_sequences_continue_across_days() -> None:
    world = FakeWorld("r1", "project:sim-r1")
    for day in range(6):
        step(world, day=day, tags_per_day=2, rename_rate=0.0)
    seen: dict[str, list[int]] = {}
    for tag in tags(world):
        area, mnemonic, seq = NUMBER.fullmatch(tag["key"]).groups()  # type: ignore[union-attr]
        seen.setdefault(f"{area}-{mnemonic}", []).append(int(seq))
    assert len(tags(world)) == 12
    for sequence in seen.values():
        assert sorted(sequence) == list(range(1, len(sequence) + 1))  # no gaps, no repeats


def test_a_rename_replaces_one_tag_in_service_with_the_next_number_of_its_group() -> None:
    world = world_with("47-FV-0001", "47-FV-0002", "10-PT-0005")
    truth = step(world, tags_per_day=0, rename_rate=1.0)
    by_key = {t["key"]: t for t in tags(world)}
    assert len(by_key) == 4
    old = [k for k, t in by_key.items() if t["status"] == "Superseded"]
    assert len(old) == 1
    new = (set(by_key) - {"47-FV-0001", "47-FV-0002", "10-PT-0005"}).pop()
    area, mnemonic = old[0].split("-")[:2]
    taken = [
        k for k in ("47-FV-0001", "47-FV-0002", "10-PT-0005") if k.startswith(f"{area}-{mnemonic}-")
    ]
    assert new == f"{area}-{mnemonic}-{max(int(k[-4:]) for k in taken) + 1:04d}"
    assert by_key[new]["title"] == by_key[old[0]]["title"]
    assert [t.intent for t in truth] == [gt.RECORD_CREATED, gt.LINK_ADDED, gt.WORKFLOW_TRANSITIONED]
    created, linked, moved = truth
    assert created.ref == new
    assert linked.ref == f"{new} supersedes {old[0]}"
    assert linked.expect == {"from": new, "to": old[0], "relation": "supersedes"}
    assert (moved.ref, moved.expect["status"]) == (old[0], "Superseded")
    assert world.links(by_key[new]["id"])[0]["relation"] == "supersedes"


def test_a_tag_that_was_replaced_is_never_renamed_again() -> None:
    world = world_with("47-FV-0001")
    step(world, tags_per_day=0, rename_rate=1.0, day=0)
    step(world, tags_per_day=0, rename_rate=1.0, day=1)
    step(world, tags_per_day=0, rename_rate=1.0, day=2)
    states = [t["status"] for t in tags(world)]
    assert states.count("Superseded") == 3 and states.count(None) == 1  # a chain, one in service


def test_with_nothing_to_rename_or_a_rate_of_zero_only_new_tags_appear() -> None:
    empty = FakeWorld("r1", "project:sim-r1")
    assert step(empty, tags_per_day=0, rename_rate=1.0) == []
    world = world_with("47-FV-0001")
    truth = step(world, tags_per_day=1, rename_rate=0.0)
    assert [t.intent for t in truth] == [gt.RECORD_CREATED]
    assert [t["status"] for t in tags(world)] == [None, None]


def test_the_same_seed_gives_the_same_day() -> None:
    first = FakeWorld("r1", "project:sim-r1")
    second = FakeWorld("r1", "project:sim-r1")
    params: dict[str, Any] = {"tags_per_day": CountRange(min=1, max=4), "rename_rate": 0.5}
    a = step(first, seed=7, **params)
    b = step(second, seed=7, **params)
    assert [(t.intent, t.ref) for t in a] == [(t.intent, t.ref) for t in b]
    other = step(FakeWorld("r1", "project:sim-r1"), seed=8, **params)
    assert [t.ref for t in other] != [t.ref for t in a] or len(other) != len(a)


@pytest.mark.parametrize("rate", [-0.1, 1.5])
def test_the_rename_rate_is_a_probability(rate: float) -> None:
    with pytest.raises(ValueError, match="rename_rate"):
        TagClerkParams(rename_rate=rate)
