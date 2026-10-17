"""The claim queue on both databases: claims, leases, idempotent completion, retries (ADR-0014)."""

from __future__ import annotations

import threading
from typing import Any

import pytest
from jobsworld import SCOPE, Clock, World
from tl_adapters.queue import (
    POSTGRES_CLAIM_LOCK,
    PostgresJobQueue,
    SqliteJobQueue,
    job_queue_for,
    job_queue_for_dialect,
)
from tl_core.jobs import JobQueue


def test_a_new_job_is_queued_with_no_attempt(world: World) -> None:
    world.enqueue("J1", max_attempts=2, priority=3)
    row = world.row("J1")
    assert (row.state, row.attempt, row.max_attempts, row.priority) == ("queued", 0, 2, 3)
    assert row.scope == SCOPE and row.lease_owner is None and row.finished_at is None


def test_a_claim_leases_the_job_to_one_worker_for_attempt_one(world: World) -> None:
    world.enqueue("J1")
    claim = world.claim("w1", lease_s=60)
    assert claim is not None
    assert (claim.job_id, claim.attempt, claim.owner, claim.max_attempts) == ("J1", 1, "w1", 3)
    row = world.row("J1")
    assert (row.state, row.attempt, row.lease_owner) == ("running", 1, "w1")
    assert row.lease_until == claim.lease_until and row.started_at is not None
    assert world.claim("w2") is None  # nothing else is claimable


def test_claims_go_by_priority_then_by_time(world: World, clock: Clock) -> None:
    world.enqueue("A")
    clock.advance(seconds=1)
    world.enqueue("B")
    clock.advance(seconds=1)
    world.enqueue("C", priority=5)
    clock.advance(seconds=1)
    order = []
    for _ in range(3):
        claim = world.claim()
        assert claim is not None
        order.append(claim.job_id)
    assert order == ["C", "A", "B"]


def test_a_job_is_not_claimable_before_its_run_after(world: World, clock: Clock) -> None:
    from datetime import timedelta

    world.enqueue("J1", run_after=clock() + timedelta(seconds=30))
    assert world.claim() is None
    clock.advance(seconds=31)
    claim = world.claim()
    assert claim is not None and claim.job_id == "J1"


def test_the_claim_filters_by_kind_and_scope(world: World) -> None:
    world.enqueue("X1", kind="extract", scope="project:P1")
    world.enqueue("V1", kind="validate", scope="project:P2")
    assert world.claim(kinds=["nothing"]) is None
    only_p2 = world.claim(scope="project:P2")
    assert only_p2 is not None and only_p2.job_id == "V1"
    only_extract = world.claim(kinds=["extract", "other"])
    assert only_extract is not None and only_extract.job_id == "X1"


def test_completion_is_idempotent_on_job_and_attempt(world: World, clock: Clock) -> None:
    world.enqueue("J1")
    claim = world.claim()
    assert claim is not None
    with world.factory() as uow:
        assert world.queue.complete(uow.conn(), claim, now=clock()) == "done"
    with world.factory() as uow:
        assert world.queue.complete(uow.conn(), claim, now=clock()) == "already"
    row = world.row("J1")
    assert row.state == "done" and row.finished_at is not None and row.lease_until is None


def test_a_claim_that_is_not_the_current_one_cannot_complete(world: World, clock: Clock) -> None:
    from dataclasses import replace

    world.enqueue("J1")
    claim = world.claim("w1")
    assert claim is not None
    with world.factory() as uow:
        assert world.queue.complete(uow.conn(), replace(claim, owner="w2"), now=clock()) == "lost"
        assert world.queue.complete(uow.conn(), replace(claim, attempt=2), now=clock()) == "lost"
    assert world.row("J1").state == "running"


def test_a_lease_that_ran_out_lets_another_worker_take_the_job(world: World, clock: Clock) -> None:
    world.enqueue("J1")
    first = world.claim("w1", lease_s=60)
    assert first is not None
    assert world.claim("w2") is None  # the lease is still good
    clock.advance(seconds=61)
    second = world.claim("w2", lease_s=60)
    assert second is not None and (second.attempt, second.owner) == (2, "w2")
    # the first worker finishes late: it must write nothing
    with world.factory() as uow:
        assert world.queue.complete(uow.conn(), first, now=clock()) == "lost"
    with world.factory() as uow:
        assert world.queue.complete(uow.conn(), second, now=clock()) == "done"
    row = world.row("J1")
    assert (row.state, row.attempt, row.lease_owner) == ("done", 2, "w2")


def test_a_late_completion_before_anyone_took_over_is_accepted(world: World, clock: Clock) -> None:
    world.enqueue("J1")
    claim = world.claim("w1", lease_s=60)
    assert claim is not None
    clock.advance(seconds=120)  # the lease ran out but nobody claimed it
    with world.factory() as uow:
        assert world.queue.complete(uow.conn(), claim, now=clock()) == "done"


def test_extending_a_lease_keeps_the_job(world: World, clock: Clock) -> None:
    world.enqueue("J1")
    claim = world.claim("w1", lease_s=60)
    assert claim is not None
    clock.advance(seconds=50)
    with world.factory() as uow:
        assert world.queue.extend(uow.conn(), claim, now=clock(), lease_s=60) is True
    clock.advance(seconds=30)  # past the first lease, inside the extended one
    assert world.claim("w2") is None
    clock.advance(seconds=40)
    with world.factory() as uow:
        assert world.queue.extend(uow.conn(), claim, now=clock(), lease_s=60) is True  # still ours
    clock.advance(seconds=100)
    taken = world.claim("w2")
    assert taken is not None
    with world.factory() as uow:
        assert world.queue.extend(uow.conn(), claim, now=clock(), lease_s=60) is False


def test_a_failed_attempt_is_queued_again_after_the_delay(world: World, clock: Clock) -> None:
    world.enqueue("J1")
    claim = world.claim()
    assert claim is not None
    with world.factory() as uow:
        outcome = world.queue.fail(uow.conn(), claim, now=clock(), error="boom", retry_delay_s=30)
    assert outcome == "retry"
    row = world.row("J1")
    assert (row.state, row.last_error, row.lease_owner) == ("queued", "boom", None)
    assert world.claim() is None
    clock.advance(seconds=31)
    again = world.claim()
    assert again is not None and again.attempt == 2
    assert world.row("J1").last_error is None  # a new claim clears the old error


def test_the_last_attempt_fails_for_good(world: World, clock: Clock) -> None:
    world.enqueue("J1", max_attempts=2)
    for number in (1, 2):
        claim = world.claim()
        assert claim is not None and claim.attempt == number
        with world.factory() as uow:
            outcome = world.queue.fail(
                uow.conn(), claim, now=clock(), error="boom", retry_delay_s=0
            )
        assert outcome == ("retry" if number == 1 else "final")
        clock.advance(seconds=1)
    row = world.row("J1")
    assert row.state == "failed" and row.finished_at is not None
    assert world.claim() is None


def test_a_permanent_failure_ends_the_job_at_once(world: World, clock: Clock) -> None:
    world.enqueue("J1", max_attempts=5)
    claim = world.claim()
    assert claim is not None
    with world.factory() as uow:
        outcome = world.queue.fail(
            uow.conn(), claim, now=clock(), error="no", retry_delay_s=0, permanent=True
        )
    assert outcome == "final" and world.row("J1").state == "failed"


def test_recording_a_failure_twice_is_the_same_as_once(world: World, clock: Clock) -> None:
    world.enqueue("J1")
    claim = world.claim()
    assert claim is not None
    outcomes = []
    for _ in range(2):
        with world.factory() as uow:
            outcomes.append(
                world.queue.fail(uow.conn(), claim, now=clock(), error="boom", retry_delay_s=30)
            )
    assert outcomes == ["retry", "already"]


def test_a_lease_that_ran_out_on_the_last_attempt_fails_the_job_for_good(
    world: World, clock: Clock
) -> None:
    world.enqueue("J1", max_attempts=1)
    claim = world.claim("w1", lease_s=60)
    assert claim is not None
    clock.advance(seconds=61)
    assert world.claim("w2") is None  # no attempt left: not claimable
    with world.factory() as uow:
        reaped = world.queue.reap_expired(uow.conn(), now=clock())
    assert [(r.job_id, r.attempt, r.max_attempts) for r in reaped] == [("J1", 1, 1)]
    row = world.row("J1")
    assert row.state == "failed" and "no attempt is left" in (row.last_error or "")
    with world.factory() as uow:
        assert world.queue.reap_expired(uow.conn(), now=clock()) == []


def test_nothing_is_reaped_while_a_lease_holds_or_an_attempt_remains(
    world: World, clock: Clock
) -> None:
    world.enqueue("A", max_attempts=1)
    world.enqueue("B", max_attempts=3)
    assert world.claim("w1", lease_s=60) is not None
    assert world.claim("w1", lease_s=60) is not None
    with world.factory() as uow:
        assert world.queue.reap_expired(uow.conn(), now=clock()) == []
    clock.advance(seconds=61)
    with world.factory() as uow:
        assert [r.job_id for r in world.queue.reap_expired(uow.conn(), now=clock())] == ["A"]
    assert world.row("B").state == "running"  # B still has attempts: it is claimable, not reaped


def test_only_a_queued_job_can_be_cancelled(world: World, clock: Clock) -> None:
    world.enqueue("J1")
    world.enqueue("J2")
    claim = world.claim()
    assert claim is not None
    running, queued = ("J1", "J2") if claim.job_id == "J1" else ("J2", "J1")
    with world.factory() as uow:
        assert world.queue.cancel(uow.conn(), running, now=clock()) is False
        assert world.queue.cancel(uow.conn(), queued, now=clock()) is True
        assert world.queue.cancel(uow.conn(), queued, now=clock()) is False
    assert world.row(queued).state == "cancelled" and world.row(running).state == "running"
    assert world.claim("w2") is None


def test_counts_show_every_state(world: World, clock: Clock) -> None:
    world.enqueue("A")
    world.enqueue("B")
    world.enqueue("C")
    claim = world.claim()
    assert claim is not None
    with world.factory() as uow:
        world.queue.complete(uow.conn(), claim, now=clock())
        counts = world.queue.counts(uow.conn())
        scoped = world.queue.counts(uow.conn(), scope="project:other")
    assert counts == {"queued": 2, "running": 0, "done": 1, "failed": 0, "cancelled": 0}
    assert sum(scoped.values()) == 0


def test_a_job_id_is_enqueued_once(world: World) -> None:
    from sqlalchemy.exc import IntegrityError

    world.enqueue("J1")
    with pytest.raises(IntegrityError):
        world.enqueue("J1")


def test_max_attempts_must_be_positive(world: World) -> None:
    with pytest.raises(ValueError, match="at least 1"):
        world.enqueue("J1", max_attempts=0)


def test_the_queue_of_each_database_takes_its_own_lock(world: World, dialect: str) -> None:
    with world.factory(readonly=True) as uow:
        queue = job_queue_for(uow.conn())
    assert isinstance(queue, JobQueue)
    if dialect == "postgres":
        assert isinstance(queue, PostgresJobQueue)
        assert queue.claim_lock == POSTGRES_CLAIM_LOCK == " FOR UPDATE SKIP LOCKED"
    else:
        assert isinstance(queue, SqliteJobQueue) and queue.claim_lock == ""
    assert type(job_queue_for_dialect(dialect)) is type(queue)
    with pytest.raises(ValueError, match="unsupported dialect"):
        job_queue_for_dialect("oracle")


def test_the_claim_statement_carries_the_lock_clause_on_postgres(
    world: World, dialect: str
) -> None:
    """The candidate select is the one place the dialect shows; capture what the engine runs."""
    from sqlalchemy import event

    seen: list[str] = []
    with world.factory() as uow:
        conn = uow.conn()

        def spy(_c: Any, _cur: Any, statement: str, *_a: Any) -> None:
            seen.append(statement)

        event.listen(conn.engine, "before_cursor_execute", spy)
        try:
            world.queue.claim(conn, owner="w", now=world.clock(), lease_s=1)
            world.queue.reap_expired(conn, now=world.clock())
        finally:
            event.remove(conn.engine, "before_cursor_execute", spy)
    selects = [s for s in seen if "FROM job_queue" in s and s.lstrip().upper().startswith("SELECT")]
    assert len(selects) == 2
    assert all(("FOR UPDATE SKIP LOCKED" in s) == (dialect == "postgres") for s in selects)


def test_racing_claimers_never_get_the_same_job(world: World) -> None:
    """Eight threads claim from 30 jobs; every job is leased exactly once."""
    total = 30
    for index in range(total):
        world.enqueue(f"J{index:02d}")
    won: list[str] = []
    guard = threading.Lock()
    errors: list[BaseException] = []

    def work(name: str) -> None:
        try:
            while True:
                claim = world.claim(name, lease_s=600)
                if claim is None:
                    return
                with guard:
                    won.append(claim.job_id)
        except BaseException as exc:  # noqa: BLE001 - reported below
            errors.append(exc)

    threads = [threading.Thread(target=work, args=(f"w{n}",), daemon=True) for n in range(8)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=120)
    assert not any(t.is_alive() for t in threads), "a claimer hung"
    assert errors == []
    assert sorted(won) == [f"J{index:02d}" for index in range(total)]
    assert world.queue.counts is not None
    with world.factory(readonly=True) as uow:
        assert world.queue.counts(uow.conn())["running"] == total
