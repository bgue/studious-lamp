"""The intent carrier: ContextVar rules, and what both adapters store and hash from it."""

from __future__ import annotations

import asyncio
import contextvars
import threading
from collections.abc import Callable, Iterator

import pytest
from sqlalchemy import Engine, text
from tl_adapters.db import DbTarget, LedgerWithSchema, make_engine, make_ledger
from tl_core.archive.segments import recomputed_hash
from tl_core.intent import Intent, current_intent, intent_json, intent_scope
from tl_core.ledger import Event, NewEvent

ONE = Intent(why="one")
TWO = Intent(why="two")


def test_there_is_no_carrier_by_default() -> None:
    assert current_intent() is None


def test_the_block_sets_restores_and_nests() -> None:
    with intent_scope(ONE):
        assert current_intent() == ONE
        with intent_scope(TWO):
            assert current_intent() == TWO
        assert current_intent() == ONE
        with intent_scope(None):
            assert current_intent() is None
        assert current_intent() == ONE
    assert current_intent() is None


def test_the_carrier_is_cleared_after_a_block_that_raises() -> None:
    with pytest.raises(RuntimeError):
        with intent_scope(ONE):
            raise RuntimeError("boom")
    assert current_intent() is None


def test_a_thread_sees_it_only_with_a_copied_context() -> None:
    seen: dict[str, Intent | None] = {}
    with intent_scope(ONE):
        plain = threading.Thread(target=lambda: seen.update(plain=current_intent()))
        plain.start()
        plain.join()
        ctx = contextvars.copy_context()
        copied = threading.Thread(target=lambda: seen.update(copied=ctx.run(current_intent)))
        copied.start()
        copied.join()
    assert seen == {"plain": None, "copied": ONE}


def test_tasks_copy_the_context_and_do_not_leak_back() -> None:
    async def inner() -> Intent | None:
        with intent_scope(TWO):
            await asyncio.sleep(0)
            return current_intent()

    async def outer() -> tuple[Intent | None, Intent | None]:
        with intent_scope(ONE):
            from_task = await asyncio.create_task(inner())
            return from_task, current_intent()

    assert asyncio.run(outer()) == (TWO, ONE)


# --- append_in -------------------------------------------------------------------------------


@pytest.fixture
def engine(new_db: Callable[[], DbTarget]) -> Iterator[Engine]:
    eng = make_engine(new_db())
    yield eng
    eng.dispose()


@pytest.fixture
def ledger(engine: Engine) -> LedgerWithSchema:
    led = make_ledger(engine)
    led.create_schema()
    return led


def put(ledger: LedgerWithSchema, stream: str, intent: Intent | None = None) -> Event:
    ledger.append(
        stream_id=stream,
        stream_type="test.Thing",
        scope="company",
        expected_version=0,
        events=[NewEvent(event_type="Thing.Created", payload={"n": 1}, intent=intent)],
        actor="user:u",
        source="test",
        correlation_id="c-" + stream,
    )
    return ledger.read_stream(stream)[0]


def column(engine: Engine, stream: str) -> str | None:
    with engine.connect() as conn:
        return conn.execute(
            text("SELECT intent FROM events WHERE stream_id = :s"), {"s": stream}
        ).scalar_one()


def test_the_carrier_value_is_stored_and_hashed(engine: Engine, ledger: LedgerWithSchema) -> None:
    with intent_scope(ONE):
        event = put(ledger, "a")
    assert column(engine, "a") == intent_json(ONE) and event.intent == ONE
    assert recomputed_hash(event) == event.hash  # the same text went to the hash


def test_an_explicit_event_intent_wins_over_the_carrier(
    engine: Engine, ledger: LedgerWithSchema
) -> None:
    with intent_scope(ONE):
        event = put(ledger, "a", TWO)
    assert column(engine, "a") == intent_json(TWO)
    assert recomputed_hash(event) == event.hash


def test_no_carrier_stores_null_and_the_old_hash(engine: Engine, ledger: LedgerWithSchema) -> None:
    event = put(ledger, "a")
    assert column(engine, "a") is None and event.intent is None
    assert recomputed_hash(event) == event.hash


def test_an_empty_carrier_stores_null(engine: Engine, ledger: LedgerWithSchema) -> None:
    with intent_scope(Intent()):
        put(ledger, "a")
    assert column(engine, "a") is None
