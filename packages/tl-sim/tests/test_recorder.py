"""The Recorder writes through the client and writes the ground truth in the same breath."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from tl_sim import groundtruth as gt
from tl_sim.actors.base import BaseActor, Rec, Recorder
from tl_sim.testing import FakeWorld, make_context, seed_lines

IDENTITY = "user:sim-crew"


def recorder(world: FakeWorld, **kw: object) -> Recorder:
    return Recorder(make_context(world, IDENTITY, **kw), IDENTITY)  # type: ignore[arg-type]


def test_create_records_the_key_and_the_expectations() -> None:
    world = FakeWorld("r1", "project:sim-r1")
    rec = recorder(world)
    made = rec.create("Valve V001")
    assert made.key == "SIMR1-REC-0001" and made.title == "Valve V001"
    (item,) = rec.truth
    assert (item.intent, item.ref, item.actor) == (gt.RECORD_CREATED, made.key, IDENTITY)
    assert item.expect == {"title": "Valve V001", "record_type": "core.Record", "voided": False}
    assert item.at == datetime(2026, 11, 2, 7, 0, tzinfo=UTC)


def test_psets_links_and_posts_each_add_their_own_line() -> None:
    world = FakeWorld("r1", "project:sim-r1")
    a, b = seed_lines(world, 2)
    rec = recorder(world)
    rec.set_psets(a, {"valve_data": {"size_in": 6, "manufacturer": "Crane"}})
    rec.link(a, b, "belongs_to")
    ref = rec.post("Done #" + a.key)
    assert [(t.intent, t.ref) for t in rec.truth] == [
        (gt.PSET_SET, a.key),
        (gt.PSET_SET, a.key),
        (gt.LINK_ADDED, f"{a.key} belongs_to {b.key}"),
        (gt.POST_CREATED, ref),
    ]
    assert rec.truth[0].expect == {"psets.valve_data.manufacturer": "Crane"}  # property order
    assert rec.truth[3].expect == {"body": "Done #" + a.key, "author": IDENTITY}


def test_a_refused_transition_returns_false_and_writes_no_truth() -> None:
    world = FakeWorld("r1", "project:sim-r1")
    (line,) = seed_lines(world, 1)
    rec = recorder(world)
    assert rec.transition(line, "approve", "Approved") is False  # a draft cannot be approved
    assert rec.transition(line, "nonsense", "x") is False
    assert rec.truth == []
    assert rec.transition(line, "submit", "Review") is True
    assert rec.truth[0].expect == {"status": "Review", "transition": "submit"}


def test_an_error_that_is_not_a_refusal_propagates_and_writes_no_truth() -> None:
    world = FakeWorld("r1", "project:sim-r1")
    rec = recorder(world)
    ghost = Rec(id="id-none", key="K", title="Ghost")
    with pytest.raises(LookupError):
        rec.set_psets(ghost, {"valve_data": {"size_in": 1}})
    assert rec.truth == []


def test_post_names_are_unique_within_a_step_and_across_slots() -> None:
    world = FakeWorld("r1", "project:sim-r1")
    first = recorder(world)
    names = {first.post("a"), first.post("a")}
    assert len(names) == 2
    later = recorder(world, now=datetime(2026, 11, 2, 7, 30, tzinfo=UTC))
    assert later.post("a") not in names


def test_records_are_read_in_key_order_without_voided_ones() -> None:
    world = FakeWorld("r1", "project:sim-r1")
    seed_lines(world, 3)
    world.record_rows[1]["voided"] = True
    rec = recorder(world)
    assert [r.title for r in rec.records()] == ["Line 6-CS-1001", "Line 6-CS-1003"]
    assert [r.title for r in rec.records(title_prefix="Valve ")] == []


def test_an_empty_status_is_the_initial_state() -> None:
    assert Rec("i", "k", "t").state == "Draft"
    assert Rec("i", "k", "t", "Review").state == "Review"


def test_a_base_actor_derives_its_identity_from_its_name() -> None:
    class Noisy(BaseActor):
        name = "planner"

    assert Noisy(None).identity == "user:sim-planner"


def test_only_a_duplicate_link_refusal_is_shrugged_off_any_other_is_raised(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from tl_sim.mcp_caller import ProposalRefusedError
    from tl_sim.testing import FakeClient

    world = FakeWorld("r1", "project:sim-r1")
    rec = Recorder(make_context(world, "agent:sim-assistant", propose=True), "agent:sim-assistant")

    def refuse(text: str):
        def propose(self: FakeClient, tool: str, arguments: dict[str, object]) -> dict[str, object]:
            raise ProposalRefusedError(text)

        return propose

    monkeypatch.setattr(
        FakeClient, "propose", refuse("a references link already exists between these records")
    )
    assert rec.propose("link_records", {}) is None and rec.truth == []
    for budget in ("agent:sim-assistant has used its 500 proposals today", "no record 'K'"):
        monkeypatch.setattr(FakeClient, "propose", refuse(budget))
        with pytest.raises(ProposalRefusedError):
            rec.propose("link_records", {})
    assert rec.truth == []
