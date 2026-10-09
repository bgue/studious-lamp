"""The change feed over a real SQLite ledger: bus, poller, paged reads and resume."""

from __future__ import annotations

import threading
from collections.abc import Iterator
from pathlib import Path

import pytest
from tl_adapters.sqlite.engine import make_engine
from tl_adapters.sqlite.ledger import SqliteLedger
from tl_adapters.sqlite.uow import create_schema, open_uow
from tl_core.bus import InProcessBus
from tl_core.changefeed import (
    ChangePoller,
    SubscriptionFilter,
    SubscriptionRegistry,
    fetch_changes,
)
from tl_core.ledger import Event, NewEvent

SCOPE = "project:P1"


def write(db: Path, key: str, *, scope: str = SCOPE, bus: InProcessBus | None = None) -> None:
    """Create one record, as a writer process would."""
    with open_uow(db, bus=bus) as uow:
        uow.append(
            stream_id=f"R-{scope}-{key}",
            stream_type="core.Record",
            scope=scope,
            expected_version=0,
            events=[
                NewEvent(
                    event_type="Record.Created",
                    payload={"record_type": "task", "key": key, "title": key, "psets": {}},
                )
            ],
            actor="user:t",
            source="test",
            correlation_id="c",
        )


@pytest.fixture
def db(tmp_path: Path) -> Path:
    path = tmp_path / "ledger.db"
    create_schema(path)
    return path


@pytest.fixture
def reader(db: Path) -> Iterator[SqliteLedger]:
    """A second connection pool on the same file: what another process would hold."""
    engine = make_engine(db)
    yield SqliteLedger(engine)
    engine.dispose()


def wait_for(got: list[int], count: int, seconds: float = 10.0) -> None:
    done = threading.Event()
    for _ in range(int(seconds / 0.01)):
        if len(got) >= count:
            done.set()
            break
        threading.Event().wait(0.01)
    assert done.is_set(), f"expected {count} events, saw {got}"


def test_the_bus_feeds_subscribers_in_commit_order(db: Path) -> None:
    bus = InProcessBus()
    registry = SubscriptionRegistry()
    registry.attach(bus)
    got: list[int] = []
    registry.subscribe(lambda event: got.append(event.seq))
    for n in range(5):
        write(db, f"K-{n}", bus=bus)
    assert got == [1, 2, 3, 4, 5]


def test_a_poller_in_another_connection_sees_writes_that_never_touched_its_bus(
    db: Path, reader: SqliteLedger
) -> None:
    registry = SubscriptionRegistry(reader)
    got: list[int] = []
    registry.subscribe(lambda event: got.append(event.seq))
    with ChangePoller(reader, registry, interval_s=0.01):
        for n in range(4):
            write(db, f"K-{n}")  # no bus: an out-of-process writer
        wait_for(got, 4)
    assert got == [1, 2, 3, 4]


def test_bus_and_poller_together_deliver_each_event_once(db: Path, reader: SqliteLedger) -> None:
    bus = InProcessBus()
    registry = SubscriptionRegistry(reader)
    registry.attach(bus)
    got: list[int] = []
    registry.subscribe(lambda event: got.append(event.seq))
    with ChangePoller(reader, registry, interval_s=0.005):
        for n in range(30):
            write(db, f"K-{n}", bus=bus)
        wait_for(got, 30)
        threading.Event().wait(0.1)  # let the poller offer every event again
    assert got == list(range(1, 31))


def test_a_client_resumes_from_its_last_seq_without_loss_or_repeats(
    db: Path, reader: SqliteLedger
) -> None:
    for n in range(10):
        write(db, f"K-{n}")
    first: list[int] = []
    registry = SubscriptionRegistry(reader)
    registry.subscribe(lambda event: first.append(event.seq), after_seq=0)
    assert first == list(range(1, 11))
    # the client "disconnects" after seq 6, more events arrive, a new session resumes from 6
    for n in range(10, 14):
        write(db, f"K-{n}")
    again: list[int] = []
    other = SubscriptionRegistry(reader)
    other.subscribe(lambda event: again.append(event.seq), after_seq=6)
    assert again == list(range(7, 15))


def test_a_restarted_poller_continues_after_its_stored_cursor(
    db: Path, reader: SqliteLedger
) -> None:
    for n in range(3):
        write(db, f"K-{n}")
    registry = SubscriptionRegistry()
    got: list[int] = []
    registry.subscribe(lambda event: got.append(event.seq), after_seq=0)
    poller = ChangePoller(reader, registry, after_seq=0)
    assert poller.poll_once() == 3
    stored = poller.cursor
    write(db, "K-3")
    write(db, "K-4")
    revived = ChangePoller(reader, registry, after_seq=stored)
    assert revived.poll_once() == 2
    assert got == [1, 2, 3, 4, 5]


def test_filters_work_end_to_end_with_scope_pushdown(db: Path, reader: SqliteLedger) -> None:
    write(db, "A", scope="company")
    write(db, "B", scope=SCOPE)
    write(db, "C", scope="company")
    registry = SubscriptionRegistry(reader)
    got: list[Event] = []
    registry.subscribe(got.append, SubscriptionFilter(scope="company"), after_seq=0)
    assert [e.seq for e in got] == [1, 3]
    page = fetch_changes(reader, flt=SubscriptionFilter(scope="company"), limit=1)
    assert ([e.seq for e in page.events], page.next_seq, page.has_more) == ([1], 1, True)
    rest = fetch_changes(reader, after_seq=page.next_seq, flt=SubscriptionFilter(scope="company"))
    assert ([e.seq for e in rest.events], rest.next_seq, rest.has_more) == ([3], 3, False)


def test_record_id_filter_selects_one_records_events(db: Path, reader: SqliteLedger) -> None:
    write(db, "A")
    write(db, "B")
    flt = SubscriptionFilter.of(record_ids=[f"R-{SCOPE}-B"])
    page = fetch_changes(reader, flt=flt)
    assert [e.stream_id for e in page.events] == [f"R-{SCOPE}-B"]
    assert page.next_seq == 2
