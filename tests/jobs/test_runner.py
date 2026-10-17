"""The worker loop: a job runs once, a killed or slow worker loses it, failures retry (ADR-0014)."""

from __future__ import annotations

import threading
from typing import Any

import pytest
from jobsworld import Clock, Kind, World
from tl_core.jobs import Claim, JobFailure, JobRunner
from tl_core.services.errors import ServiceError


def test_an_empty_queue_has_nothing_to_do(world: World) -> None:
    kind = Kind()
    assert world.runner(kind).run_once() is None
    assert kind.calls == []


def test_a_job_is_started_prepared_run_and_settled_once(world: World) -> None:
    world.enqueue("J1")
    kind = Kind()
    result = world.runner(kind).run_once()
    assert result is not None
    assert (result.job_id, result.attempt, result.outcome) == ("J1", 1, "done")
    assert [c[0] for c in kind.calls] == ["started", "prepare", "run", "settle"]
    assert world.row("J1").state == "done"
    assert world.runner(kind).run_once() is None


def test_run_until_idle_runs_every_job_and_serve_stops_when_told(world: World) -> None:
    for index in range(3):
        world.enqueue(f"J{index}")
    kind = Kind()
    runner = world.runner(kind)
    assert [r.outcome for r in runner.run_until_idle()] == ["done"] * 3
    world.enqueue("J9")
    stops = iter([False, False, True])
    slept: list[float] = []
    ran = runner.serve(lambda: next(stops), idle_s=0.5, sleep=slept.append)
    assert ran == 1 and slept == [0.5]  # one job, then one idle wait, then stop


def test_a_job_of_a_kind_nobody_serves_is_left_alone(world: World) -> None:
    world.enqueue("J1", kind="other")
    assert world.runner(Kind()).run_once() is None
    assert world.row("J1").state == "queued"


def test_a_failing_attempt_is_retried_after_a_delay_and_then_succeeds(
    world: World, clock: Clock
) -> None:
    world.enqueue("J1")
    state = {"fail": True}

    def work(claim: Claim) -> str:
        if state["fail"]:
            raise RuntimeError("private detail /home/user/secret")
        return "ok"

    kind = Kind(work=work)
    runner = world.runner(kind)
    first = runner.run_once()
    assert first is not None and first.outcome == "retry"
    row = world.row("J1")
    assert row.state == "queued" and row.last_error == "internal_error: unexpected RuntimeError"
    assert "secret" not in (row.last_error or "")  # only the type name is kept
    assert runner.run_once() is None  # the delay has not passed
    clock.advance(seconds=31)
    state["fail"] = False
    second = runner.run_once()
    assert second is not None and (second.outcome, second.attempt) == ("done", 2)
    assert kind.count("retry") == 1 and kind.count("settle") == 1


def test_the_last_attempt_that_fails_fails_the_job_for_good(world: World, clock: Clock) -> None:
    world.enqueue("J1", max_attempts=2)

    def work(claim: Claim) -> str:
        raise RuntimeError("x")

    kind = Kind(work=work)
    runner = world.runner(kind)
    assert runner.run_once() is not None
    clock.advance(seconds=61)
    last = runner.run_once()
    assert last is not None and last.outcome == "final"
    assert world.row("J1").state == "failed"
    assert (kind.count("retry"), kind.count("final"), kind.count("settle")) == (1, 1, 0)


def test_a_permanent_failure_of_prepare_ends_the_job_without_a_retry(world: World) -> None:
    world.enqueue("J1")
    kind = Kind(prepare_error=JobFailure("source_too_large", "too big", retryable=False))
    result = world.runner(kind).run_once()
    assert result is not None and result.outcome == "final"
    row = world.row("J1")
    assert row.state == "failed" and row.last_error == "source_too_large: too big"
    assert kind.count("run") == 0


def test_a_retryable_failure_of_prepare_is_retried(world: World) -> None:
    world.enqueue("J1")
    kind = Kind(prepare_error=JobFailure("source_not_available", "in quarantine"))
    result = world.runner(kind).run_once()
    assert result is not None and result.outcome == "retry"


def test_a_refusal_while_settling_rolls_the_completion_back_and_fails_the_job(
    world: World,
) -> None:
    world.enqueue("J1")
    kind = Kind(settle_error=ServiceError("the derived document was voided"))
    result = world.runner(kind).run_once()
    assert result is not None and result.outcome == "final"  # a ServiceError is permanent
    row = world.row("J1")
    assert row.state == "failed" and "was voided" in (row.last_error or "")


def test_an_unexpected_error_while_settling_is_retried(world: World) -> None:
    world.enqueue("J1")
    kind = Kind(settle_error=RuntimeError("db hiccup"))
    result = world.runner(kind).run_once()
    assert result is not None and result.outcome == "retry"
    assert world.row("J1").state == "queued"  # the completion was rolled back with the settle


def test_a_worker_that_dies_mid_run_loses_the_job_to_the_next_one_and_it_completes_once(
    world: World, clock: Clock
) -> None:
    world.enqueue("J1")
    dead = world.claim("dead-worker", lease_s=60)  # claimed, then the process was killed
    assert dead is not None
    kind = Kind()
    survivor = world.runner(kind, "w2")
    assert survivor.run_once() is None  # the lease still holds
    clock.advance(seconds=61)
    result = survivor.run_once()
    assert result is not None and (result.outcome, result.attempt) == ("done", 2)
    assert kind.count("settle") == 1
    with world.factory() as uow:  # the dead worker "comes back" and tries to finish
        assert world.queue.complete(uow.conn(), dead, now=clock()) == "lost"


def test_a_slow_worker_whose_lease_was_taken_over_settles_nothing(
    world: World, clock: Clock
) -> None:
    """A is still working when its lease ends and B finishes the job; A must write nothing."""
    world.enqueue("J1")
    kind = Kind()
    runner_b = world.runner(kind, "B", lease_s=60)
    inner: dict[str, Any] = {}

    def slow(claim: Claim) -> str:
        if claim.owner == "A":
            clock.advance(seconds=61)  # A's lease ends while A is still working
            inner["b"] = runner_b.run_once()  # B claims attempt 2 and finishes it
        return f"by {claim.owner}"

    kind.work = slow
    runner_a = world.runner(kind, "A", lease_s=60)
    result = runner_a.run_once()
    assert result is not None and result.outcome == "lost" and result.attempt == 1
    assert inner["b"].outcome == "done" and inner["b"].attempt == 2
    assert kind.count("settle") == 1  # once, by B
    assert [c for c in kind.calls if c[0] == "settle"] == [("settle", "J1", 2)]
    assert world.row("J1").lease_owner == "B"


def test_a_job_whose_lease_ran_out_on_its_last_attempt_is_failed_and_reported(
    world: World, clock: Clock
) -> None:
    world.enqueue("J1", max_attempts=1)
    assert world.claim("dead", lease_s=60) is not None
    clock.advance(seconds=61)
    kind = Kind()
    assert world.runner(kind).run_once() is None
    assert kind.calls == [("expired", "J1", 1)]
    assert world.row("J1").state == "failed"


def test_two_workers_run_forty_jobs_and_each_settles_exactly_once(world: World) -> None:
    for index in range(40):
        world.enqueue(f"J{index:02d}")
    kind = Kind()
    guard = threading.Lock()
    errors: list[BaseException] = []
    plain = kind.settle

    def counted(uow: Any, claim: Claim, outcome: Any) -> None:
        with guard:
            plain(uow, claim, outcome)

    kind.settle = counted  # type: ignore[method-assign]

    def work(name: str) -> None:
        try:
            JobRunner(
                world.factory, world.queue, [kind], worker_id=name, clock=world.clock
            ).run_until_idle()
        except BaseException as exc:  # noqa: BLE001 - reported below
            errors.append(exc)

    threads = [threading.Thread(target=work, args=(f"w{n}",), daemon=True) for n in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=120)
    assert not any(t.is_alive() for t in threads), "a worker hung"
    assert errors == []
    settled = sorted(c[1] for c in kind.calls if c[0] == "settle")
    assert settled == [f"J{index:02d}" for index in range(40)]
    with world.factory(readonly=True) as uow:
        assert world.queue.counts(uow.conn())["done"] == 40


def test_two_kinds_cannot_share_a_name(world: World) -> None:
    with pytest.raises(ValueError, match="share a name"):
        JobRunner(world.factory, world.queue, [Kind(), Kind()])
