"""The error queue (retry) and the dry run of a mapping (FANOUT D4; admin commands)."""

from __future__ import annotations

import hashlib
from typing import Any

import pytest
from intworld import ADMIN, SCOPE, World
from tl_core.integration.errors import (
    IntegrationNotFoundError,
    IntegrationStateError,
    InvalidIntegrationError,
)
from tl_core.integration.inbound import store as body_store
from tl_core.integration.inbound.delivery import (
    RetryInboundDelivery,
    dry_run_mapping,
    handle_retry_delivery,
)
from tl_core.integration.inbound.service import ReviseInboundEndpoint, handle_revise_endpoint
from tl_core.webhooks.rows import as_object, load_json


@pytest.fixture(autouse=True)
def store() -> Any:
    body_store.configure(None)
    yield
    body_store.configure(None)


def revise(world: World, endpoint_id: str, changes: dict[str, Any]) -> None:
    with world.factory() as uow:
        handle_revise_endpoint(
            uow,
            ReviseInboundEndpoint(
                actor=ADMIN, source="test", scope=SCOPE, endpoint_id=endpoint_id,
                changes=changes, reason="fix",
            ),
        )  # fmt: skip


def retry(world: World, delivery_id: str, corrected: Any = None, *, scope: str = SCOPE) -> Any:
    with world.factory() as uow:
        return handle_retry_delivery(
            uow,
            RetryInboundDelivery(
                actor=ADMIN, source="api", scope=scope, delivery_id=delivery_id,
                corrected_payload=corrected,
            ),
        )  # fmt: skip


def broken(world: World) -> tuple[Any, str]:
    """An endpoint whose mapping needs `$.text` as a string, and a delivery that fails on it."""
    made = world.endpoint(mapping='{"command": "PostToFeed", "args": {"body": $.text.x.y}}')
    delivery_id = world.deliver(made.endpoint_id, {"text": "hello"})
    world.inbound_runner().run_until_idle()
    assert world.deliveries()[0]["state"] == "failed"
    return made, delivery_id


def test_a_failed_delivery_is_retried_with_the_current_mapping(world: World) -> None:
    body_store.configure(world.store)
    made, delivery_id = broken(world)
    revise(
        world, made.endpoint_id, {"mapping": '{"command": "PostToFeed", "args": {"body": $.text}}'}
    )
    made_event = retry(world, delivery_id)
    assert made_event.events[0].event_type == "Inbound.Retried"
    row = world.deliveries()[0]
    assert (row["state"], row["error_code"], row["endpoint_version"]) == ("queued", None, 3)
    world.inbound_runner().run_until_idle()
    assert world.deliveries()[0]["state"] == "applied"
    assert [p["body"] for p in world.posts()] == ["hello"]
    body = as_object(load_json(world.events("Inbound.Retried")[0]["payload"]))
    assert body["by"] == ADMIN and body["corrected_sha256"] is None
    assert body["original_sha256"] == world.deliveries()[0]["payload_sha256"]


def test_a_corrected_payload_is_stored_beside_the_original(world: World) -> None:
    body_store.configure(world.store)
    made, delivery_id = broken(world)
    revise(
        world, made.endpoint_id, {"mapping": '{"command": "PostToFeed", "args": {"body": $.text}}'}
    )
    original_key = world.deliveries()[0]["object_key"]
    before = world.store.objects[original_key]
    retry(world, delivery_id, {"text": "corrected"})
    world.inbound_runner().run_until_idle()
    row = world.deliveries()[0]
    assert [p["body"] for p in world.posts()] == ["corrected"]
    assert world.store.objects[original_key] == before  # the received body is never changed
    assert row["corrected_object_key"].startswith(original_key + ".corrected.")
    sha = hashlib.sha256(world.store.objects[row["corrected_object_key"]]).hexdigest()
    event = as_object(load_json(world.events("Inbound.Retried")[0]["payload"]))
    assert event["corrected_sha256"] == sha and row["payload_sha256"] != sha
    with world.factory(readonly=True) as uow:
        assert body_store.orphans(uow, world.store) == []


def test_only_a_failed_or_killed_delivery_retries(world: World) -> None:
    body_store.configure(world.store)
    made = world.endpoint()
    delivery_id = world.deliver(made.endpoint_id, {"text": "x"})
    with pytest.raises(IntegrationStateError):  # queued
        retry(world, delivery_id)
    world.inbound_runner().run_until_idle()
    with pytest.raises(IntegrationStateError):  # applied
        retry(world, delivery_id)
    with pytest.raises(IntegrationNotFoundError):
        retry(world, delivery_id, scope="project:OTHER")
    with pytest.raises(IntegrationNotFoundError):
        retry(world, "01J0000000000000000000000X")


def test_a_killed_delivery_can_be_retried_after_the_switch_is_off(world: World) -> None:
    body_store.configure(world.store)
    made = world.endpoint()
    delivery_id = world.deliver(made.endpoint_id, {"text": "x"})
    world.setting("integration.kill_switch", True)
    world.inbound_runner().run_until_idle()
    assert world.deliveries()[0]["state"] == "killed"
    world.setting("integration.kill_switch", False)
    retry(world, delivery_id)
    world.inbound_runner().run_until_idle()
    assert world.deliveries()[0]["state"] == "applied" and len(world.posts()) == 1


@pytest.mark.parametrize("bad", [float("nan"), "x" * 300_000, [[[]]] * 1, None])
def test_a_corrected_payload_must_be_acceptable_json_within_the_cap(world: World, bad: Any) -> None:
    body_store.configure(world.store)
    _, delivery_id = broken(world)
    if bad is None or bad == [[[]]]:
        retry(world, delivery_id, bad)  # None means "no correction"; a small list is fine
        return
    with pytest.raises((InvalidIntegrationError, ValueError)):
        retry(world, delivery_id, bad)
    assert world.deliveries()[0]["state"] == "failed"


def test_a_retry_without_a_store_is_refused_only_when_a_correction_needs_one(world: World) -> None:
    _, delivery_id = broken(world)
    with pytest.raises(IntegrationStateError):
        retry(world, delivery_id, {"text": "x"})
    retry(world, delivery_id)  # no correction, no store needed


# --- dry run -------------------------------------------------------------------------------------


def dry(world: World, endpoint_id: str, **kw: Any) -> Any:
    with world.factory(readonly=True) as uow:
        return dry_run_mapping(uow, world.runner, endpoint_id=endpoint_id, scope=SCOPE, **kw)


def test_a_dry_run_over_a_sample_plans_commands_and_writes_nothing(world: World) -> None:
    made = world.endpoint(on=False, live=False)
    before = len(world.rows("SELECT 1 FROM events"))
    report = dry(world, made.endpoint_id, sample={"text": "hello"})
    assert report.status == "ok" and len(report.commands) == 1
    planned = report.commands[0]
    assert (planned.command_type, planned.permitted, planned.problem) == ("PostToFeed", True, None)
    assert planned.command["body"] == "hello" and planned.command["scope"] == SCOPE
    assert len(world.rows("SELECT 1 FROM events")) == before and world.posts() == []


def test_a_dry_run_reports_each_refused_command_and_still_plans_the_rest(world: World) -> None:
    mapping = (
        '[{"command": "PostToFeed", "args": {"body": "ok"}}, '
        '{"command": "CreateRecord", "args": {"record_type": "core.Record", "title": "T"}}, '
        '{"command": "AddLink", "args": {"from_id": {"$key": "NO-1"}, "to_id": "x"}}]'
    )
    made = world.endpoint(mapping=mapping, allowed_commands=["PostToFeed", "AddLink"])
    report = dry(world, made.endpoint_id, sample={})
    flags = [
        (c.command_type, c.permitted, c.problem.code if c.problem else None)
        for c in report.commands
    ]
    assert flags == [
        ("PostToFeed", True, None),
        ("CreateRecord", False, "command_not_allowed"),
        ("AddLink", False, "key_not_found"),
    ]


def test_a_dry_run_over_a_stored_delivery(world: World) -> None:
    body_store.configure(world.store)
    made = world.endpoint()
    delivery_id = world.deliver(made.endpoint_id, {"text": "stored"})
    report = dry(world, made.endpoint_id, delivery_id=delivery_id)
    assert report.commands[0].command["body"] == "stored"
    assert report.payload_sha256 == world.deliveries()[0]["payload_sha256"]
    other = world.endpoint("other")
    with pytest.raises(IntegrationNotFoundError):
        dry(world, other.endpoint_id, delivery_id=delivery_id)


def test_a_dry_run_reports_a_mapping_error_and_checks_its_arguments(world: World) -> None:
    made = world.endpoint(mapping='{"command": "PostToFeed", "args": {"body": $number($.text)}}')
    report = dry(world, made.endpoint_id, sample={"text": "abc"})
    assert report.status == "error" and report.commands == []
    with pytest.raises(InvalidIntegrationError):
        dry(world, made.endpoint_id)
    with pytest.raises(InvalidIntegrationError):
        dry(world, made.endpoint_id, sample={}, delivery_id="x")
    with pytest.raises(IntegrationNotFoundError):
        dry(world, "01J0000000000000000000000X", sample={})
