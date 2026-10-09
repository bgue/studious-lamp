"""The long-lived SQLite unit-of-work factory servers use (P0-I4-C)."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from tl_adapters.sqlite.factory import SqliteUowFactory
from tl_adapters.sqlite.uow import create_schema
from tl_core.bus import InProcessBus
from tl_core.ledger import Event, NewEvent


def append(factory: SqliteUowFactory, key: str) -> None:
    with factory(False) as uow:
        uow.append(
            stream_id=f"R-{key}",
            stream_type="core.Record",
            scope="project:P1",
            expected_version=0,
            events=[
                NewEvent(
                    event_type="Record.Created",
                    payload={"record_type": "core.Record", "key": key, "title": key},
                )
            ],
            actor="user:t",
            source="test",
            correlation_id="c",
        )


@pytest.fixture
def factory(tmp_path: Path) -> Iterator[SqliteUowFactory]:
    db = tmp_path / "tl.db"
    create_schema(db)
    made = SqliteUowFactory(db)
    yield made
    made.close()


def test_committed_events_are_published_on_the_factorys_bus(factory: SqliteUowFactory) -> None:
    seen: list[Event] = []
    assert isinstance(factory.bus, InProcessBus)
    factory.bus.subscribe(seen.append)
    append(factory, "A")
    append(factory, "B")
    assert [e.payload["key"] for e in seen] == ["A", "B"]


def test_a_rolled_back_unit_publishes_nothing(factory: SqliteUowFactory) -> None:
    seen: list[Event] = []
    factory.bus.subscribe(seen.append)
    with pytest.raises(RuntimeError), factory(False) as uow:
        uow.append(
            stream_id="R-X",
            stream_type="core.Record",
            scope="project:P1",
            expected_version=0,
            events=[
                NewEvent(
                    event_type="Record.Created",
                    payload={"record_type": "core.Record", "key": "X", "title": "X"},
                )
            ],
            actor="user:t",
            source="test",
            correlation_id="c",
        )
        raise RuntimeError("refuse")
    assert seen == [] and factory.ledger.head_seq() == 0


def test_a_read_only_unit_refuses_to_append(factory: SqliteUowFactory) -> None:
    with pytest.raises(RuntimeError, match="read-only"), factory(True) as uow:
        uow.append()


def test_units_share_one_engine_and_see_each_others_commits(factory: SqliteUowFactory) -> None:
    append(factory, "A")
    with factory(True) as uow:
        assert uow.ledger.head_seq() == 1
    assert factory.ledger.read_after(0)[0].payload["key"] == "A"
