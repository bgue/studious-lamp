"""The unit of work, schema creation and rebuild on every adapter (P0-I1-T07, parity P0-I5)."""

from __future__ import annotations

import threading
import time
import uuid
from collections.abc import Callable, Sequence

import pytest
from sqlalchemy import Connection, inspect, text
from tl_adapters._unit import BaseUnitOfWork
from tl_adapters.db import DbTarget, create_schema, open_uow, rebuild_projections
from tl_core.bus import InProcessBus
from tl_core.ledger import ConcurrencyError, Event, NewEvent
from tl_core.projection import InMemoryRegistry
from tl_core.projection.testing import CounterProjector


class FailingProjector:
    name = "failing"
    handles = frozenset({"Test.Boom"})

    def ddl(self, dialect: str) -> list[str]:
        return []

    def apply(self, conn: Connection, event: Event) -> None:
        raise RuntimeError("projector bug")

    def reset(self, conn: Connection) -> None:
        return None


@pytest.fixture
def db(new_db: Callable[[], DbTarget]) -> DbTarget:
    target = new_db()
    create_schema(target, registry=InMemoryRegistry([CounterProjector()]))
    return target


def registry() -> InMemoryRegistry:
    return InMemoryRegistry([CounterProjector()])


def bump(uow: BaseUnitOfWork, stream: str, expected: int, n: int = 1) -> None:
    uow.append(
        stream_id=stream,
        stream_type="test.Thing",
        scope="project:P1",
        expected_version=expected,
        events=[NewEvent(event_type="Test.Bumped", payload={"i": i}) for i in range(n)],
        actor="user:dev",
        source="test",
        correlation_id="c",
    )


def counter(db: DbTarget) -> dict[str, int]:
    with open_uow(db, readonly=True, registry=registry()) as uow:
        rows = uow.conn().execute(text("SELECT stream_id, n FROM test_counter_rows")).all()
    return {r.stream_id: r.n for r in rows}


def test_append_updates_projection_in_the_same_transaction(db: DbTarget) -> None:
    with open_uow(db, registry=registry()) as uow:
        bump(uow, "s1", 0, n=2)
        # read-your-writes: visible on the transaction's own connection before commit
        row = uow.conn().execute(text("SELECT n, last_seq FROM test_counter_rows")).one()
        assert (row.n, row.last_seq) == (2, 2)
        # but not to a different connection until commit
        assert uow.ledger.head_seq() == 0
    assert counter(db) == {"s1": 2}
    with open_uow(db, readonly=True) as uow:
        assert uow.ledger.head_seq() == 2


def test_exception_rolls_back_events_and_projection_and_publishes_nothing(db: DbTarget) -> None:
    bus = InProcessBus()
    seen: list[int] = []
    bus.subscribe(lambda e: seen.append(e.seq))
    with pytest.raises(RuntimeError, match="abort"):
        with open_uow(db, registry=registry(), bus=bus) as uow:
            bump(uow, "s1", 0)
            raise RuntimeError("abort")
    assert counter(db) == {}
    assert seen == []
    with open_uow(db, readonly=True) as uow:
        assert uow.ledger.head_seq() == 0


def test_projector_failure_rolls_back_the_whole_transaction(db: DbTarget) -> None:
    reg = InMemoryRegistry([CounterProjector(), FailingProjector()])
    with pytest.raises(RuntimeError, match="projector bug"):
        with open_uow(db, registry=reg) as uow:
            bump(uow, "s1", 0)
            uow.append(
                stream_id="s2",
                stream_type="test.Thing",
                scope="project:P1",
                expected_version=0,
                events=[NewEvent(event_type="Test.Boom", payload={})],
                actor="user:dev",
                source="test",
                correlation_id="c",
            )
    assert counter(db) == {}
    with open_uow(db, readonly=True) as uow:
        assert uow.ledger.head_seq() == 0


def test_commit_publishes_events_after_the_transaction(db: DbTarget) -> None:
    bus = InProcessBus()
    seen: list[tuple[int, int]] = []

    def on_event(event: Event) -> None:
        # the commit has happened: a fresh connection already sees the event
        with open_uow(db, readonly=True) as other:
            seen.append((event.seq, other.ledger.head_seq()))

    bus.subscribe(on_event)
    with open_uow(db, registry=registry(), bus=bus) as uow:
        bump(uow, "s1", 0, n=2)
        assert seen == []
    assert seen == [(1, 2), (2, 2)]


def test_stale_expected_version_raises_and_rolls_back(db: DbTarget) -> None:
    with open_uow(db, registry=registry()) as uow:
        bump(uow, "s1", 0)
    with pytest.raises(ConcurrencyError):
        with open_uow(db, registry=registry()) as uow:
            bump(uow, "s2", 0)
            bump(uow, "s1", 0)
    assert counter(db) == {"s1": 1}


def test_readonly_uow_refuses_append_and_closed_uow_refuses_conn(db: DbTarget) -> None:
    with open_uow(db, readonly=True, registry=registry()) as uow:
        with pytest.raises(RuntimeError, match="read-only"):
            bump(uow, "s1", 0)
    with pytest.raises(RuntimeError, match="not open"):
        uow.conn()


def test_create_schema_is_idempotent_and_builds_projector_tables(
    new_db: Callable[[], DbTarget],
) -> None:
    path = new_db()
    reg = registry()
    create_schema(path, registry=reg)
    create_schema(path, registry=reg)
    with open_uow(path, readonly=True, registry=reg) as uow:
        names = set(inspect(uow.conn()).get_table_names())
    assert {"events", "test_counter_rows"} <= names


def test_rebuild_replays_the_ledger_into_reset_projections(db: DbTarget) -> None:
    with open_uow(db, registry=registry()) as uow:
        bump(uow, "s1", 0, n=3)
        bump(uow, "s2", 0, n=1)
    with open_uow(db, registry=registry()) as uow:
        uow.conn().execute(text("UPDATE test_counter_rows SET n = 99"))  # corrupt the read model
        uow.conn().execute(text("INSERT INTO test_counter_rows VALUES ('ghost', 7, 0)"))
    assert counter(db)["s1"] == 99
    replayed = rebuild_projections(db, registry=registry())
    assert replayed == 4
    assert counter(db) == {"s1": 3, "s2": 1}


def test_rebuild_with_names_only_touches_those_projectors(db: DbTarget) -> None:
    with open_uow(db, registry=registry()) as uow:
        bump(uow, "s1", 0)
    with pytest.raises(KeyError):
        rebuild_projections(db, types=["nope"], registry=registry())
    assert rebuild_projections(db, types=["test_counter"], registry=registry()) == 1


def test_failed_rebuild_leaves_old_rows(db: DbTarget) -> None:
    class ExplodingOnReplay(CounterProjector):
        def apply(self, conn: Connection, event: Event) -> None:
            raise RuntimeError("replay bug")

    with open_uow(db, registry=registry()) as uow:
        bump(uow, "s1", 0, n=2)
    with pytest.raises(RuntimeError, match="replay bug"):
        rebuild_projections(db, registry=InMemoryRegistry([ExplodingOnReplay()]))
    assert counter(db) == {"s1": 2}


class SlowBus(InProcessBus):
    """Widens the gap between commit and publish so an ordering bug would show."""

    calls = 0

    def publish(self, events: Sequence[Event]) -> None:
        SlowBus.calls += 1
        if SlowBus.calls % 3 == 1:  # every third publish is slow, so later commits overtake it
            time.sleep(0.02)
        super().publish(events)


def test_concurrent_writers_publish_in_commit_order_without_loss(db: DbTarget) -> None:
    SlowBus.calls = 0
    bus = SlowBus()
    seen: list[int] = []
    bus.subscribe(lambda e: seen.append(e.seq))
    barrier = threading.Barrier(2)

    def writer(name: str) -> None:
        barrier.wait()
        for _ in range(15):
            with open_uow(db, registry=registry(), bus=bus) as uow:
                bump(uow, f"{name}-{uuid.uuid4().hex}", 0)

    threads = [threading.Thread(target=writer, args=(n,)) for n in ("a", "b")]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert seen == list(range(1, 31))
    assert sum(counter(db).values()) == 30


def test_a_write_from_inside_a_callback_completes_and_is_delivered_in_order(db: DbTarget) -> None:
    bus = InProcessBus()
    first: list[int] = []
    second: list[int] = []
    nested = {"done": False}

    def on_event(event: Event) -> None:
        first.append(event.seq)
        if event.seq == 1 and not nested["done"]:
            nested["done"] = True
            with open_uow(db, registry=registry(), bus=bus) as inner:  # same bus, from a callback
                bump(inner, "inner", 0)

    bus.subscribe(on_event)
    bus.subscribe(lambda e: second.append(e.seq))

    def outer() -> None:
        with open_uow(db, registry=registry(), bus=bus) as uow:
            bump(uow, "outer", 0)

    thread = threading.Thread(target=outer, daemon=True)
    thread.start()
    thread.join(10)
    assert not thread.is_alive(), "nested write deadlocked"
    assert first == [1, 2]
    assert second == [1, 2]
    assert counter(db) == {"outer": 1, "inner": 1}


def test_a_slow_subscriber_does_not_block_another_writers_commit(db: DbTarget) -> None:
    bus = InProcessBus()
    seen: list[int] = []
    started, release = threading.Event(), threading.Event()

    def slow(event: Event) -> None:
        seen.append(event.seq)
        if event.seq == 1:
            started.set()
            assert release.wait(10)

    bus.subscribe(slow)

    def writer_a() -> None:
        with open_uow(db, registry=registry(), bus=bus) as uow:
            bump(uow, "a", 0)

    thread_a = threading.Thread(target=writer_a, daemon=True)
    thread_a.start()
    assert started.wait(10)  # A has committed and its subscriber is now blocked
    done_b = threading.Event()

    def writer_b() -> None:
        with open_uow(db, registry=registry(), bus=bus) as uow:
            bump(uow, "b", 0)
        done_b.set()

    thread_b = threading.Thread(target=writer_b, daemon=True)
    thread_b.start()
    assert done_b.wait(10), "writer B was blocked by a slow subscriber"
    assert counter(db) == {"a": 1, "b": 1}  # B committed while A's callback still runs
    assert seen == [1]
    release.set()
    thread_a.join(10)
    thread_b.join(10)
    assert seen == [1, 2]
