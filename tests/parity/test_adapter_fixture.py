"""The parity fixtures hand out what they say they do (P0-I5).

If ``just test-parity`` ever ran everything on SQLite twice, these would fail: they check the
dialect of the connection the test really got, and that every ``new_db()`` is its own database.
"""

from __future__ import annotations

from collections.abc import Callable

from sqlalchemy import text
from tl_adapters.db import DbTarget, create_schema, dialect_of, is_postgres, open_uow
from tl_core.ledger import NewEvent


def append_one(db: DbTarget, stream: str) -> None:
    with open_uow(db) as uow:
        uow.append(
            stream_id=stream,
            stream_type="core.Record",
            scope="company",
            expected_version=0,
            events=[
                NewEvent(
                    event_type="Record.Created",
                    payload={
                        "record_type": "core.Record",
                        "key": stream,
                        "title": "t",
                        "psets": {},
                    },
                )
            ],
            actor="user:t",
            source="test",
            correlation_id="c",
        )


def test_the_connection_really_is_the_adapter_that_was_asked_for(
    adapter_name: str, new_db: Callable[[], DbTarget]
) -> None:
    target = new_db()
    assert dialect_of(target) == adapter_name
    assert is_postgres(target) == (adapter_name == "postgres")
    create_schema(target)
    with open_uow(target, readonly=True) as uow:
        name = uow.conn().dialect.name
        version = uow.conn().execute(
            text("SELECT version()" if name == "postgresql" else "SELECT sqlite_version()")
        )
        assert version.scalar_one()
    assert name == ("postgresql" if adapter_name == "postgres" else "sqlite")


def test_every_new_db_is_a_separate_empty_database(new_db: Callable[[], DbTarget]) -> None:
    first, second = new_db(), new_db()
    assert first != second
    create_schema(first)
    create_schema(second)
    append_one(first, "only-here")
    with open_uow(second, readonly=True) as uow:
        assert uow.ledger.head_seq() == 0
    with open_uow(first, readonly=True) as uow:
        assert uow.ledger.head_seq() == 1


def test_the_db_fixture_comes_with_the_default_schema(db: DbTarget) -> None:
    with open_uow(db, readonly=True) as uow:
        count = uow.conn().execute(text("SELECT COUNT(*) FROM cur_core_record")).scalar_one()
    assert count == 0
