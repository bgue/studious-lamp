"""Outbox and webhook delivery behave the same on SQLite and Postgres (P0-I5 workstream B)."""

from __future__ import annotations

import json
import threading
from typing import Any

import pytest
from jsonschema import Draft202012Validator
from scenario import run_scenario
from sqlalchemy import text
from tl_adapters.db import rebuild_projections
from tl_core.webhooks import queries
from tl_core.webhooks.rows import OutboxRow, load_json
from tl_core.webhooks.signing import SigningSecret, verify
from tl_core.webhooks.subscriptions import (
    DisableWebhookSubscription,
    EnableWebhookSubscription,
    RotateWebhookSecret,
    UpdateWebhookSubscription,
    disable_subscription,
    enable_subscription,
    rotate_secret,
    update_subscription,
)
from tl_schema import catalog
from world import SCOPE, World

RECORDS = {"event_types": ["Record.*"]}
COMMON: dict[str, Any] = {"actor": "user:alice", "source": "test", "scope": SCOPE}


def outbox(world: World) -> list[OutboxRow]:
    with world.factory(readonly=True) as uow:
        rows = uow.conn().execute(text("SELECT * FROM outbox_events ORDER BY seq")).mappings()
        return [OutboxRow.from_mapping(row) for row in rows]


def states(world: World, sid: str) -> list[str]:
    rows = world.query(
        "SELECT status FROM wh_delivery WHERE subscription_id = :s ORDER BY seq, delivery_id", s=sid
    )
    return [r["status"] for r in rows]


def one_subject(world: World, events: int) -> str:
    rid = world.record("P1-S")
    for version in range(1, events):
        world.retitle(rid, f"title {version}", version=version)
    return rid


def test_the_outbox_row_commits_with_the_event_and_a_rollback_leaves_nothing(
    pworld: World,
) -> None:
    rid = pworld.record("P1-A", title="Gate valve")
    pworld.retitle(rid, "Gate valve 47", version=1)
    first, second = outbox(pworld)
    assert (first.event_type, first.subject_id, first.subject_key) == (
        "Record.Created",
        rid,
        "P1-A",
    )
    assert second.changed_fields == ("title",)
    assert second.data["changes"] == {"title": ["Gate valve", "Gate valve 47"]}
    with pytest.raises(RuntimeError), pworld.factory() as uow:
        uow.append(
            stream_id="S1",
            stream_type="core.Record",
            scope=SCOPE,
            expected_version=0,
            events=[_new({"record_type": "t", "key": "K", "title": "T"})],
            actor="user:a",
            source="test",
            correlation_id="c",
        )
        raise RuntimeError("refuse")
    assert len(outbox(pworld)) == 2


def _new(payload: dict[str, Any]) -> Any:
    from tl_core.ledger import NewEvent

    return NewEvent(event_type="Record.Created", payload=payload)


def test_a_rebuild_reproduces_the_outbox_and_sends_nothing(pworld: World) -> None:
    pworld.subscribe(filter=RECORDS)
    rid = pworld.record("P1-R")
    pworld.retitle(rid, "Renamed", version=1)
    pworld.dispatcher().run_until_idle()
    for _ in range(2):  # one event of the record per cycle
        pworld.engine().run_cycle()
    before = outbox(pworld)
    sent, deliveries = (
        len(pworld.transport.sent),
        pworld.query("SELECT delivery_id FROM wh_delivery"),
    )
    assert rebuild_projections(pworld.path, types=["outbox"]) >= len(before)
    assert outbox(pworld) == before
    pworld.dispatcher().run_until_idle()
    pworld.engine().run_cycle()
    assert len(pworld.transport.sent) == sent
    assert pworld.query("SELECT delivery_id FROM wh_delivery") == deliveries


def test_subjects_are_ordered_retried_and_dead_lettered_then_redriven(pworld: World) -> None:
    sid = pworld.subscribe(filter=RECORDS).subscription_id
    one_subject(pworld, 3)
    dispatcher = pworld.dispatcher()
    dispatcher.run_until_idle()
    pworld.transport.script = [500]
    engine = pworld.engine()
    assert engine.run_cycle().retried == 1
    assert engine.run_cycle().claimed == 0  # backing off: the next event may not overtake
    pworld.clock.advance(seconds=11)
    for _ in range(4):
        engine.run_cycle()
        pworld.clock.advance(seconds=1)
    sent = [json.loads(r.body)["tlseq"] for r in pworld.transport.sent]
    assert sent == [sent[0], sent[0], sent[0] + 1, sent[0] + 2]
    assert states(pworld, sid) == ["delivered"] * 3
    pworld.transport.script = [410]
    pworld.record("P1-GONE")
    dispatcher.run_until_idle()
    assert engine.run_cycle().dead == 1
    assert dispatcher.redrive(sid) == 1
    assert engine.run_cycle().delivered == 1
    assert sorted(states(pworld, sid)) == ["delivered"] * 4 + ["redriven"]
    with pworld.factory(readonly=True) as uow:
        assert queries.list_dlq(uow, sid) == []


def test_concurrent_workers_never_hold_the_same_delivery(pworld: World) -> None:
    pworld.subscribe(filter=RECORDS)
    for n in range(12):
        pworld.record(f"P1-{n}")
    pworld.dispatcher().run_until_idle()
    engines = [pworld.engine(worker_id=f"w{n}") for n in range(4)]
    taken: list[list[str]] = [[] for _ in engines]

    def grab(index: int) -> None:
        taken[index] = [c.delivery_id for c in engines[index].claim(limit=12)]

    threads = [threading.Thread(target=grab, args=(n,), daemon=True) for n in range(4)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=30)
    flat = [d for chunk in taken for d in chunk]
    assert len(flat) == 12 and len(set(flat)) == 12


def test_auto_disable_writes_an_event_and_stops_claims(pworld: World) -> None:
    from tl_core.webhooks.retry import HealthPolicy

    pworld.subscribe(filter=RECORDS)
    one_subject(pworld, 5)
    pworld.dispatcher().run_until_idle()
    pworld.transport.default = 410
    engine = pworld.engine(health=HealthPolicy(max_consecutive_dead=3, max_failing_hours=1000))
    assert sum(engine.run_cycle().disabled for _ in range(3)) == 1
    row = pworld.query("SELECT status, disabled_reason FROM cur_webhook_subscription")[0]
    assert (row["status"], row["disabled_reason"]) == ("disabled", "sustained_failure")
    assert engine.claim() == []


def test_subscription_lifecycle_windows_and_secret_rotation(pworld: World) -> None:
    issued = pworld.subscribe(filter=RECORDS, mode="delta")
    sid = issued.subscription_id
    dispatcher = pworld.dispatcher()
    pworld.record("P1-1")
    with pworld.factory() as uow:
        update_subscription(
            uow, UpdateWebhookSubscription(subscription_id=sid, changes={"name": "n2"}, **COMMON)
        )
        rotated = rotate_secret(
            uow,
            RotateWebhookSecret(subscription_id=sid, overlap_hours=2, **COMMON),
            clock=pworld.clock,
        )
        disable_subscription(uow, DisableWebhookSubscription(subscription_id=sid, **COMMON))
    pworld.record("P1-2")
    with pworld.factory() as uow:
        enable_subscription(uow, EnableWebhookSubscription(subscription_id=sid, **COMMON))
    pworld.record("P1-3")
    dispatcher.run_until_idle()
    keys = [
        json.loads(r["body"])["data"]["origin"]["key"]
        for r in pworld.query("SELECT body FROM wh_delivery ORDER BY seq")
    ]
    assert keys == ["P1-1", "P1-3"]  # a late pass still honours the windows
    pworld.engine().run_cycle(limit=10)
    request = pworld.transport.sent[0]
    assert len(request.headers["webhook-signature"].split()) == 2
    for secret in (issued.secret, rotated.secret):
        verify(
            request.headers,
            request.body,
            [SigningSecret(secret)],
            now=int(pworld.clock().timestamp()),
        )
    with pworld.factory(readonly=True) as uow:
        (summary,) = queries.list_subscriptions(uow)
    assert summary["name"] == "n2" and summary["filter"] == RECORDS
    assert issued.secret not in json.dumps(pworld.query("SELECT payload FROM events"), default=str)


def test_replay_and_record_selector(pworld: World) -> None:
    sid = pworld.subscribe(filter={**RECORDS, "record_selector": "title~gate"}).subscription_id
    a, b = pworld.record("P1-A", title="Gate valve"), pworld.record("P1-B", title="Pump")
    dispatcher = pworld.dispatcher()
    dispatcher.run_until_idle()
    rows = pworld.query("SELECT seq FROM wh_delivery")
    assert len(rows) == 1 and a != b
    assert dispatcher.replay(sid, 1, 999) == 1
    assert len(pworld.query("SELECT * FROM wh_delivery WHERE origin = 'replay'")) == 1


def test_a_test_send_and_the_attempt_log(pworld: World) -> None:
    sid = pworld.subscribe(filter=RECORDS).subscription_id
    assert pworld.engine().send_test(sid).ok
    assert pworld.transport.sent[0].headers["webhook-test"] == "1"
    pworld.record("P1-1")
    pworld.dispatcher().run_until_idle()
    pworld.engine().run_cycle()
    with pworld.factory(readonly=True) as uow:
        log = queries.list_deliveries(uow, sid)
        attempts = queries.list_attempts(uow, log[0]["delivery_id"])
    assert [a["outcome"] for a in attempts] == ["delivered"]
    assert load_json(json.dumps(log[0]["status"])) == "delivered"


def test_every_catalog_event_type_is_delivered_and_valid(pworld: World) -> None:
    delivered = run_scenario(pworld)
    seen = set()
    for bodies in delivered.values():
        for body in bodies:
            event_type = body["type"].removeprefix("tl.core.").rsplit(".v", 1)[0]
            schema = catalog.envelope_schema(event_type)
            checker = Draft202012Validator(
                schema, format_checker=Draft202012Validator.FORMAT_CHECKER
            )
            errors = list(checker.iter_errors(body))
            assert not errors, (event_type, errors[0].message)
            seen.add(event_type)
    assert seen == set(catalog.event_types())


def test_make_uow_factory_gives_the_adapters_factory_with_one_call_shape(pworld: World) -> None:
    from tl_adapters.db import is_postgres, make_uow_factory
    from tl_adapters.postgres.factory import PostgresUowFactory
    from tl_adapters.sqlite.factory import SqliteUowFactory

    other = make_uow_factory(pworld.path)
    try:
        assert isinstance(
            other, PostgresUowFactory if is_postgres(pworld.path) else SqliteUowFactory
        )
        with other(readonly=True) as uow:
            assert uow.conn().execute(text("SELECT COUNT(*) FROM events")).scalar_one() == 0
    finally:
        other.dispose()
