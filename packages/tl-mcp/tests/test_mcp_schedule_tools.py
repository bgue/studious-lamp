"""The schedule tool: an agent proposes publishing a snapshot; a controller accepts (P1-I4)."""

from __future__ import annotations

import asyncio
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from mcp.server.mcpserver.exceptions import ToolError
from mcp_harness import ACTOR, McpHarness
from tl_core.services import proposals
from tl_core.services.errors import ProposalAccessError
from tl_mod_schedule.testing import ScheduleWorld


def CONTROLLER(level: str) -> bool:  # noqa: N802 - a document controller holds these
    return level in ("user", "controller")


class Env:
    def __init__(self, harness: McpHarness, world: ScheduleWorld, one: str, two: str) -> None:
        self.h, self.world, self.one, self.two = harness, world, one, two

    def events(self, event_type: str) -> list[Any]:
        with self.h.factory(True) as uow:
            return [e for e in uow.ledger.read_after(0, limit=5000) if e.event_type == event_type]


@pytest.fixture
def env(tmp_path: Path) -> Iterator[Env]:
    harness = McpHarness.build(tmp_path)
    try:
        world = ScheduleWorld(harness.db, tmp_path / "objects")
        world.define()
        one, two = world.two_weeks()
        world.publish(one)
        yield Env(harness, world, one, two)
    finally:
        harness.close()


def test_the_tool_is_registered_and_says_it_only_proposes(env: Env) -> None:
    tools = {t.name: t for t in asyncio.run(env.h.server.list_tools())}
    tool = tools["propose_publish_schedule_snapshot"]
    assert tool.annotations is not None and tool.annotations.read_only_hint is False
    assert tool.annotations.destructive_hint is False
    assert "Accepting needs the document controller or admin role" in " ".join(
        (tool.description or "").split()
    )


def test_publishing_is_proposed_and_changes_nothing_until_a_controller_accepts(env: Env) -> None:
    out = env.h.structured(
        "propose_publish_schedule_snapshot", project="P123", schedule="MAIN", number=2
    )
    proposal = out["proposal"]
    assert (proposal["status"], proposal["tool"], proposal["agent"]) == (
        "pending", "propose_publish_schedule_snapshot", ACTOR,
    )  # fmt: skip
    assert "MAIN#2" in proposal["summary"]
    assert env.world.schedule().current_snapshot_number == 1  # nothing published
    assert env.world.snapshot(env.two).state == "Valid"
    assert len(env.events("Proposal.Created")) == 1
    assert env.events("Schedule.SnapshotPublished")[0].payload["snapshot_number"] == 1

    boss = "user:boss"
    done = proposals.accept_or_fail(
        env.h.factory, proposal_id=proposal["proposal_id"], by=boss, holds=CONTROLLER
    )
    assert done.status == "accepted"
    assert env.world.schedule().current_snapshot_number == 2
    assert env.world.snapshot(env.one).state == "Superseded"
    assert env.events("Schedule.SnapshotPublished")[-1].actor == boss


def test_a_user_who_is_not_a_controller_cannot_accept_it(env: Env) -> None:
    out = env.h.structured(
        "propose_publish_schedule_snapshot", project="P123", schedule="MAIN", number=2
    )
    with pytest.raises(ProposalAccessError, match="needs the controller role"):
        proposals.accept_or_fail(
            env.h.factory, proposal_id=out["proposal"]["proposal_id"], by="user:ursula"
        )
    with pytest.raises(ProposalAccessError, match="needs the controller role"):
        proposals.accept_or_fail(
            env.h.factory,
            proposal_id=out["proposal"]["proposal_id"],
            by="user:ursula",
            holds=lambda level: level == "user",
        )
    assert env.world.schedule().current_snapshot_number == 1
    done = proposals.accept_or_fail(
        env.h.factory, proposal_id=out["proposal"]["proposal_id"], by="user:dora", holds=CONTROLLER
    )
    assert done.status == "accepted" and env.world.schedule().current_snapshot_number == 2


def test_a_proposal_that_could_not_be_applied_is_refused_at_once(env: Env) -> None:
    with pytest.raises(ToolError, match="no schedule 'NOPE'"):
        env.h.call("propose_publish_schedule_snapshot", project="P123", schedule="NOPE", number=1)
    with pytest.raises(ToolError, match="no snapshot 9"):
        env.h.call("propose_publish_schedule_snapshot", project="P123", schedule="MAIN", number=9)
    with pytest.raises(ToolError, match="only a Valid snapshot can be published"):
        env.h.call("propose_publish_schedule_snapshot", project="P123", schedule="MAIN", number=1)
    assert env.events("Proposal.Created") == []
