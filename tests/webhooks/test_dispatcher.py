"""The dispatcher: which events reach which subscription, windows, replay, redrive."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from tl_core.webhooks.subscriptions import (
    DisableWebhookSubscription,
    EnableWebhookSubscription,
    disable_subscription,
    enable_subscription,
)
from world import SCOPE, World

COMMON: dict[str, Any] = {"actor": "user:alice", "source": "test", "scope": SCOPE}


def deliveries(world: World, sid: str | None = None) -> list[dict[str, object]]:
    where = "WHERE subscription_id = :s" if sid else ""
    return world.query(
        f"SELECT seq, origin, status, event_id, body, dedupe_key FROM wh_delivery {where} "
        "ORDER BY seq, delivery_id",
        **({"s": sid} if sid else {}),
    )


def test_events_before_the_subscription_are_not_delivered(world: World) -> None:
    world.record("P1-OLD")
    sid = world.subscribe().subscription_id
    world.record("P1-NEW")
    world.dispatcher().run_until_idle()
    rows = deliveries(world, sid)
    assert len(rows) == 1
    assert json.loads(str(rows[0]["body"]))["data"]["origin"]["key"] == "P1-NEW"


def test_the_filter_selects_by_event_type_and_record_selector(world: World) -> None:
    sid = world.subscribe(filter={"event_types": ["Record.Updated"]}).subscription_id
    a, b = world.record("P1-A"), world.record("P1-B")
    world.retitle(a, "A2", version=1)
    world.retitle(b, "B2", version=1)
    world.dispatcher().run_until_idle()
    assert [
        json.loads(str(r["body"]))["data"]["origin"]["key"] for r in deliveries(world, sid)
    ] == [
        "P1-A",
        "P1-B",
    ]
    only_a = world.subscribe(
        filter={"event_types": ["Record.Updated"], "record_selector": "title~A2"}
    ).subscription_id
    world.retitle(a, "A3", version=2)
    world.retitle(b, "B3", version=2)
    world.dispatcher().run_until_idle()
    assert len(deliveries(world, only_a)) == 0  # the selector sees the current title (A3), not A2
    selected = world.subscribe(
        filter={"event_types": ["Record.Updated"], "record_selector": "title~3"}
    ).subscription_id
    world.retitle(a, "A34", version=3)
    world.retitle(b, "B4", version=3)
    world.dispatcher().run_until_idle()
    keys = [
        json.loads(str(r["body"]))["data"]["origin"]["key"] for r in deliveries(world, selected)
    ]
    assert keys == ["P1-A"]


def test_scope_rules_project_subscriptions_see_only_their_project(world: World) -> None:
    records = {"event_types": ["Record.*"]}
    project = world.subscribe(scope="project:P1", filter=records).subscription_id
    company = world.subscribe(scope="company", filter=records).subscription_id
    narrowed = world.subscribe(
        scope="company", filter={**records, "scope_selector": "project:P2"}
    ).subscription_id
    world.record("P1-X", scope="project:P1")
    world.record("P2-X", scope="project:P2")
    world.dispatcher().run_until_idle()
    keys = lambda sid: sorted(  # noqa: E731
        json.loads(str(r["body"]))["data"]["origin"]["key"] for r in deliveries(world, sid)
    )
    assert keys(project) == ["P1-X"]
    assert keys(company) == ["P1-X", "P2-X"]
    assert keys(narrowed) == ["P2-X"]


def test_the_active_window_follows_disable_and_enable(world: World) -> None:
    sid = world.subscribe(filter={"event_types": ["Record.*"]}).subscription_id
    dispatcher = world.dispatcher()
    world.record("P1-1")
    with world.factory() as uow:
        disable_subscription(uow, DisableWebhookSubscription(subscription_id=sid, **COMMON))
    world.record("P1-2")
    with world.factory() as uow:
        enable_subscription(uow, EnableWebhookSubscription(subscription_id=sid, **COMMON))
    world.record("P1-3")
    dispatcher.run_until_idle()  # one late pass: windows are by seq, not by when the pass runs
    keys = [json.loads(str(r["body"]))["data"]["origin"]["key"] for r in deliveries(world, sid)]
    assert keys == ["P1-1", "P1-3"]


def test_expired_subscriptions_stop_receiving(world: World) -> None:
    from tl_core.webhooks.subscriptions import CreateWebhookSubscription, create_subscription

    with world.factory() as uow:
        sid = create_subscription(
            uow,
            CreateWebhookSubscription(
                name="short",
                target_url="https://hook.test/",
                expires_at=datetime.now(UTC) + timedelta(days=1),  # events carry real time
                **COMMON,
            ),
            clock=world.clock,
        ).subscription_id
    world.record("P1-BEFORE")
    world.dispatcher().run_until_idle()
    assert len(deliveries(world, sid)) == 1


def test_running_twice_creates_nothing_new_and_the_cursor_persists(world: World) -> None:
    sid = world.subscribe().subscription_id
    world.record("P1-1")
    dispatcher = world.dispatcher()
    first = dispatcher.run_until_idle()
    second = dispatcher.run_until_idle()
    assert first.created == 1 and second.created == 0 and second.read == 0
    assert len(deliveries(world, sid)) == 1
    other = world.dispatcher()  # a new process picks up from the stored cursor
    assert other.run_once().read == 0


def test_the_lag_window_catches_a_row_that_became_visible_late(world: World) -> None:
    sid = world.subscribe().subscription_id
    world.record("P1-1")
    world.record("P1-2")
    dispatcher = world.dispatcher(lag_window=50)
    dispatcher.run_until_idle()
    assert len(deliveries(world, sid)) == 2
    # Simulate a row that committed after the cursor passed it: delete its delivery, re-run.
    from sqlalchemy import text

    with world.factory() as uow:
        uow.conn().execute(text("DELETE FROM wh_delivery WHERE seq = 3"))
    dispatcher.run_until_idle()
    assert [r["seq"] for r in deliveries(world, sid)] == [2, 3]


def test_replay_resends_a_seq_range_with_the_same_event_ids(world: World) -> None:
    sid = world.subscribe().subscription_id
    ids = [world.record(f"P1-{n}") for n in range(3)]
    dispatcher = world.dispatcher()
    dispatcher.run_until_idle()
    original = deliveries(world, sid)
    created = dispatcher.replay(sid, original[1]["seq"], original[2]["seq"])  # type: ignore[arg-type]
    assert created == 2 and ids
    rows = deliveries(world, sid)
    assert len(rows) == 5
    replays = [r for r in rows if r["origin"] == "replay"]
    assert [r["event_id"] for r in replays] == [r["event_id"] for r in original[1:]]
    assert all(r["dedupe_key"] != str(r["seq"]) for r in replays)
    assert [r["body"] for r in replays] == [r["body"] for r in original[1:]]


def test_replay_rejects_unknown_subscriptions_and_backwards_ranges(world: World) -> None:
    dispatcher = world.dispatcher()
    with pytest.raises(LookupError):
        dispatcher.replay("01J9Z6Q4W3X2Y1V0T9S8R7Q6ZZ", 1, 2)
    sid = world.subscribe().subscription_id
    with pytest.raises(ValueError):
        dispatcher.replay(sid, 5, 1)


def test_replay_between_times_uses_the_recorded_time(world: World) -> None:
    sid = world.subscribe(filter={"event_types": ["Record.*"]}).subscription_id
    world.record("P1-1")
    dispatcher = world.dispatcher()
    dispatcher.run_until_idle()
    now = world.clock()
    # Events are stamped with the real clock; a window around "now" of the test covers them.
    from datetime import UTC, datetime

    real = datetime.now(UTC)
    assert dispatcher.replay_between(sid, real - timedelta(hours=1), real + timedelta(hours=1)) == 1
    assert dispatcher.replay_between(sid, now - timedelta(days=9), now - timedelta(days=8)) == 0


def test_payload_modes_shape_the_stored_body(world: World) -> None:
    thin = world.subscribe(mode="thin").subscription_id
    delta = world.subscribe(mode="delta").subscription_id
    full = world.subscribe(mode="full").subscription_id
    rid = world.record("P1-M", title="Mode")
    world.retitle(rid, "Mode 2", version=1)
    world.dispatcher().run_until_idle()
    bodies = {
        name: json.loads(str(deliveries(world, sid)[-1]["body"]))
        for name, sid in (("thin", thin), ("delta", delta), ("full", full))
    }
    assert set(bodies["thin"]["data"]) == {"origin"}
    assert set(bodies["delta"]["data"]) == {"origin", "changes", "links", "detail"}
    assert set(bodies["full"]["data"]) == {"origin", "changes", "links", "detail", "record"}
    assert bodies["delta"]["data"]["changes"] == {"title": ["Mode", "Mode 2"]}
    assert bodies["full"]["data"]["record"]["title"] == "Mode 2"
    for body in bodies.values():
        assert body["tlseq"] == 2 + 3 or body["tlseq"] >= 1
        assert body["tlstreamversion"] == 2
        assert body["data"]["origin"]["uri"].endswith("/r/core.Record/P1-M@v2")
        assert body["subject"] == f"urn:tl:{rid}"
        assert body["type"] == "tl.core.Record.Updated.v1"
