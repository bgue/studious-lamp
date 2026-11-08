"""Bronze ``events.intent``: on new and old bronze tables; dropped where the payload is redacted."""

from __future__ import annotations

from typing import Any

import pytest
from builder import LedgerBuilder
from tl_adapters.db import make_ledger
from tl_core.intent import Intent, intent_json
from tl_core.ledger import NewEvent
from tl_lake import LakeConfig, read_snapshot, sync_lake
from tl_lake import sync as sync_module
from tl_lake.duck import open_lake
from tl_lake.schema import EVENTS_COLUMNS

SECRET = Intent(why="INTENTSECRETWHY")


def put(ledger: LedgerBuilder, stream_type: str, stream: str, intent: Intent | None) -> None:
    engine = ledger.engine()
    try:
        make_ledger(engine).append(
            stream_id=stream,
            stream_type=stream_type,
            scope="company",
            expected_version=0,
            events=[NewEvent(event_type="Thing.Created", payload={"k": "v"}, intent=intent)],
            actor="user:u",
            source="test",
            correlation_id="c-" + stream,
        )
    finally:
        engine.dispose()


def sync(ledger: LedgerBuilder, lake: LakeConfig) -> None:
    engine = ledger.engine()
    try:
        with read_snapshot(engine) as conn:
            sync_lake(lake, conn)
    finally:
        engine.dispose()


def bronze(lake: LakeConfig) -> list[tuple[Any, ...]]:
    with open_lake(lake, write=False) as con:
        return con.execute("SELECT seq, intent FROM events ORDER BY seq").fetchall()


def test_the_bronze_schema_has_the_intent_column_last() -> None:
    assert EVENTS_COLUMNS[-1].name == "intent" and not EVENTS_COLUMNS[-1].not_null


def test_a_visible_row_keeps_its_intent_and_a_hidden_row_drops_it(
    ledger: LedgerBuilder, lake: LakeConfig
) -> None:
    put(ledger, "test.Thing", "t1", SECRET)
    put(ledger, "core.Account", "a1", SECRET)  # an internal stream: redacted whole
    put(ledger, "test.Thing", "t2", None)
    sync(ledger, lake)
    assert bronze(lake) == [(1, intent_json(SECRET)), (2, None), (3, None)]
    with open_lake(lake, write=False) as con:
        everything = str(con.execute("SELECT * FROM events WHERE seq = 2").fetchall())
    assert "INTENTSECRETWHY" not in everything


def test_an_old_bronze_table_gains_the_column(
    ledger: LedgerBuilder, lake: LakeConfig, monkeypatch: pytest.MonkeyPatch
) -> None:
    put(ledger, "test.Thing", "t1", None)
    with monkeypatch.context() as m:  # a lake made before the column existed
        m.setattr(sync_module, "EVENTS_COLUMNS", EVENTS_COLUMNS[:-1])
        sync(ledger, lake)
    with open_lake(lake, write=False) as con:
        names = [r[1] for r in con.execute("PRAGMA table_info('events')").fetchall()]
    assert "intent" not in names
    put(ledger, "test.Thing", "t2", SECRET)
    sync(ledger, lake)
    assert bronze(lake) == [(1, None), (2, intent_json(SECRET))]
