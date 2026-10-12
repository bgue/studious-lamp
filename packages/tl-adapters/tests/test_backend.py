"""``open_backend``: one backend from a SQLite path or a Postgres URL (P1-I0-S30).

Runs on the adapters named by ``--adapters`` (SQLite by default; ``just test-parity`` adds
Postgres).
"""

from __future__ import annotations

import ssl
from collections.abc import Callable
from pathlib import Path
from typing import Any, cast

import pytest
import sqlalchemy
from sqlalchemy import Engine, text
from sqlalchemy.exc import SQLAlchemyError
from tl_adapters.backend import (
    BackendUnavailableError,
    DatabaseBackend,
    connection_failure,
    ledger_exists,
    open_backend,
)
from tl_adapters.db import (
    DbTarget,
    as_target,
    create_schema,
    dialect_of,
    display_target,
    is_postgres,
    make_engine,
    target_key,
)
from tl_adapters.postgres import engine as pg_engine
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
    with open_backend(target) as backend:
        with backend(True) as uow, pytest.raises(RuntimeError, match="read-only"):
            create(uow, "X")
        # raw SQL is refused too, not only the ledger's append
        with pytest.raises(SQLAlchemyError), backend(True) as uow:
            uow.conn().execute(text("CREATE TABLE zz_readonly (x INTEGER)"))
        with pytest.raises(SQLAlchemyError), backend(True) as uow:
            uow.conn().execute(text("DELETE FROM cur_core_record"))


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


def test_the_read_connection_refuses_raw_sql_writes(target: DbTarget) -> None:
    with open_backend(target) as backend:
        with backend() as uow:
            create(uow, "A")
        for statement in (
            "CREATE TABLE zz_snapshot (x INTEGER)",
            "DELETE FROM cur_core_record",
            "UPDATE cur_core_record SET title = 'changed'",
        ):
            with pytest.raises(SQLAlchemyError), backend.read_connection() as conn:
                conn.execute(text(statement))
        with backend(True) as uow:  # nothing changed, and the connection is usable again
            titles = [
                r.title for r in uow.conn().execute(text("SELECT title FROM cur_core_record"))
            ]
        with backend() as uow:  # query_only does not stay on after a read connection
            create(uow, "B")
    assert titles == ["A"]


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


@pytest.mark.parametrize(
    "url",
    [
        "postgresql://u:pw@db.example/tl",
        "POSTGRESQL://u:pw@db.example/tl",
        "PostgreSQL://u:pw@db.example/tl",
        "postgres://u:pw@db.example/tl",
        "postgresql+pg8000://u:pw@db.example/tl",
    ],
)
def test_every_spelling_of_a_postgres_url_is_postgres(url: str) -> None:
    assert as_target(url) == url
    assert is_postgres(url)
    assert dialect_of(url) == "postgres"
    assert "pw" not in display_target(url)


@pytest.mark.parametrize(
    "url",
    [
        "mysql://u:SeCrEt@h/d",
        "sqlite://u:SeCrEt@h/d",
        "https://u:SeCrEt@h/d",
        "postgresql:///x",
        "postgresql://u:SeCr@Et@localhost/db",
        "postgresql://:SeCrEt@h/d",
    ],
)
def test_a_url_that_is_not_a_usable_postgres_url_is_refused_without_echoing_it(url: str) -> None:
    with pytest.raises(ValueError) as raised:
        as_target(url)
    assert "SeCr" not in str(raised.value)
    assert "Et@" not in str(raised.value)


@pytest.mark.parametrize("mode", ["bogus", "prefer", "allow", "REQUIRE"])
def test_an_unsupported_sslmode_is_refused_when_the_target_is_read(mode: str) -> None:
    with pytest.raises(ValueError, match="sslmode") as raised:
        as_target(f"postgresql://u:SeCrEt@h/d?sslmode={mode}")
    assert "SeCrEt" not in str(raised.value)
    for good in ("disable", "require", "verify-ca", "verify-full"):
        assert as_target(f"postgresql://u:pw@h/d?sslmode={good}")


def test_a_refused_url_never_becomes_a_directory(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    with pytest.raises(ValueError):
        as_target("postgresql+psycopg://u:SeCrEt@h/d")
    assert list(tmp_path.iterdir()) == []


def test_the_display_name_hides_every_way_a_password_can_be_written() -> None:
    assert "zzz" not in display_target("postgresql://u:p@h/d?password=zzz&sslmode=disable")
    assert "sslmode=disable" in display_target("postgresql://u:p@h/d?password=zzz&sslmode=disable")
    assert "zzz" not in display_target("postgresql://u@h/d?PASSWORD=zzz")
    assert "zzz" not in display_target("postgresql://u@h/d?sslpassword=zzz")
    unescaped = display_target("postgresql://u:SeCr@Et@localhost/db")
    assert "SeCr" not in unescaped and "Et" not in unescaped


def test_connection_failure_recognises_refused_logins_and_missing_databases() -> None:
    url = "postgresql://someone:hunter2@127.0.0.1:1/tl?sslmode=disable"
    engine = make_engine(url)
    with pytest.raises(SQLAlchemyError) as raised:
        engine.connect()
    engine.dispose()
    found = connection_failure(url, raised.value)
    assert found is not None and "hunter2" not in str(found)
    assert connection_failure("/tmp/x.db", Exception("x")) is None
    assert connection_failure(url, ValueError("not a connection problem")) is None


def tls_of(url: str, monkeypatch: pytest.MonkeyPatch) -> object:
    """The ``ssl_context`` the engine for ``url`` hands to the driver (nothing connects)."""
    seen: dict[str, object] = {}
    real = sqlalchemy.create_engine

    def spy(*args: Any, **kwargs: Any) -> Engine:
        connect_args = kwargs.get("connect_args")
        if isinstance(connect_args, dict):
            seen.update(cast(dict[str, object], connect_args))
        return real(*args, **kwargs)

    monkeypatch.setattr(pg_engine, "create_engine", spy, raising=False)
    DatabaseBackend(url).close()  # no probe: nothing connects until a transaction
    return seen.get("ssl_context")


@pytest.mark.parametrize("scheme", ["postgresql", "postgres", "POSTGRESQL"])
def test_sslmode_reaches_the_driver_as_the_documented_tls_policy(
    scheme: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    base = f"{scheme}://u:pw@db.example/tl"
    assert tls_of(base + "?sslmode=disable", monkeypatch) is False
    require = tls_of(base + "?sslmode=require", monkeypatch)
    assert isinstance(require, ssl.SSLContext)
    assert (require.verify_mode, require.check_hostname) == (ssl.CERT_NONE, False)
    ca = tls_of(base + "?sslmode=verify-ca", monkeypatch)
    assert isinstance(ca, ssl.SSLContext)
    assert (ca.verify_mode, ca.check_hostname) == (ssl.CERT_REQUIRED, False)
    full = tls_of(base + "?sslmode=verify-full", monkeypatch)
    assert isinstance(full, ssl.SSLContext)
    assert (full.verify_mode, full.check_hostname) == (ssl.CERT_REQUIRED, True)
    assert tls_of(base, monkeypatch) is None  # no sslmode: the driver default
    for refused in ("prefer", "allow"):
        with pytest.raises(ValueError, match="sslmode"):
            tls_of(base + f"?sslmode={refused}", monkeypatch)


@pytest.mark.parametrize(
    "query",
    [
        "host=evil.example",
        "port=5999",
        "hostaddr=10.0.0.9",
        "HOST=evil.example",
        "password=SeCrEt",
        "PASSWORD=SeCrEt",
        "sslpassword=SeCrEt",
        "connect_timeout=5",
        "user=other",
    ],
)
def test_a_query_parameter_the_adapter_does_not_understand_is_refused(query: str) -> None:
    with pytest.raises(ValueError, match="query parameter") as raised:
        as_target(f"postgresql://u:pw@db.example/tl?{query}")
    assert "SeCrEt" not in str(raised.value) and "evil" not in str(raised.value)
    for good in ("sslmode=disable", "options=-csearch_path%3Dx", "application_name=tl"):
        assert as_target(f"postgresql://u:pw@db.example/tl?{good}")


def test_two_spellings_of_one_server_share_a_session_key_and_two_servers_never_do() -> None:
    one = target_key(as_target("postgresql://u:pw@DB.Example:5432/tl"))
    assert one == target_key(as_target("postgres://u:other@db.example/tl?sslmode=require"))
    assert one == "pg:u@db.example:5432/tl"
    assert one != target_key(as_target("postgresql://u:pw@db.example:5433/tl"))
    assert one != target_key(as_target("postgresql://u:pw@db2.example/tl"))
    with pytest.raises(ValueError):  # a host= in the query string would alias another server
        as_target("postgresql://u:pw@db.example/tl?host=db2.example")


def test_the_key_and_the_display_never_hold_the_value_of_options_or_another_parameter() -> None:
    secret = "-csearch_path%3Dtop_secret_schema"
    url = f"postgresql://u:pw@db.example/tl?options={secret}&application_name=tl&sslmode=disable"
    key, shown = target_key(url), display_target(url)
    assert "top_secret_schema" not in key + shown and "pw@" not in shown
    assert key.startswith("pg:u@db.example:5432/tl?options=sha256:")
    assert "application_name=tl" in shown and "sslmode=disable" in shown
    assert "options=***" in shown
    # defensive: display_target is also called on text that as_target never saw
    for raw in ("password=SeCrEt", "PASSWORD=SeCrEt", "sslpassword=SeCrEt", "host=evil.example"):
        assert "SeCrEt" not in display_target(f"postgresql://u:pw@h/d?{raw}")
        assert "evil" not in display_target(f"postgresql://u:pw@h/d?{raw}")
