"""Dry run of a rule over history: what it would have done, with nothing written (FANOUT D7)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from intworld import World
from tl_core.integration.contract import Rule
from tl_core.integration.rules.dryrun import draft_rule, dry_run_rule
from tl_core.integration.rules.engine import load_rule


def stored(world: World, rule_id: str):  # noqa: ANN201
    with world.factory(readonly=True) as uow:
        found = load_rule(uow.conn(), rule_id)
    assert found is not None
    return found


def event_count(world: World) -> int:
    return int(world.rows("SELECT COUNT(*) AS n FROM events")[0]["n"])


def test_it_lists_what_the_rule_would_have_done_and_writes_nothing(world: World) -> None:
    rule_id = world.create_rule()  # disabled, propose: a dry run does not care
    world.post("first #safety")
    world.post("no tag")
    world.post("second #safety")
    before = event_count(world)
    report = dry_run_rule(world.factory, world.runner, stored(world, rule_id))
    assert event_count(world) == before
    assert world.rows("SELECT COUNT(*) AS n FROM rule_firing")[0]["n"] == 0
    assert report.events_read >= 4 and not report.truncated
    assert [f.outcome for f in report.firings] == ["proposed", "proposed"]
    first = report.firings[0]
    assert first.condition_basis == "current" and first.depth == 0
    planned = first.planned[0]
    assert planned.command_type == "PostToFeed" and planned.permitted and planned.access == "user"
    assert planned.problem is None and "actor" not in planned.command
    assert planned.command["scope"] == "project:P123"


def test_a_range_by_seq_and_by_time_narrows_the_events(world: World) -> None:
    rule_id = world.create_rule()
    world.post("first #safety")
    middle = world.post("second #safety").events[0].seq
    world.post("third #safety")
    rule = stored(world, rule_id)
    only_second = dry_run_rule(world.factory, world.runner, rule, from_seq=middle, to_seq=middle)
    assert [f.seq for f in only_second.firings] == [middle]
    future = datetime.now(UTC) + timedelta(days=1)
    assert dry_run_rule(world.factory, world.runner, rule, since=future).firings == []
    past = datetime.now(UTC) - timedelta(days=1)
    assert len(dry_run_rule(world.factory, world.runner, rule, since=past).firings) == 3


def test_the_limits_stop_the_report_and_say_so(world: World) -> None:
    rule_id = world.create_rule()
    for n in range(5):
        world.post(f"post {n} #safety")
    rule = stored(world, rule_id)
    by_events = dry_run_rule(world.factory, world.runner, rule, max_events=2)
    assert by_events.truncated and by_events.events_read == 2
    by_firings = dry_run_rule(world.factory, world.runner, rule, max_firings=2)
    assert by_firings.truncated and len(by_firings.firings) == 2


def test_a_draft_is_tried_before_it_is_stored(world: World) -> None:
    world.post("a #safety")
    draft = Rule(
        key="draft-rule",
        title="Draft",
        scope="project:P123",
        when={"event_types": ["Feed.Posted"], "hashtags": ["safety"]},
        then=[{"command": "PostToFeed", "args": {"body": "seen ${event_id}"}}],  # type: ignore[list-item]
        service_actor="svc:rule-draft-rule",
        owner="user:boss",
        mode="act",
    )
    report = dry_run_rule(world.factory, world.runner, draft_rule(draft))
    assert [f.outcome for f in report.firings] == ["fired"]
    assert report.firings[0].planned[0].command["body"].startswith("seen ")
    assert world.rows("SELECT rule_id FROM cur_rule") == []


def test_a_refused_step_shows_its_problem_and_the_outcome(world: World) -> None:
    rule_id = world.create_rule(
        then=[{"command": "PostToFeed", "args": {"bodyy": "typo"}}],
    )
    world.post("a #safety")
    report = dry_run_rule(world.factory, world.runner, stored(world, rule_id))
    firing = report.firings[0]
    assert firing.outcome == "refused"
    assert firing.problems[0].code == "unknown_field"
    assert firing.planned[0].problem is not None and not firing.planned[0].permitted


def test_a_condition_is_evaluated_on_the_record_as_it_is_now(world: World) -> None:
    rule_id = world.create_rule(
        when={"event_types": ["Record.Created"]},
        condition="key:K-2",
        then=[{"command": "PostToFeed", "args": {"body": "found ${subject_key}"}}],
    )
    world.record("K-1")
    world.record("K-2")
    report = dry_run_rule(world.factory, world.runner, stored(world, rule_id))
    outcomes = {f.outcome for f in report.firings}
    assert outcomes == {"skipped_condition", "proposed"}
    assert all(f.condition_basis == "current" for f in report.firings)


def test_it_applies_the_same_loop_protection_as_the_worker(world: World) -> None:
    rule_id = world.create_rule(
        key="echo",
        when={"event_types": ["Feed.Posted"]},
        then=[{"command": "PostToFeed", "args": {"body": "echo"}}],
    )
    world.revise_rule(rule_id, {"mode": "act"})
    world.switch_rule(rule_id, on=True)
    world.post("hello")
    world.worker().run_until_idle()
    report = dry_run_rule(world.factory, world.runner, stored(world, rule_id))
    assert [f.outcome for f in report.firings] == ["fired", "refused"]
    assert report.firings[1].problems[0].code == "self_trigger"


def test_it_ignores_the_kill_switch_and_the_moment_the_rule_was_switched_on(world: World) -> None:
    world.post("old #safety")
    rule_id = world.create_rule()
    world.switch_rule(rule_id, on=True)  # after the post
    world.setting("integration.kill_switch", True)
    report = dry_run_rule(world.factory, world.runner, stored(world, rule_id))
    assert len(report.firings) == 1


def test_a_range_past_the_end_is_an_empty_report(world: World) -> None:
    rule_id = world.create_rule()
    report = dry_run_rule(world.factory, world.runner, stored(world, rule_id), from_seq=1000)
    assert report.firings == [] and report.events_read == 0 and not report.truncated
