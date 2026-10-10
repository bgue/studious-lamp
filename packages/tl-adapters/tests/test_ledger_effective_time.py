"""``effective_time`` reaches the ledger the same way on SQLite and Postgres (FANOUT D5).

``NewEvent.effective_at`` is None: the override is used, else ``recorded_at``. An event that sets
its own ``effective_at`` keeps it. ``recorded_at`` and the hash chain do not change.
"""

from __future__ import annotations

from collections.abc import Callable, Iterator
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import Engine
from tl_adapters.db import DbTarget, LedgerWithSchema, make_engine, make_ledger
from tl_core.ledger import NewEvent, canonical_json, event_hash, iso_utc
from tl_core.util import effective_time

BASE_TIME = datetime(2026, 1, 1, tzinfo=UTC)
SIM_TIME = datetime(2027, 3, 4, 8, 30, tzinfo=UTC)


class FakeClock:
    def __init__(self) -> None:
        self.calls = 0

    def __call__(self) -> datetime:
        self.calls += 1
        return BASE_TIME + timedelta(seconds=self.calls)


class FakeIds:
    def __init__(self) -> None:
        self.calls = 0

    def __call__(self) -> str:
        self.calls += 1
        return f"E{self.calls:025d}"


@pytest.fixture
def engine(new_db: Callable[[], DbTarget]) -> Iterator[Engine]:
    eng = make_engine(new_db())
    yield eng
    eng.dispose()


@pytest.fixture
def ledger(engine: Engine) -> LedgerWithSchema:
    led: LedgerWithSchema = make_ledger(engine, clock=FakeClock(), id_gen=FakeIds())
    led.create_schema()
    return led


def append(ledger: LedgerWithSchema, stream: str, expected: int, event: NewEvent):
    return ledger.append(
        stream_id=stream,
        stream_type="core.Record",
        scope="project:sim-r1",
        expected_version=expected,
        events=[event],
        actor="agent:sim-crew",
        source="sim:r1",
        correlation_id="corr-1",
    )


def plain(**payload: object) -> NewEvent:
    return NewEvent(event_type="Record.Created", payload=dict(payload) or {"n": 1})


def test_without_an_override_effective_at_is_recorded_at(ledger: LedgerWithSchema) -> None:
    stored = append(ledger, "s1", 0, plain()).events[0]
    assert stored.effective_at == stored.recorded_at


def test_the_override_sets_effective_at_and_nothing_else_moves(ledger: LedgerWithSchema) -> None:
    with effective_time(SIM_TIME):
        stored = append(ledger, "s1", 0, plain()).events[0]
    assert stored.effective_at == SIM_TIME
    assert stored.recorded_at == BASE_TIME + timedelta(seconds=1)  # the real clock, unchanged
    (read,) = ledger.read_stream("s1")
    assert read.effective_at == SIM_TIME
    assert read.recorded_at == stored.recorded_at


def test_the_hash_does_not_depend_on_the_override(
    ledger: LedgerWithSchema, new_db: Callable[[], DbTarget]
) -> None:
    other_engine = make_engine(new_db())
    try:
        other: LedgerWithSchema = make_ledger(other_engine, clock=FakeClock(), id_gen=FakeIds())
        other.create_schema()
        with effective_time(SIM_TIME):
            simulated = append(ledger, "s1", 0, plain(title="x")).events[0]
        real = append(other, "s1", 0, plain(title="x")).events[0]
    finally:
        other_engine.dispose()
    assert simulated.effective_at != real.effective_at
    assert simulated.hash == real.hash
    assert simulated.hash == event_hash(
        None,
        simulated.event_id,
        "s1",
        1,
        "Record.Created",
        canonical_json({"title": "x"}),
        iso_utc(simulated.recorded_at),
    )


def test_an_event_that_sets_its_own_effective_at_keeps_it(ledger: LedgerWithSchema) -> None:
    own = datetime(2025, 5, 5, 5, 5, tzinfo=UTC)
    with effective_time(SIM_TIME):
        stored = append(ledger, "s1", 0, plain().model_copy(update={"effective_at": own}))
    assert stored.events[0].effective_at == own


def test_every_event_of_one_append_gets_the_override(ledger: LedgerWithSchema) -> None:
    with effective_time(SIM_TIME):
        result = ledger.append(
            stream_id="s1",
            stream_type="core.Record",
            scope="project:sim-r1",
            expected_version=0,
            events=[plain(a=1), plain(a=2)],
            actor="agent:sim-crew",
            source="sim:r1",
            correlation_id="c",
        )
    assert [e.effective_at for e in result.events] == [SIM_TIME, SIM_TIME]
    after = append(ledger, "s1", 2, plain(a=3)).events[0]
    assert after.effective_at == after.recorded_at  # outside the block again
