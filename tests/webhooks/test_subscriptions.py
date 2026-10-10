"""Subscription commands: validation, events without secrets, rotation overlap."""

from __future__ import annotations

import json
from typing import Any

import pytest
from tl_core.services.errors import NoChangesError
from tl_core.webhooks.signing import SigningSecret, verify
from tl_core.webhooks.subscriptions import (
    AlreadyInStateError,
    DisableWebhookSubscription,
    EnableWebhookSubscription,
    InvalidSubscriptionError,
    RotateWebhookSecret,
    SubscriptionNotFoundError,
    UpdateWebhookSubscription,
    disable_subscription,
    enable_subscription,
    rotate_secret,
    update_subscription,
)
from world import SCOPE, World

COMMON: dict[str, Any] = {"actor": "user:alice", "source": "test", "scope": SCOPE}


def row(world: World, sid: str) -> dict[str, object]:
    return world.query("SELECT * FROM cur_webhook_subscription WHERE subscription_id = :s", s=sid)[
        0
    ]


def test_create_projects_a_row_and_hands_back_the_secret_once(world: World) -> None:
    issued = world.subscribe(filter={"event_types": ["Record.*"]}, mode="delta")
    current = row(world, issued.subscription_id)
    assert current["status"] == "active"
    assert current["payload_mode"] == "delta"
    assert json.loads(str(current["filter_json"])) == {"event_types": ["Record.*"]}
    assert current["current_secret_id"] == issued.secret_id
    assert issued.secret.startswith("whsec_")
    assert issued.secret not in repr(issued) and issued.secret not in str(issued)
    created = issued.events[0]
    assert created.stream_type == "core.WebhookSubscription"
    assert json.loads(str(current["active_windows_json"])) == [{"from": created.seq, "until": None}]


def test_no_secret_ever_reaches_the_ledger(world: World) -> None:
    issued = world.subscribe()
    with world.factory() as uow:
        rotated = rotate_secret(
            uow, RotateWebhookSecret(subscription_id=issued.subscription_id, **COMMON)
        )
    everything = json.dumps(world.query("SELECT payload FROM events"))
    outbox = json.dumps(world.query("SELECT data_json FROM outbox_events"))
    for secret in (issued.secret, rotated.secret):
        assert secret not in everything and secret not in outbox
        assert secret[6:] not in everything


@pytest.mark.parametrize(
    "kwargs",
    [
        {"url": "ftp://x.test/"},
        {"url": "https://u:p@x.test/"},
        {"url": "not a url"},
        {"mode": "huge"},
        {"filter": {"nope": ["x"]}},
        {"filter": {"event_types": []}},
        {"filter": {"record_selector": "status:"}},
        {"filter": {"transitions": ["InReview"]}},
    ],
)
def test_invalid_subscriptions_are_refused_before_anything_is_written(
    world: World, kwargs: dict[str, object]
) -> None:
    with pytest.raises(InvalidSubscriptionError):
        world.subscribe(**kwargs)  # type: ignore[arg-type]
    assert world.query("SELECT * FROM events") == []
    assert world.query("SELECT * FROM wh_secret") == []


def test_update_changes_only_what_differs_and_validates(world: World) -> None:
    sid = world.subscribe().subscription_id
    with world.factory() as uow:
        update_subscription(
            uow,
            UpdateWebhookSubscription(
                subscription_id=sid,
                changes={"payload_mode": "full", "filter": {"hashtags": ["safety"]}, **{}},
                **COMMON,
            ),
        )
    current = row(world, sid)
    assert current["payload_mode"] == "full"
    assert json.loads(str(current["filter_json"])) == {"hashtags": ["safety"]}
    with world.factory() as uow, pytest.raises(NoChangesError):
        update_subscription(
            uow,
            UpdateWebhookSubscription(
                subscription_id=sid, changes={"payload_mode": "full"}, **COMMON
            ),
        )
    with world.factory() as uow, pytest.raises(InvalidSubscriptionError):
        update_subscription(
            uow, UpdateWebhookSubscription(subscription_id=sid, changes={"owner": "x"}, **COMMON)
        )


def test_disable_and_enable_move_the_delivery_window(world: World) -> None:
    sid = world.subscribe().subscription_id
    with world.factory() as uow:
        disabled = disable_subscription(
            uow, DisableWebhookSubscription(subscription_id=sid, **COMMON)
        )
    current = row(world, sid)
    assert (current["status"], current["disabled_reason"]) == ("disabled", "owner")
    created_seq = world.query("SELECT MIN(seq) AS s FROM events")[0]["s"]
    assert json.loads(str(current["active_windows_json"])) == [
        {"from": created_seq, "until": disabled.events[0].seq}
    ]
    with world.factory() as uow, pytest.raises(AlreadyInStateError):
        disable_subscription(uow, DisableWebhookSubscription(subscription_id=sid, **COMMON))
    with world.factory() as uow:
        enabled = enable_subscription(uow, EnableWebhookSubscription(subscription_id=sid, **COMMON))
    current = row(world, sid)
    assert current["status"] == "active"
    assert json.loads(str(current["active_windows_json"]))[-1] == {
        "from": enabled.events[0].seq,
        "until": None,
    }
    with world.factory() as uow, pytest.raises(AlreadyInStateError):
        enable_subscription(uow, EnableWebhookSubscription(subscription_id=sid, **COMMON))


def test_unknown_subscription_and_wrong_scope_are_not_found(world: World) -> None:
    sid = world.subscribe().subscription_id
    with world.factory() as uow, pytest.raises(SubscriptionNotFoundError):
        enable_subscription(
            uow, EnableWebhookSubscription(subscription_id="01J9Z6Q4W3X2Y1V0T9S8R7Q6ZZ", **COMMON)
        )
    other = {**COMMON, "scope": "project:P2"}
    with world.factory() as uow, pytest.raises(SubscriptionNotFoundError):
        disable_subscription(uow, DisableWebhookSubscription(subscription_id=sid, **other))


def secrets_of(world: World, sid: str) -> list[dict[str, object]]:
    return world.query(
        "SELECT secret_id, state, expires_at FROM wh_secret WHERE subscription_id = :s "
        "ORDER BY created_at, secret_id",
        s=sid,
    )


def test_rotation_keeps_the_old_secret_signing_for_the_overlap_then_retires_it(
    world: World,
) -> None:
    issued = world.subscribe()
    sid = issued.subscription_id
    world.subscribe(url="https://other.test/")  # a second subscription must be unaffected
    world.clock.advance(minutes=1)
    with world.factory() as uow:
        rotated = rotate_secret(
            uow,
            RotateWebhookSecret(subscription_id=sid, overlap_hours=2, **COMMON),
            clock=world.clock,
        )
    assert row(world, sid)["current_secret_id"] == rotated.secret_id
    old, new = secrets_of(world, sid)
    assert old["state"] == "active" and old["expires_at"] is not None
    assert new["state"] == "active" and new["expires_at"] is None
    event = rotated.events[0]
    assert event.payload["previous_secret_id"] == issued.secret_id
    assert event.payload["previous_expires_at"] == old["expires_at"]

    # Both secrets sign during the overlap; only the new one after it.
    world.dispatcher().run_until_idle()
    world.record("P1-ROT")
    world.dispatcher().run_until_idle()
    engine = world.engine()
    engine.run_cycle()
    last = [r for r in world.transport.sent if r.target.host == "hook.test"][-1]
    headers, body = last.headers, last.body
    assert len(headers["webhook-signature"].split()) == 2
    for secret in (issued.secret, rotated.secret):
        verify(headers, body, [SigningSecret(secret)], now=int(world.clock().timestamp()))

    world.clock.advance(hours=3)
    world.record("P1-ROT2")
    world.dispatcher().run_until_idle()
    engine.run_cycle()
    last = [r for r in world.transport.sent if r.target.host == "hook.test"][-1]
    headers = last.headers
    assert len(headers["webhook-signature"].split()) == 1
    verify(
        headers,
        last.body,
        [SigningSecret(rotated.secret)],
        now=int(world.clock().timestamp()),
    )


def test_a_second_rotation_retires_the_secret_that_was_already_expiring(world: World) -> None:
    sid = world.subscribe().subscription_id
    for _ in range(2):
        with world.factory() as uow:
            rotate_secret(
                uow, RotateWebhookSecret(subscription_id=sid, **COMMON), clock=world.clock
            )
        world.clock.advance(minutes=1)
    states = [s["state"] for s in secrets_of(world, sid)]
    assert states == ["retired", "active", "active"]
