"""Seal, restore and re-verify a ledger whose events carry intents, on both adapters."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import pytest
from sqlalchemy import text
from tl_adapters.db import DbTarget, create_schema, make_engine, make_ledger, read_tx, write_tx
from tl_adapters.restore import restore_from_archive
from tl_core.archive import generate_signer, seal_segment, verify_archive
from tl_core.intent import Intent, IntentRef, IntentToward, intent_json
from tl_core.ledger import NewEvent


class Store:
    """A write-once in-memory archive store."""

    def __init__(self) -> None:
        self.files: dict[str, bytes] = {}

    def put_bytes(self, key: str, data: bytes) -> None:
        from tl_core.archive import ArchiveExistsError

        if key in self.files:
            raise ArchiveExistsError(key)
        self.files[key] = data

    def get_bytes(self, key: str) -> bytes:
        return self.files[key]

    def exists(self, key: str) -> bool:
        return key in self.files

    def list_keys(self, prefix: str) -> list[str]:
        return sorted(k for k in self.files if k.startswith(prefix))


def rows(db: DbTarget) -> list[tuple[Any, ...]]:
    engine = make_engine(db)
    try:
        with read_tx(engine) as conn:
            return [tuple(r) for r in conn.execute(text("SELECT * FROM events ORDER BY seq")).all()]
    finally:
        engine.dispose()


@pytest.mark.parametrize("old_target", [False, True], ids=["fresh", "pre-intent-table"])
def test_seal_restore_verify_with_intents(new_db: Callable[[], DbTarget], old_target: bool) -> None:
    source = new_db()
    create_schema(source)
    engine = make_engine(source)
    ledger = make_ledger(engine)
    intents = [
        None,
        Intent(why="reason", next=[IntentRef(text="then this")]),
        Intent(toward=IntentToward(target="R-1", condition="signed")),
        None,
    ]
    for i, intent in enumerate(intents):
        ledger.append(
            stream_id=f"s{i}",
            stream_type="test.Thing",
            scope="company",
            expected_version=0,
            events=[NewEvent(event_type="Thing.Created", payload={"n": i}, intent=intent)],
            actor="user:u",
            source="test",
            correlation_id=f"c{i}",
        )
    signer = generate_signer()
    store = Store()
    with read_tx(engine) as conn:
        assert seal_segment(conn, store, signer, max_events=3) is not None
        assert seal_segment(conn, store, signer, max_events=3) is not None
    engine.dispose()
    assert verify_archive(store, public_key=signer.public_key) == []

    target = new_db()
    if old_target:  # an empty database made before the column existed: restore adds it first
        create_schema(target)
        old = make_engine(target)
        with write_tx(old) as conn:
            conn.exec_driver_sql("ALTER TABLE events DROP COLUMN intent")
        old.dispose()
    restore_from_archive(store, target, public_key=signer.public_key)
    assert rows(target) == rows(source)  # verbatim, intent text included
    assert [r[-1] for r in rows(target)] == [intent_json(i) for i in intents]
    engine = make_engine(target)
    try:
        with read_tx(engine) as conn:
            assert verify_archive(store, public_key=signer.public_key, conn=conn) == []
    finally:
        engine.dispose()
