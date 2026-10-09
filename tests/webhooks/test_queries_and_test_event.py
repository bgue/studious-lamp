"""Read-only views for the CLI and the catalog-backed test event."""

from __future__ import annotations

import json

import pytest
from tl_core.webhooks import queries
from tl_core.webhooks.delivery import DeliveryEngine
from tl_core.webhooks.egress import EgressPolicy
from tl_core.webhooks.signing import SigningSecret, verify
from world import World

RECORDS = {"event_types": ["Record.*"]}


def test_send_test_posts_a_signed_catalog_sample_and_queues_nothing(world: World) -> None:
    issued = world.subscribe(filter=RECORDS)
    result = world.engine().send_test(issued.subscription_id, "Workflow.Transitioned")
    assert result.ok and result.status == 200
    request = world.transport.sent[0]
    body = json.loads(request.body)
    assert body["type"] == "tl.core.Workflow.Transitioned.v1"
    assert body["id"] == result.event_id == request.headers["webhook-id"]
    assert body["time"].endswith("Z")
    verify(
        request.headers,
        request.body,
        [SigningSecret(issued.secret)],
        now=int(world.clock().timestamp()),
    )
    assert world.query("SELECT * FROM wh_delivery") == []
    assert world.query("SELECT * FROM wh_attempt") == []


def test_send_test_reports_failures_and_blocked_targets(world: World) -> None:
    sid = world.subscribe().subscription_id
    world.transport.default = 503
    failed = world.engine().send_test(sid)
    assert (failed.ok, failed.status, failed.blocked) == (False, 503, False)
    blocked = DeliveryEngine(
        world.factory,
        world.transport,
        egress=EgressPolicy((), lambda host, port: ["10.0.0.1"]),
        clock=world.clock,
    ).send_test(sid)
    assert blocked.blocked and not blocked.ok and blocked.status is None
    with pytest.raises(LookupError):
        world.engine().send_test("01J9Z6Q4W3X2Y1V0T9S8R7Q6ZZ")
    with pytest.raises(KeyError):
        world.engine().send_test(sid, "Nope.Nothing")


def test_listings_show_state_counts_and_never_a_secret(world: World) -> None:
    issued = world.subscribe(filter=RECORDS)
    sid = issued.subscription_id
    rid = world.record("P1-1")
    world.retitle(rid, "two", version=1)
    world.dispatcher().run_until_idle()
    world.transport.script = [410]
    engine = world.engine()
    engine.run_cycle()
    with world.factory(readonly=True) as uow:
        (summary,) = queries.list_subscriptions(uow, SCOPE_P1)
        assert summary["pending"] == 1 and summary["dead"] == 1
        assert summary["filter"] == RECORDS and summary["payload_mode"] == "thin"
        assert queries.get_subscription(uow, sid) == summary
        assert queries.get_subscription(uow, "nope") is None
        dlq = queries.list_dlq(uow, sid)
        assert [d["dead_reason"] for d in dlq] == ["gone"]
        attempts = queries.list_attempts(uow, dlq[0]["delivery_id"])
        assert [(a["attempt"], a["status"], a["outcome"]) for a in attempts] == [(1, 410, "dead")]
        log = queries.list_deliveries(uow, sid)
        assert [d["status"] for d in log] == ["pending", "dead"]
        assert [d["seq"] for d in queries.list_deliveries(uow, sid, status="dead")] == [
            dlq[0]["seq"]
        ]
        assert queries.list_subscriptions(uow, "project:P2") == []
        dump = json.dumps([summary, dlq, attempts, log], default=str)
    assert issued.secret not in dump and "whsec_" not in dump


SCOPE_P1 = "project:P1"
