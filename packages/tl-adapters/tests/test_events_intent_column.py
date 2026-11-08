"""``events.intent`` on both adapters: fresh and pre-existing databases, append, read, hash."""

from __future__ import annotations

from collections.abc import Callable, Iterator

import pytest
from sqlalchemy import Engine, text
from sqlalchemy.exc import IntegrityError
from tl_adapters.db import DbTarget, LedgerWithSchema, make_engine, make_ledger, write_tx
from tl_core.archive.segments import recomputed_hash
from tl_core.intent import Intent, IntentToward, intent_json
from tl_core.ledger import NewEvent


@pytest.fixture
def engine(new_db: Callable[[], DbTarget]) -> Iterator[Engine]:
    eng = make_engine(new_db())
    yield eng
    eng.dispose()


def columns(engine: Engine) -> list[str]:
    with engine.connect() as conn:
        return list(conn.execute(text("SELECT * FROM events WHERE 1 = 0")).keys())


def put(ledger: LedgerWithSchema, stream: str, intent: Intent | None) -> None:
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


def drop_column(engine: Engine) -> None:
    with write_tx(engine) as conn:
        conn.exec_driver_sql("ALTER TABLE events DROP COLUMN intent")


def test_a_fresh_database_has_the_column(engine: Engine) -> None:
    make_ledger(engine).create_schema()
    assert columns(engine)[-1] == "intent"


def test_an_existing_database_gets_the_column_idempotently(engine: Engine) -> None:
    ledger = make_ledger(engine)
    ledger.create_schema()
    put(ledger, "old", None)
    drop_column(engine)
    assert "intent" not in columns(engine)
    ledger.create_schema()
    assert columns(engine)[-1] == "intent"
    ledger.create_schema()
    assert columns(engine).count("intent") == 1
    assert ledger.read_stream("old")[0].intent is None  # the old row is untouched


def test_the_first_append_adds_the_column_to_an_existing_database(engine: Engine) -> None:
    ledger = make_ledger(engine)
    ledger.create_schema()
    drop_column(engine)
    fresh = make_ledger(engine)  # a process that opened the old file and never ran create_schema
    put(fresh, "s1", Intent(why="because"))
    assert fresh.read_stream("s1")[0].intent == Intent(why="because")


def test_append_stores_the_text_and_read_returns_the_model(engine: Engine) -> None:
    ledger = make_ledger(engine)
    ledger.create_schema()
    intent = Intent(why="w", toward=IntentToward(target="R-1", state="Done"))
    put(ledger, "with", intent)
    put(ledger, "empty", Intent())
    put(ledger, "none", None)
    with engine.connect() as conn:
        stored = dict(conn.execute(text("SELECT stream_id, intent FROM events")).all())
    assert stored == {"with": intent_json(intent), "empty": None, "none": None}
    got = ledger.read_stream("with")[0]
    assert got.intent == intent
    assert recomputed_hash(got) == got.hash
    for stream in ("empty", "none"):
        event = ledger.read_stream(stream)[0]
        assert event.intent is None and recomputed_hash(event) == event.hash


def test_the_hash_covers_the_intent(engine: Engine) -> None:
    ledger = make_ledger(engine)
    ledger.create_schema()
    put(ledger, "a", Intent(why="one"))
    event = ledger.read_stream("a")[0]
    forged = event.model_copy(update={"intent": Intent(why="two")})
    assert recomputed_hash(forged) != event.hash


def test_update_of_the_intent_is_still_refused(engine: Engine) -> None:
    ledger = make_ledger(engine)
    ledger.create_schema()
    put(ledger, "a", Intent(why="one"))
    with pytest.raises(IntegrityError, match="append-only"), engine.begin() as conn:
        conn.execute(text("UPDATE events SET intent = 'x'"))
    assert ledger.read_stream("a")[0].intent == Intent(why="one")
