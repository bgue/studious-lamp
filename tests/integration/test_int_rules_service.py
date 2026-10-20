"""Authoring rules: create, revise, enable, disable, and what a stored rule must be (ADR-0017)."""

from __future__ import annotations

from typing import Any

import pytest
from intworld import ADMIN, SCOPE, World
from tl_core.integration.errors import (
    DuplicateIntegrationError,
    IntegrationNotFoundError,
    IntegrationStateError,
    InvalidIntegrationError,
)
from tl_core.integration.rules.service import (
    CreateRule,
    ReviseRule,
    handle_create_rule,
    handle_revise_rule,
)
from tl_core.webhooks.rows import as_object, load_json


def create(world: World, **fields: Any) -> str:
    return world.create_rule(**fields)


def refused_create(world: World, **fields: Any) -> str:
    with pytest.raises(InvalidIntegrationError) as caught:
        world.create_rule(**fields)
    return str(caught.value)


def test_a_new_rule_is_disabled_in_propose_mode_with_its_own_service_actor(world: World) -> None:
    rule_id = create(world)
    row = world.rows("SELECT * FROM cur_rule WHERE rule_id = :i", i=rule_id)[0]
    assert row["service_actor"] == "svc:rule-hse-notify"
    assert (bool(row["enabled"]), row["mode"], row["access"], row["version"]) == (
        False,
        "propose",
        "user",
        1,
    )
    assert row["owner"] == ADMIN and row["enabled_from_seq"] == 0


def test_the_service_actor_cannot_be_chosen_by_the_caller(world: World) -> None:
    """The model has no such field; an extra one is ignored and the actor is made from the key."""
    rule_id = create(world, service_actor="svc:rule-other")
    row = world.rows("SELECT service_actor FROM cur_rule WHERE rule_id = :i", i=rule_id)[0]
    assert row["service_actor"] == "svc:rule-hse-notify"


def test_a_key_is_unique(world: World) -> None:
    create(world)
    with pytest.raises(DuplicateIntegrationError):
        create(world)


@pytest.mark.parametrize(
    ("fields", "wanted"),
    [
        ({"when": {}}, "when must narrow"),
        ({"when": {"nonsense": ["x"]}}, "when:"),
        ({"when": {"event_types": []}}, "when:"),
        ({"condition": "status:("}, "condition:"),
        ({"then": []}, "at least"),
        ({"then": [{"command": "VoidRecord", "args": {}}]}, "not a command automation"),
        ({"then": [{"command": "PostToFeed", "args": {"actor": "user:x"}}]}, "server sets"),
        ({"then": [{"command": "PostToFeed", "args": {"source": "rule:x"}}]}, "server sets"),
        ({"then": [{"command": "PostToFeed", "args": {"body": "${nope}"}}]}, "not a binding"),
        ({"then": [{"command": "PostToFeed", "args": {"body": "$5"}}]}, "lone $"),
        ({"key": "Bad Key"}, "key"),
        ({"integration_app": "no-such-app"}, "no integration app"),
        ({"title": ""}, "title"),
    ],
)
def test_a_rule_that_cannot_run_is_not_stored(
    world: World, fields: dict[str, Any], wanted: str
) -> None:
    try:
        message = refused_create(world, **fields)
    except Exception as exc:  # a model refusal that is not an integration error
        message = str(exc)
    assert wanted.lower() in message.lower()
    assert world.rows("SELECT rule_id FROM cur_rule") == []


def test_more_steps_than_the_limit_are_refused(world: World) -> None:
    step = {"command": "PostToFeed", "args": {"body": "x"}}
    assert "at most" in refused_create(world, then=[step] * 6).lower()


def test_a_revision_is_a_new_version_that_keeps_the_identity(world: World) -> None:
    rule_id = create(world)
    world.revise_rule(rule_id, {"title": "Notify the HSE team", "mode": "act"}, reason="go live")
    row = world.rows("SELECT * FROM cur_rule WHERE rule_id = :i", i=rule_id)[0]
    assert (row["version"], row["mode"], row["title"]) == (2, "act", "Notify the HSE team")
    assert row["service_actor"] == "svc:rule-hse-notify" and row["key"] == "hse-notify"
    event = world.events("Rule.Revised")[0]
    payload = as_object(load_json(event["payload"]))
    assert payload["reason"] == "go live" and payload["version"] == 2
    assert payload["rule"]["mode"] == "act" and payload["rule"]["enabled"] is False


def test_a_revision_needs_a_reason_and_may_not_change_the_identity(world: World) -> None:
    rule_id = create(world)
    with pytest.raises(Exception, match="reason"):
        ReviseRule(
            actor=ADMIN,
            source="t",
            scope=SCOPE,
            rule_id=rule_id,
            changes={"title": "x"},
            reason=" ",
        )
    for forbidden in ("key", "scope", "service_actor", "enabled", "version"):
        with pytest.raises(InvalidIntegrationError):
            world.revise_rule(rule_id, {forbidden: "x"})
    with pytest.raises(InvalidIntegrationError):
        world.revise_rule(rule_id, {})
    with pytest.raises(InvalidIntegrationError):
        world.revise_rule(rule_id, {"title": "Notify HSE"})  # nothing changes


def test_a_revision_is_checked_like_a_new_rule(world: World) -> None:
    rule_id = create(world)
    for changes in ({"when": {}}, {"condition": "status:("}, {"access": "admin"}, {"mode": "run"}):
        with pytest.raises(InvalidIntegrationError):
            world.revise_rule(rule_id, changes)
    assert world.rows("SELECT version FROM cur_rule")[0]["version"] == 1


def test_a_revision_of_a_rule_that_moved_is_a_conflict(world: World) -> None:
    from tl_core.ledger import ConcurrencyError

    rule_id = create(world)
    with pytest.raises(ConcurrencyError), world.factory() as uow:
        handle_revise_rule(
            uow,
            ReviseRule(
                actor=ADMIN, source="t", scope=SCOPE, rule_id=rule_id,
                changes={"title": "x"}, reason="r", expected_version=7,
            ),
        )  # fmt: skip


def test_a_rule_is_found_in_its_own_scope_only(world: World) -> None:
    rule_id = create(world)
    with pytest.raises(IntegrationNotFoundError):
        world.revise_rule(rule_id, {"title": "x"}, scope="project:OTHER")
    with pytest.raises(IntegrationNotFoundError):
        world.switch_rule(rule_id, on=True, scope="company")
    with pytest.raises(IntegrationNotFoundError):
        world.switch_rule("01J9Z6Q4W3X2Y1V0T9S8R7Q6PB", on=True)


def test_enable_and_disable_say_where_they_started(world: World) -> None:
    rule_id = create(world)
    with pytest.raises(IntegrationStateError):
        world.switch_rule(rule_id, on=False)
    world.switch_rule(rule_id, on=True)
    row = world.rows("SELECT * FROM cur_rule WHERE rule_id = :i", i=rule_id)[0]
    assert bool(row["enabled"]) and row["enabled_from_seq"] > 0
    with pytest.raises(IntegrationStateError):
        world.switch_rule(rule_id, on=True)
    world.switch_rule(rule_id, on=False)
    assert not bool(world.rows("SELECT enabled FROM cur_rule")[0]["enabled"])


def test_a_company_rule_is_created_at_company_scope(world: World) -> None:
    with world.factory() as uow:
        made = handle_create_rule(
            uow,
            CreateRule(
                actor=ADMIN, source="t", scope="company", key="c-rule", title="c",
                when={"hashtags": ["a"]},
                then=[{"command": "PostToFeed", "args": {"body": "x"}}],
            ),
        )  # fmt: skip
    assert made.events[0].scope == "company"


def register_app(world: World, name: str) -> None:
    from tl_core.integration import streams as s
    from tl_core.ledger import NewEvent
    from tl_core.util import new_ulid

    app = new_ulid()
    payload = {"app_id": app, "name": name, "label": "A", "owner": ADMIN}
    with world.factory() as uow:
        uow.append(
            stream_id=app,
            stream_type=s.APP_STREAM_TYPE,
            scope=SCOPE,
            expected_version=0,
            events=[NewEvent(event_type=s.APP_REGISTERED, payload=payload)],
            actor=ADMIN,
            source="t",
            correlation_id=new_ulid(),
        )


def test_an_app_can_own_a_rule_and_switching_the_app_off_stops_it(world: World) -> None:
    from sqlalchemy import text

    register_app(world, "acme")
    rule_id = create(world, integration_app="acme")
    assert world.rows("SELECT integration_app FROM cur_rule")[0]["integration_app"] == "acme"
    world.revise_rule(rule_id, {"mode": "act"})
    world.switch_rule(rule_id, on=True)
    with world.factory() as uow:
        uow.conn().execute(text("UPDATE cur_integration_app SET enabled = :f"), {"f": False})
    world.post("a #safety")
    assert world.worker().run_until_idle().fired == 0
