"""The document registrar on an in-memory world (``tl_sim.testing``) (P1-I2-T12a)."""

from __future__ import annotations

import re
from typing import Any

import pytest
from tl_sim import groundtruth as gt
from tl_sim.actors.document_registrar import KINDS, DocumentRegistrar, next_number
from tl_sim.scenario import CountRange, DocumentRegistrarParams
from tl_sim.testing import FakeWorld, make_context
from tl_sim.types import GroundTruth

IDENTITY = "user:sim-document_registrar"
NUMBER = re.compile(r"^([A-Z]+)-(\d{4})$")
NOUNS = {code: (discipline, noun) for code, discipline, noun in KINDS}


def step(world: FakeWorld, *, seed: int = 1, day: int = 0, **params: Any) -> list[GroundTruth]:
    actor = DocumentRegistrar(DocumentRegistrarParams(**params))
    return actor.step(make_context(world, actor.identity, seed=seed, day=day))


def seeded(
    world: FakeWorld, *, documents: tuple[str, ...] = (), tags: tuple[str, ...] = ()
) -> None:
    """Documents and tags made by another hand (the orchestrator)."""
    client = world.client("user:sim-orchestrator", make_context(world, "x").client.clock)  # type: ignore[attr-defined]
    for number in documents:
        client.register_document(number, f"Seeded {number}", number.split("-")[0], "PIP")
    for number in tags:
        client.create_tag(number, "ControlValve", f"Seeded {number}")


def of_type(world: FakeWorld, record_type: str) -> list[dict[str, Any]]:
    return sorted((r for r in world.records() if r["type"] == record_type), key=lambda r: r["key"])


def test_identity_and_name_follow_the_contract() -> None:
    actor = DocumentRegistrar(DocumentRegistrarParams())
    assert (actor.name, actor.identity) == ("document_registrar", IDENTITY)


def test_next_number_is_one_more_than_the_largest_for_that_type() -> None:
    known = ["ISO-0007", "ISO-0003", "PID-0020", "ISO-old", "ISO-"]
    assert next_number(known, "ISO") == "ISO-0008"
    assert next_number(known, "PID") == "PID-0021"
    assert next_number(known, "DS") == "DS-0001"
    assert next_number([], "LD") == "LD-0001"


def test_each_new_document_has_a_number_and_a_title_the_registry_would_accept() -> None:
    world = FakeWorld("r1", "project:sim-r1")
    truth = step(world, documents_per_day=3, revision_rate=0.0, link_rate=0.0)
    made = of_type(world, "documents.Document")
    assert len(made) == 3
    for doc in made:
        code, seq = NUMBER.fullmatch(doc["key"]).groups()  # type: ignore[union-attr]
        assert code in NOUNS and int(seq) >= 1
        assert doc["title"] == f"{NOUNS[code][1]} {doc['key']}" and doc["status"] == "Registered"
    assert [t.intent for t in truth] == [gt.RECORD_CREATED] * 3
    assert all(t.actor == IDENTITY for t in truth)
    assert {t.ref for t in truth} == {doc["key"] for doc in made}
    assert all(
        t.expect["record_type"] == "documents.Document" and t.expect["voided"] is False
        for t in truth
    )


def test_sequences_continue_across_days() -> None:
    world = FakeWorld("r1", "project:sim-r1")
    for day in range(6):
        step(world, day=day, documents_per_day=2, revision_rate=0.0, link_rate=0.0)
    seen: dict[str, list[int]] = {}
    for doc in of_type(world, "documents.Document"):
        code, seq = NUMBER.fullmatch(doc["key"]).groups()  # type: ignore[union-attr]
        seen.setdefault(code, []).append(int(seq))
    assert len(of_type(world, "documents.Document")) == 12
    for sequence in seen.values():
        assert sorted(sequence) == list(range(1, len(sequence) + 1))


def test_a_revision_starts_the_first_draft_of_one_document_without_a_revision() -> None:
    world = FakeWorld("r1", "project:sim-r1")
    seeded(world, documents=("ISO-0001", "PID-0002"))
    truth = step(world, documents_per_day=0, revision_rate=1.0, link_rate=0.0)
    revisions = of_type(world, "documents.Revision")
    assert len(revisions) == 1
    rev = revisions[0]
    assert rev["key"] in ("ISO-0001@A", "PID-0002@A") and rev["status"] == "Draft"
    assert rev["title"] == f"{rev['key'].split('@')[0]} rev A"
    assert [t.intent for t in truth] == [gt.RECORD_CREATED]
    assert truth[0].expect["record_type"] == "documents.Revision"
    assert truth[0].ref == rev["key"] and truth[0].expect["title"] == rev["title"]


def test_a_document_with_a_revision_is_not_given_another() -> None:
    world = FakeWorld("r1", "project:sim-r1")
    seeded(world, documents=("ISO-0001",))
    step(world, documents_per_day=0, revision_rate=1.0, link_rate=0.0, day=0)
    truth = step(world, documents_per_day=0, revision_rate=1.0, link_rate=0.0, day=1)
    assert truth == [] and len(of_type(world, "documents.Revision")) == 1


def test_a_new_document_can_get_its_first_revision_the_same_day() -> None:
    world = FakeWorld("r1", "project:sim-r1")
    truth = step(world, documents_per_day=1, revision_rate=1.0, link_rate=0.0)
    assert [t.expect["record_type"] for t in truth] == ["documents.Document", "documents.Revision"]


def test_a_tag_is_linked_to_a_document_created_today() -> None:
    world = FakeWorld("r1", "project:sim-r1")
    seeded(world, documents=("ISO-0001",), tags=("47-FV-0001",))
    truth = step(world, documents_per_day=1, revision_rate=0.0, link_rate=1.0)
    assert [t.intent for t in truth] == [gt.RECORD_CREATED, gt.LINK_ADDED]
    created, linked = truth
    assert linked.ref == f"47-FV-0001 references {created.ref}"
    assert linked.expect == {"from": "47-FV-0001", "to": created.ref, "relation": "references"}
    tag = next(r for r in world.records() if r["key"] == "47-FV-0001")
    assert [link["relation"] for link in world.links(tag["id"])] == ["references"]


def test_without_a_new_document_or_a_tag_nothing_is_linked() -> None:
    world = FakeWorld("r1", "project:sim-r1")
    assert [
        t.intent for t in step(world, documents_per_day=1, revision_rate=0.0, link_rate=1.0)
    ] == [gt.RECORD_CREATED]
    seeded(world, tags=("47-FV-0001",))
    assert step(world, documents_per_day=0, revision_rate=0.0, link_rate=1.0, day=1) == []


def test_the_same_seed_gives_the_same_day() -> None:
    first, second = FakeWorld("r1", "project:sim-r1"), FakeWorld("r1", "project:sim-r1")
    params: dict[str, Any] = {
        "documents_per_day": CountRange(min=1, max=4),
        "revision_rate": 0.5,
        "link_rate": 0.5,
    }
    a = step(first, seed=7, **params)
    b = step(second, seed=7, **params)
    assert [(t.intent, t.ref) for t in a] == [(t.intent, t.ref) for t in b]
    other = step(FakeWorld("r1", "project:sim-r1"), seed=8, **params)
    assert [t.ref for t in other] != [t.ref for t in a] or len(other) != len(a)


@pytest.mark.parametrize("name", ["revision_rate", "link_rate"])
@pytest.mark.parametrize("rate", [-0.1, 1.5])
def test_the_rates_are_probabilities(name: str, rate: float) -> None:
    with pytest.raises(ValueError, match=name):
        DocumentRegistrarParams.model_validate({name: rate})
