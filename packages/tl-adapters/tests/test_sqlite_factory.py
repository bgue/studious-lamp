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


def test_readonly_may_be_passed_by_position_or_keyword(factory: SqliteUowFactory) -> None:
    for call in (lambda: factory(True), lambda: factory(readonly=True)):
        with pytest.raises(RuntimeError, match="read-only"), call() as uow:
            uow.append()
    with factory() as uow:  # the default is a write unit
        assert uow.ledger.head_seq() == 0
    with factory(readonly=False) as uow:
        assert uow.ledger.head_seq() == 0


def test_close_and_dispose_both_release_the_engine(tmp_path: Path) -> None:
    db = tmp_path / "tl.db"
    create_schema(db)
    for name in ("close", "dispose"):
        made = SqliteUowFactory(db)
        assert made.engine is not None and made.ledger is not None and made.bus is not None
        getattr(made, name)()
        getattr(made, name)()  # harmless twice
