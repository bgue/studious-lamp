"""The delivery engine: signing on the wire, ordering per subject, retries, DLQ, health."""

from __future__ import annotations

import json
import threading

import pytest
from tl_core.webhooks.delivery import DeliveryEngine
from tl_core.webhooks.egress import EgressPolicy
from tl_core.webhooks.retry import HealthPolicy, RetryPolicy
from tl_core.webhooks.signing import SigningSecret, verify
from tl_core.webhooks.transport import TransportResult
from world import World

RECORDS = {"event_types": ["Record.*"]}


def status_of(world: World, sid: str) -> list[tuple[int, str, int]]:
    rows = world.query(
        "SELECT seq, status, attempts FROM wh_delivery WHERE subscription_id = :s "
        "ORDER BY seq, delivery_id",
        s=sid,
    )
    return [(r["seq"], r["status"], r["attempts"]) for r in rows]


def one_subject(world: World, events: int) -> str:
    """One record with ``events`` events (create plus retitles): one ordered queue."""
    rid = world.record("P1-S")
    for version in range(1, events):
        world.retitle(rid, f"title {version}", version=version)
    return rid


def prepare(world: World, *, mode: str = "thin") -> str:
    sid = world.subscribe(filter=RECORDS, mode=mode).subscription_id
    return sid


# --- what goes on the wire ---


def test_a_delivery_is_signed_with_standard_webhooks_headers_and_verifies(world: World) -> None:
    issued = world.subscribe(filter=RECORDS, mode="delta")
    rid = world.record("P1-1")
    world.dispatcher().run_until_idle()
    stats = world.engine().run_cycle()
    assert (stats.claimed, stats.delivered) == (1, 1)
    request = world.transport.sent[0]
    event = world.query("SELECT event_id, seq FROM events WHERE stream_id = :s", s=rid)[0]
    headers = request.headers
    assert headers["webhook-id"] == event["event_id"]
    assert headers["Content-Type"] == "application/json"
    assert (
        verify(
            headers,
            request.body,
            [SigningSecret(issued.secret)],
            now=int(world.clock().timestamp()),
        )
        == event["event_id"]
    )
    body = json.loads(request.body)
    assert body["id"] == event["event_id"] and body["tlseq"] == event["seq"]
    assert body["specversion"] == "1.0"
    assert (request.target.host, request.target.ip) == ("hook.test", "93.184.216.34")
    assert world.resolver_calls == ["hook.test"]  # resolved once for the one attempt


def test_the_secret_never_appears_in_attempt_rows_or_delivery_rows(world: World) -> None:
    issued = world.subscribe(filter=RECORDS)
    world.record("P1-1")
    world.dispatcher().run_until_idle()
    world.transport.default = 500
    world.engine().run_cycle()
    dump = json.dumps(
        [world.query(f"SELECT * FROM {t}") for t in ("wh_attempt", "wh_delivery", "wh_health")]
    )
    assert issued.secret not in dump and issued.secret[6:] not in dump


def test_a_success_marks_delivered_and_logs_the_attempt(world: World) -> None:
    sid = prepare(world)
    world.record("P1-1")
    world.dispatcher().run_until_idle()
    world.engine().run_cycle()
    assert status_of(world, sid) == [(2, "delivered", 1)]
    attempt = world.query("SELECT * FROM wh_attempt")[0]
    assert (attempt["attempt"], attempt["status"], attempt["outcome"]) == (1, 200, "delivered")
    health = world.query("SELECT * FROM wh_health")[0]
    assert (health["delivered_total"], health["consecutive_dead"], health["failing_since"]) == (
        1,
        0,
        None,
    )


# --- ordering ---


def test_event_n_plus_one_of_a_subject_waits_for_event_n(world: World) -> None:
    sid = prepare(world)
    rid = world.record("P1-1")
    world.retitle(rid, "two", version=1)
    world.retitle(rid, "three", version=2)
    world.dispatcher().run_until_idle()
    world.transport.script = [500]
    engine = world.engine()
    first = engine.run_cycle(limit=10)
    assert (first.claimed, first.retried) == (1, 1)  # only the head was claimed
    assert status_of(world, sid) == [(2, "pending", 1), (3, "pending", 0), (4, "pending", 0)]
    assert engine.run_cycle().claimed == 0  # still backing off: nothing may overtake it
    world.clock.advance(seconds=11)
    seqs = []
    for _ in range(3):
        engine.run_cycle(limit=10)
        seqs = [json.loads(r.body)["tlseq"] for r in world.transport.sent]
        world.clock.advance(seconds=1)
    assert seqs == [2, 2, 3, 4]
    assert [s for _, s, _ in status_of(world, sid)] == ["delivered"] * 3


def test_different_subjects_are_claimed_together(world: World) -> None:
    prepare(world)
    for n in range(3):
        world.record(f"P1-{n}")
    world.dispatcher().run_until_idle()
    claims = world.engine().claim(limit=10)
    assert len({c.subject_id for c in claims}) == 3


def test_a_dead_letter_unblocks_the_next_event_of_the_subject(world: World) -> None:
    sid = prepare(world)
    rid = world.record("P1-1")
    world.retitle(rid, "two", version=1)
    world.dispatcher().run_until_idle()
    world.transport.script = [410]  # the first event is refused for good
    engine = world.engine()
    engine.run_cycle()
    assert [s for _, s, _ in status_of(world, sid)] == ["dead", "pending"]
    engine.run_cycle()
    assert [s for _, s, _ in status_of(world, sid)] == ["dead", "delivered"]


def test_ordering_is_per_subscription_not_global(world: World) -> None:
    a = prepare(world)
    b = world.subscribe(filter=RECORDS, url="https://other.test/").subscription_id
    rid = world.record("P1-1")
    world.retitle(rid, "two", version=1)
    world.dispatcher().run_until_idle()

    def responder(request):  # type: ignore[no-untyped-def]
        if request.target.host == "hook.test":
            return TransportResult(status=500, latency_ms=1)
        return TransportResult(status=200, latency_ms=1)

    world.transport.responder = responder
    engine = world.engine()
    for _ in range(3):
        engine.run_cycle()
    assert [s for _, s, _ in status_of(world, b)] == ["delivered", "delivered"]
    assert [s for _, s, _ in status_of(world, a)] == ["pending", "pending"]


def test_a_replay_row_is_ordered_by_seq_with_the_rest_of_its_subject(world: World) -> None:
    sid = prepare(world)
    rid = world.record("P1-1")
    world.retitle(rid, "two", version=1)
    dispatcher = world.dispatcher()
    dispatcher.run_until_idle()
    engine = world.engine()
    engine.run_cycle()
    engine.run_cycle()
    assert [s for _, s, _ in status_of(world, sid)] == ["delivered", "delivered"]
    dispatcher.replay(sid, 1, 100)
    engine.run_cycle(limit=10)
    engine.run_cycle(limit=10)
    sent = [json.loads(r.body)["tlseq"] for r in world.transport.sent]
    assert sent == [2, 3, 2, 3]
    assert [r.headers["webhook-id"] for r in world.transport.sent[:2]] == [
        r.headers["webhook-id"] for r in world.transport.sent[2:]
    ]


# --- leases ---


def test_two_workers_never_hold_the_same_delivery(world: World) -> None:
    prepare(world)
    world.record("P1-1")
    world.dispatcher().run_until_idle()
    one, two = world.engine(worker_id="a"), world.engine(worker_id="b")
    first = one.claim()
    assert two.claim() == []
    assert len(first) == 1
    # A crashed worker's lease expires and the row is taken over.
    world.clock.advance(seconds=61)
    taken = two.claim()
    assert [c.delivery_id for c in taken] == [c.delivery_id for c in first]
    # The old owner can no longer settle it.
    lost = one.settle(first[0], one.attempt(first[0]))
    assert lost.state == "lost"
    assert two.settle(taken[0], two.attempt(taken[0])).state == "delivered"


def test_concurrent_claims_from_threads_hand_each_delivery_to_one_worker(world: World) -> None:
    prepare(world)
    for n in range(12):
        world.record(f"P1-{n}")
    world.dispatcher().run_until_idle()
    engines = [world.engine(worker_id=f"w{n}") for n in range(4)]
    taken: list[list[str]] = [[] for _ in engines]

    def run(index: int) -> None:
        taken[index] = [c.delivery_id for c in engines[index].claim(limit=12)]

    threads = [threading.Thread(target=run, args=(n,), daemon=True) for n in range(4)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=20)
    flat = [d for chunk in taken for d in chunk]
    assert len(flat) == 12 and len(set(flat)) == 12


# --- retries and the DLQ ---


def test_failures_back_off_then_succeed_and_the_body_never_changes(world: World) -> None:
    sid = prepare(world)
    world.record("P1-1")
    world.dispatcher().run_until_idle()
    world.transport.script = [500, 503]
    engine = world.engine()
    for _ in range(3):
        engine.run_cycle()
        world.clock.advance(seconds=300)
    assert status_of(world, sid) == [(2, "delivered", 3)]
    bodies = {r.body for r in world.transport.sent}
    assert len(world.transport.sent) == 3 and len(bodies) == 1
    stamps = [r.headers["webhook-timestamp"] for r in world.transport.sent]
    assert stamps == sorted(stamps) and len(set(stamps)) == 3  # signed afresh each attempt
    outcomes = [
        a["outcome"] for a in world.query("SELECT outcome FROM wh_attempt ORDER BY attempt")
    ]
    assert outcomes == ["retry", "retry", "delivered"]
    health = world.query("SELECT * FROM wh_health")[0]
    assert health["failing_since"] is None and health["failed_total"] == 2


def test_the_retry_window_ends_in_the_dlq_and_the_last_error_is_kept(world: World) -> None:
    sid = prepare(world)
    world.record("P1-1")
    world.dispatcher().run_until_idle()
    world.transport.default = 500
    engine = world.engine(retry=RetryPolicy(max_hours=1, base_s=600, max_delay_s=1200, jitter=0))
    cycles = 0
    while cycles < 20:
        engine.run_cycle()
        row = world.query("SELECT status FROM wh_delivery")[0]
        if row["status"] == "dead":
            break
        world.clock.advance(seconds=1300)
        cycles += 1
    dead = world.query("SELECT * FROM wh_delivery")[0]
    assert dead["status"] == "dead" and dead["dead_reason"] == "retries_exhausted"
    assert (
        dead["last_status"] == 500 and dead["dead_at"] is not None and dead["lease_owner"] is None
    )
    assert status_of(world, sid)[0][1] == "dead"
    assert dead["attempts"] >= 2


def test_gone_is_dead_at_once(world: World) -> None:
    prepare(world)
    world.record("P1-1")
    world.dispatcher().run_until_idle()
    world.transport.script = [410]
    settled = world.engine().deliver(world.engine().claim()[0])
    assert (settled.state, settled.dead_reason) == ("dead", "gone")


def test_retry_after_is_honoured(world: World) -> None:
    prepare(world)
    world.record("P1-1")
    world.dispatcher().run_until_idle()
    world.transport.script = [TransportResult(status=429, latency_ms=1, retry_after_s=500)]
    engine = world.engine(retry=RetryPolicy(base_s=1, jitter=0, max_delay_s=3600))
    settled = engine.deliver(engine.claim()[0])
    assert settled.next_attempt_at is not None
    assert (settled.next_attempt_at - world.clock()).total_seconds() == pytest.approx(500)


def test_a_blocked_target_is_dead_lettered_without_any_request(world: World) -> None:
    sid = world.subscribe(filter=RECORDS, url="https://internal.test/").subscription_id
    world.record("P1-1")
    world.dispatcher().run_until_idle()
    engine = DeliveryEngine(
        world.factory,
        world.transport,
        egress=EgressPolicy((), lambda host, port: ["10.0.0.7"]),
        clock=world.clock,
        worker_id="w",
    )
    settled = engine.deliver(engine.claim()[0])
    assert (settled.state, settled.dead_reason) == ("dead", "egress_denied")
    assert world.transport.sent == []
    assert status_of(world, sid)[0][1] == "dead"


def test_an_unresolvable_host_is_retried_not_dead(world: World) -> None:
    from tl_core.webhooks.egress import ResolutionFailed

    def nxdomain(host: str, port: int) -> list[str]:
        raise ResolutionFailed(host)

    prepare(world)
    world.record("P1-1")
    world.dispatcher().run_until_idle()
    engine = DeliveryEngine(
        world.factory, world.transport, egress=EgressPolicy((), nxdomain), clock=world.clock
    )
    assert engine.deliver(engine.claim()[0]).state == "retry"


def test_redrive_re_enqueues_dead_letters_and_keeps_the_history(world: World) -> None:
    sid = prepare(world)
    world.record("P1-1")
    dispatcher = world.dispatcher()
    dispatcher.run_until_idle()
    world.transport.script = [410]
    engine = world.engine()
    engine.run_cycle()
    assert dispatcher.redrive(sid, ["01J9Z6Q4W3X2Y1V0T9S8R7Q6ZZ"]) == 0
    assert dispatcher.redrive(sid) == 1
    rows = world.query(
        "SELECT status, origin, replay_of FROM wh_delivery ORDER BY created_at, origin"
    )
    assert sorted((r["status"], r["origin"]) for r in rows) == [
        ("pending", "redrive"),
        ("redriven", "live"),
    ]
    engine.run_cycle()
    assert sorted(s for _, s, _ in status_of(world, sid)) == ["delivered", "redriven"]
    assert dispatcher.redrive(sid) == 0


# --- health and auto-disable ---


def test_sustained_failure_disables_the_subscription_with_an_audit_event(world: World) -> None:
    prepare(world)
    one_subject(world, 5)
    world.dispatcher().run_until_idle()
    world.transport.default = 410
    engine = world.engine(health=HealthPolicy(max_consecutive_dead=3, max_failing_hours=1000))
    results = [engine.run_cycle(limit=10) for _ in range(3)]
    assert sum(r.disabled for r in results) == 1
    row = world.query("SELECT status, disabled_reason FROM cur_webhook_subscription")[0]
    assert (row["status"], row["disabled_reason"]) == ("disabled", "sustained_failure")
    event = world.query(
        "SELECT payload, actor FROM events WHERE event_type = 'WebhookSubscription.Disabled'"
    )[0]
    assert json.loads(event["payload"])["reason"] == "sustained_failure"
    assert event["actor"] == "svc:webhooks"
    # A disabled subscription is not claimed any more.
    world.clock.advance(hours=1)
    assert engine.claim() == []
    assert any(d["status"] == "pending" for d in world.query("SELECT status FROM wh_delivery"))


def test_a_success_resets_the_dead_letter_count(world: World) -> None:
    prepare(world)
    one_subject(world, 5)
    world.dispatcher().run_until_idle()
    engine = world.engine(health=HealthPolicy(max_consecutive_dead=3, max_failing_hours=1000))
    world.transport.script = [410, 410, 200, 410, 410]
    for _ in range(5):
        engine.run_cycle(limit=10)
    row = world.query("SELECT status FROM cur_webhook_subscription")[0]
    assert row["status"] == "active"
    health = world.query("SELECT consecutive_dead FROM wh_health")[0]
    assert health["consecutive_dead"] == 2


def test_failing_for_too_long_disables_even_without_dead_letters(world: World) -> None:
    prepare(world)
    world.record("P1-1")
    world.dispatcher().run_until_idle()
    world.transport.default = 500
    engine = world.engine(
        retry=RetryPolicy(max_hours=500, base_s=3600, max_delay_s=3600, jitter=0),
        health=HealthPolicy(max_consecutive_dead=99, max_failing_hours=5),
    )
    for _ in range(8):
        engine.run_cycle()
        world.clock.advance(hours=1, seconds=1)
    assert world.query("SELECT status FROM cur_webhook_subscription")[0]["status"] == "disabled"
