"""``open_backend``: one backend from a SQLite path or a Postgres URL (P1-I0-S30).

Runs on the adapters named by ``--adapters`` (SQLite by default; ``just test-parity`` adds
Postgres).
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import pytest
from sqlalchemy import text
from tl_adapters.backend import BackendUnavailableError, ledger_exists, open_backend
from tl_adapters.db import DbTarget, as_target, create_schema, display_target, is_postgres
from tl_core.ledger import Event, NewEvent


def create(uow: object, key: str) -> None:
    uow.append(  # type: ignore[attr-defined]
        stream_id=key,
        stream_type="core.Record",
        scope="project:P1",
        expected_version=0,
        events=[
            NewEvent(
                event_type="Record.Created",
                payload={"record_type": "core.Record", "key": key, "title": key, "psets": {}},
            )
        ],
        actor="user:t",
        source="test",
        correlation_id="c",
    )


@pytest.fixture
def target(new_db: Callable[[], DbTarget]) -> DbTarget:
    found = new_db()
    create_schema(found)
    return found


def test_the_backend_writes_reads_and_publishes_on_either_adapter(target: DbTarget) -> None:
    seen: list[Event] = []
    with open_backend(target) as backend:
        backend.bus.subscribe(seen.append)
        for key in ("A", "B", "C"):
            with backend() as uow:
                create(uow, key)
        with backend(readonly=True) as uow:
            titles = [
                row.title
                for row in uow.conn().execute(
                    text("SELECT title FROM cur_core_record ORDER BY title")
                )
            ]
        head = backend.ledger.head_seq()
    assert titles == ["A", "B", "C"]
    assert head == 3
    assert [e.seq for e in seen] == [1, 2, 3]


def test_the_readonly_unit_of_work_refuses_a_write(target: DbTarget) -> None:
    with open_backend(target) as backend, backend(True) as uow:
        with pytest.raises(RuntimeError, match="read-only"):
            create(uow, "X")


def test_the_read_connection_is_one_snapshot(target: DbTarget) -> None:
    with open_backend(target) as backend:
        with backend() as uow:
            create(uow, "A")
        with backend.read_connection() as conn:
            before = conn.execute(text("SELECT COUNT(*) FROM events")).scalar()
            with backend() as uow:  # a commit made after the snapshot began
                create(uow, "B")
            after = conn.execute(text("SELECT COUNT(*) FROM events")).scalar()
        assert (before, after) == (1, 1)


def test_the_ledger_exists_only_after_the_schema_is_created(
    new_db: Callable[[], DbTarget],
) -> None:
    empty = new_db()
    assert ledger_exists(empty) is False
    create_schema(empty)
    assert ledger_exists(empty) is True


def test_the_display_name_never_carries_a_password(target: DbTarget) -> None:
    with open_backend(target) as backend:
        assert backend.display == display_target(target)
        assert "postgres:postgres@" not in backend.display


def test_closing_twice_is_harmless(target: DbTarget) -> None:
    backend = open_backend(target)
    backend.close()
    backend.close()


def test_as_target_keeps_a_url_whole_and_makes_a_path_of_anything_else(tmp_path: Path) -> None:
    url = "postgresql://u:p%40ss@db.example:5432/tl?sslmode=disable"
    assert as_target(url) == url
    assert as_target("postgres://u@h/d") == "postgres://u@h/d"
    assert is_postgres(as_target(url))
    assert as_target("./dev/data/tl.db") == Path("./dev/data/tl.db")
    assert as_target(str(tmp_path / "x.db")) == tmp_path / "x.db"
    assert not is_postgres(as_target(tmp_path / "x.db"))


def test_an_unreachable_server_is_a_named_error_without_the_password() -> None:
    url = "postgresql://someone:hunter2@127.0.0.1:1/tl?sslmode=disable"
    with pytest.raises(BackendUnavailableError) as raised:
        open_backend(url)
    assert "hunter2" not in str(raised.value)
    assert "127.0.0.1" in str(raised.value)
    with pytest.raises(BackendUnavailableError) as raised_exists:
        ledger_exists(url)
    assert "hunter2" not in str(raised_exists.value)


@pytest.mark.requires_postgres
def test_sslmode_in_the_url_reaches_the_driver(pg_db: str) -> None:
    create_schema(pg_db)
    join = "&" if "?" in pg_db else "?"
    for mode in ("disable", "require"):
        with open_backend(f"{pg_db}{join}sslmode={mode}") as backend:
            with backend() as uow:
                create(uow, f"S-{mode}")
    with pytest.raises(ValueError, match="sslmode"):
        open_backend(f"{pg_db}{join}sslmode=prefer")
