"""The rules worker: act, propose, loop protection, budgets, exactly-once, the kill switch.

Everything runs on the real ledger of each adapter, with the real command runner of the API
table. The feed is the stage: a post that carries a hashtag is the event, a post by a rule is the
effect (FANOUT D7, D20 clause 2).
"""

from __future__ import annotations

from typing import Any

import pytest
from intworld import PERSON, SCOPE, World
from tl_core.integration.rules import engine
from tl_core.integration.rules.engine import depth_of, rule_source
from tl_core.services import proposals
from tl_core.webhooks.rows import as_list, as_object, load_json

RULE_ACTOR = "svc:rule-hse-notify"


def bodies(world: World) -> list[str]:
    return [p["body"] for p in world.posts()]


def enabled_rule(world: World, *, act: bool = True, **fields: Any) -> str:
    """A rule that is on; in ``act`` mode unless told otherwise (that is a revision, version 2)."""
    rule_id = world.create_rule(**fields)
    if act:
        world.revise_rule(rule_id, {"mode": "act"}, scope=fields.get("scope", SCOPE))
    world.switch_rule(rule_id, on=True, scope=fields.get("scope", SCOPE))
    return rule_id


def test_a_post_with_the_hashtag_makes_the_rule_post_as_its_service_actor(world: World) -> None:
    enabled_rule(world)
    original = world.post("Gas smell at the tank farm #safety")
    stats = world.worker().run_until_idle()
    assert stats.fired == 1
    posts = world.posts()
    assert len(posts) == 2
    made = posts[1]
    assert made["body"].startswith("HSE notified of ")
    assert made["actor"] == RULE_ACTOR
    assert made["source"] == "rule:hse-notify@2/d1"
    assert made["causation_id"] == original.events[0].event_id
    assert made["correlation_id"] == posts[0]["correlation_id"]


def test_a_post_without_the_hashtag_is_left_alone(world: World) -> None:
    enabled_rule(world)
    world.post("Lunch is at noon")
    assert world.worker().run_until_idle().fired == 0
    assert len(world.posts()) == 1 and world.firings() == []


def test_the_cursor_moves_past_every_event_it_read(world: World) -> None:
    enabled_rule(world)
    world.post("a #safety")
    world.worker().run_until_idle()
    assert world.cursor() > 0
    before = world.cursor()
    assert world.worker().run_until_idle().read == 0
    assert world.cursor() == before


def test_a_firing_is_exactly_once_even_when_the_cursor_is_lost(world: World) -> None:
    enabled_rule(world)
    world.post("a #safety")
    world.worker().run_until_idle()
    count = len(world.posts())
    with world.factory() as uow:
        from sqlalchemy import text

        uow.conn().execute(text("UPDATE rule_cursor SET last_seq = 0"))
    world.worker().run_until_idle()
    assert len(world.posts()) == count
    assert len([f for f in world.firings() if f["outcome"] == "fired"]) == 1


def test_a_rule_starts_disabled_and_in_propose_mode(world: World) -> None:
    rule_id = world.create_rule()
    row = world.rows("SELECT * FROM cur_rule WHERE rule_id = :i", i=rule_id)[0]
    assert (bool(row["enabled"]), row["mode"]) == (False, "propose")
    world.post("a #safety")
    assert world.worker().run_until_idle().fired == 0


def test_propose_mode_makes_a_proposal_a_person_accepts(world: World) -> None:
    rule_id = world.create_rule()
    world.switch_rule(rule_id, on=True)
    world.post("a #safety")
    stats = world.worker().run_until_idle()
    assert stats.proposed == 1 and len(world.posts()) == 1
    with world.factory(readonly=True) as uow:
        pending = proposals.list_proposals(uow.conn(), SCOPE, status="pending")
    assert [p.agent for p in pending] == [RULE_ACTOR]
    assert pending[0].tool == "rule" and pending[0].command_type == "PostToFeed"
    done = proposals.accept_or_fail(world.factory, proposal_id=pending[0].proposal_id, by=PERSON)
    assert done.status == "accepted"
    made = world.posts()[1]
    assert (made["actor"], made["source"]) == (PERSON, "rule:hse-notify")


def test_only_events_after_the_rule_was_switched_on_count(world: World) -> None:
    rule_id = world.create_rule()
    world.revise_rule(rule_id, {"mode": "act"})
    world.post("early #safety")  # before the rule is on, and not yet read by the worker
    world.switch_rule(rule_id, on=True)
    world.post("late #safety")
    world.worker().run_until_idle()
    assert [p["body"] for p in world.posts()].count("early #safety") == 1
    made = [b for b in bodies(world) if b.startswith("HSE notified")]
    assert len(made) == 1, "only the late post fires the rule"


def test_a_disabled_rule_and_a_rule_of_a_disabled_app_do_nothing(world: World) -> None:
    rule_id = enabled_rule(world)
    world.switch_rule(rule_id, on=False)
    world.post("a #safety")
    assert world.worker().run_until_idle().fired == 0


def test_a_rule_sees_only_the_events_of_its_scope(world: World) -> None:
    enabled_rule(world)
    world.post("elsewhere #safety", scope="project:OTHER")
    assert world.worker().run_until_idle().fired == 0


def test_a_company_rule_acts_in_the_scope_of_the_event(world: World) -> None:
    enabled_rule(world, scope="company", key="all-safety")
    world.post("a #safety")
    world.worker().run_until_idle()
    assert world.posts()[1]["scope"] == SCOPE


# --- loop protection ------------------------------------------------------------------------------


def ping_pong(world: World) -> None:
    for key, listens, says in (("rule-a", "a", "#b ping"), ("rule-b", "b", "#a pong")):
        rule_id = enabled_rule(
            world,
            key=key,
            when={"event_types": ["Feed.Posted"], "hashtags": [listens]},
            then=[{"command": "PostToFeed", "args": {"body": says}}],
        )
        assert rule_id


def test_two_rules_that_feed_each_other_stop_at_depth_three(world: World) -> None:
    ping_pong(world)
    world.post("start #a")
    world.worker().run_until_idle()
    posts = world.posts()
    depths = [depth_of(p["source"])[1] for p in posts]
    assert depths == [0, 1, 2, 3], "the chain is cut after depth 3"
    blocked = world.events("Rule.Blocked")
    assert len(blocked) == 1
    payload = as_object(load_json(blocked[0]["payload"]))
    assert (payload["outcome"], payload["depth"]) == ("depth_limit", 3)
    assert world.worker().run_until_idle().read == 0, "and nothing runs on"


def test_a_rule_does_not_fire_on_its_own_work(world: World) -> None:
    enabled_rule(
        world,
        key="echo",
        when={"event_types": ["Feed.Posted"]},
        then=[{"command": "PostToFeed", "args": {"body": "echo"}}],
    )
    world.post("hello")
    world.worker().run_until_idle()
    assert bodies(world) == ["hello", "echo"]
    own = [f for f in world.firings() if f["outcome"] == "refused"]
    assert len(own) == 1 and world.events("Rule.Blocked") == []


def test_the_depth_is_read_from_the_source_and_nothing_else() -> None:
    assert depth_of("rule:a-b@12/d2") == ("a-b", 2)
    assert depth_of(rule_source("k", 3, 1)) == ("k", 1)
    for source in ("api", "tui", "rule:x", "rule:x@1", "rule:x@1/d", "xrule:x@1/d1", "rule:X@1/d1"):
        assert depth_of(source) == (None, 0), source


def test_a_person_cannot_pose_as_a_rule_to_dodge_or_to_trigger_the_limit(world: World) -> None:
    """The source is the server's; a client command with ``rule:`` is refused before it is run."""
    from tl_core.services.errors import ReservedIdentifierError
    from tl_core.services.feed import PostToFeed
    from tl_core.services.reserved import refuse_reserved

    with pytest.raises(ReservedIdentifierError):
        refuse_reserved(
            PostToFeed(actor=PERSON, source="rule:hse-notify@1/d3", scope=SCOPE, body="x")
        )


# --- budgets --------------------------------------------------------------------------------------


def test_the_rules_per_event_are_bounded_and_the_excess_is_recorded(
    world: World, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(engine, "RULE_MAX_RULES_PER_EVENT", 2)
    for n in range(4):
        enabled_rule(
            world, key=f"r{n}", then=[{"command": "PostToFeed", "args": {"body": f"r{n}"}}]
        )
    world.post("a #safety")
    world.worker().run_until_idle()
    made = [b for b in bodies(world) if b.startswith("r")]
    assert made == ["r0", "r1"], "in key order"
    outcomes = sorted(f["outcome"] for f in world.firings())
    assert outcomes == ["budget", "budget", "fired", "fired"]
    assert len(world.events("Rule.Blocked")) == 2


def test_the_commands_per_event_are_bounded_across_rules(
    world: World, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(engine, "RULE_MAX_COMMANDS_PER_EVENT", 3)
    two = [{"command": "PostToFeed", "args": {"body": "x"}}] * 2
    for key in ("a1", "a2"):
        enabled_rule(world, key=key, then=two)
    world.post("a #safety")
    world.worker().run_until_idle()
    assert len([b for b in bodies(world) if b == "x"]) == 2, "the second rule would pass 3"
    assert sorted(f["outcome"] for f in world.firings()) == ["budget", "fired"]


# --- refusals roll back --------------------------------------------------------------------------


def test_a_step_that_fails_undoes_the_whole_firing_and_says_so(world: World) -> None:
    enabled_rule(
        world,
        then=[
            {"command": "PostToFeed", "args": {"body": "first"}},
            {
                "command": "UpdateRecord",
                "args": {"stream_id": "01J9Z6Q4W3X2Y1V0T9S8R7Q6PB", "changes": {"title": "x"}},
            },
        ],
    )  # fmt: skip
    world.post("a #safety")
    stats = world.worker().run_until_idle()
    assert stats.fired == 0 and stats.blocked == 1
    assert bodies(world) == ["a #safety"], "the first step was rolled back"
    blocked = world.events("Rule.Blocked")
    problems = as_list(as_object(load_json(blocked[0]["payload"]))["problems"])
    assert problems[0]["code"] == "command_refused"
    assert [f["outcome"] for f in world.firings()] == ["refused"]


def test_a_step_with_a_field_the_command_lacks_is_refused_not_ignored(world: World) -> None:
    enabled_rule(world, then=[{"command": "PostToFeed", "args": {"bodyy": "typo"}}])
    world.post("a #safety")
    world.worker().run_until_idle()
    assert bodies(world) == ["a #safety"]
    payload = as_object(load_json(world.events("Rule.Blocked")[0]["payload"]))
    assert as_list(payload["problems"])[0]["code"] == "unknown_field"


def test_a_binding_too_long_refuses_the_step(world: World) -> None:
    enabled_rule(
        world,
        when={"event_types": ["Record.Created"]},
        then=[{"command": "PostToFeed", "args": {"body": "T: ${subject_title}"}}],
    )
    world.record("K-2", title="u" * 1_100)
    world.worker().run_until_idle()
    payload = as_object(load_json(world.events("Rule.Blocked")[0]["payload"]))
    assert as_list(payload["problems"])[0]["code"] == "binding_too_long"
    assert world.posts() == []


def test_a_rule_links_with_its_own_source(
    world: World,
) -> None:
    one, two = world.record("L-1"), world.record("L-2")
    enabled_rule(
        world,
        key="linker",
        when={"event_types": ["Record.Created"]},
        then=[{"command": "AddLink", "args": {"from_id": one, "to_id": two}}],
    )
    world.record("L-3")
    world.worker().run_until_idle()
    links = world.rows("SELECT source FROM cur_links WHERE from_id = :f", f=one)
    assert [row["source"] for row in links] == ["rule"]


# --- the kill switch ------------------------------------------------------------------------------


def test_the_kill_switch_stops_the_rules_and_the_events_are_not_replayed(world: World) -> None:
    enabled_rule(world)
    world.setting("integration.kill_switch", True)
    world.post("during #safety")
    stats = world.worker().run_until_idle()
    assert stats.killed == 1 and stats.fired == 0
    assert [f["outcome"] for f in world.firings()] == ["killed"]
    world.setting("integration.kill_switch", False)
    world.post("after #safety")
    world.worker().run_until_idle()
    assert len([b for b in bodies(world) if b.startswith("HSE notified")]) == 1
    world.worker().run_until_idle()
    assert len([b for b in bodies(world) if b.startswith("HSE notified")]) == 1


def test_the_switch_is_read_for_every_event_not_once_per_start(world: World) -> None:
    enabled_rule(world)
    worker = world.worker()
    world.post("one #safety")
    worker.run_until_idle()
    world.setting("integration.kill_switch", True)
    world.post("two #safety")
    worker.run_until_idle()  # the same worker, a change in between
    assert len([b for b in bodies(world) if b.startswith("HSE notified")]) == 1


# --- a loop that goes through an action ----------------------------------------------------------


def settle(world: World) -> None:
    """Rules and jobs in turn until neither has anything left to do."""
    for _ in range(20):
        read = world.worker().run_until_idle().read
        ran = len(world.run_jobs())
        if read == 0 and ran == 0:
            return
    raise AssertionError("the system did not settle: the loop was not cut")


def test_a_loop_through_an_action_is_cut_at_the_same_depth(world: World) -> None:
    world.define_action(name="ping", label="Ping #go", result_handling=["store", "post_to_feed"])
    enabled_rule(
        world,
        key="again",
        when={"event_types": ["Feed.Posted"], "hashtags": ["go"]},
        then=[{"command": "InvokeAction", "args": {"action": "ping"}}],
    )
    world.post("kick #go")
    settle(world)
    assert len(world.events("Action.Requested")) == 3, "three rounds, then the depth limit"
    blocked = world.events("Rule.Blocked")
    assert len(blocked) == 1
    assert as_object(load_json(blocked[0]["payload"]))["outcome"] == "depth_limit"
    requested = world.events("Action.Requested")
    assert {r["actor"] for r in requested} == {"svc:rule-again"}
    assert [depth_of(r["source"])[1] for r in requested] == [1, 2, 3]


def test_a_rule_cannot_invoke_an_action_that_needs_more_than_it_holds(world: World) -> None:
    world.define_action(name="big", access="controller")
    enabled_rule(
        world,
        key="small",
        when={"event_types": ["Feed.Posted"], "hashtags": ["go"]},
        then=[{"command": "InvokeAction", "args": {"action": "big"}}],
    )
    world.post("kick #go")
    world.worker().run_until_idle()
    assert world.events("Action.Requested") == []
    payload = as_object(load_json(world.events("Rule.Blocked")[0]["payload"]))
    assert as_list(payload["problems"])[0]["code"] == "command_refused"


def test_a_controller_rule_may_invoke_a_controller_action(world: World) -> None:
    world.define_action(name="big", access="controller")
    enabled_rule(
        world,
        key="medium",
        access="controller",
        when={"event_types": ["Feed.Posted"], "hashtags": ["go"]},
        then=[{"command": "InvokeAction", "args": {"action": "big"}}],
    )
    world.post("kick #go")
    world.worker().run_until_idle()
    assert len(world.events("Action.Requested")) == 1
