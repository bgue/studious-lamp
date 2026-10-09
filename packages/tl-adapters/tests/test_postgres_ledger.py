"""What is specific to the Postgres adapter: locking, loaders, triggers, wake-ups (P0-I5).

Behaviour shared with SQLite is covered by ``test_ledger.py`` and ``test_uow.py``, which run on
both adapters.
These tests need the server at ``TL_PG_URL`` and skip when it is unreachable.
"""

from __future__ import annotations

import threading
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from sqlalchemy import Engine, text
from sqlalchemy.exc import DBAPIError, IntegrityError
from tl_adapters.postgres import engine as pg_engine
from tl_adapters.postgres.ledger import PostgresLedger
from tl_adapters.postgres.notify import NotifyListener
from tl_adapters.sqlite.engine import make_engine as make_sqlite_engine
from tl_adapters.sqlite.ledger import SqliteLedger
from tl_core.changefeed import ChangePoller, SubscriptionRegistry
from tl_core.ledger import NewEvent
from tl_core.services.errors import LockTimeoutError

pytestmark = pytest.mark.requires_postgres

BASE_TIME = datetime(2026, 1, 1, tzinfo=UTC)
WAIT = 10.0


class FakeClock:
    def __init__(self) -> None:
        self.calls = 0

    def __call__(self) -> datetime:
        self.calls += 1
        return BASE_TIME + timedelta(seconds=self.calls, microseconds=self.calls)


class FakeIds:
    def __init__(self) -> None:
        self.calls = 0

    def __call__(self) -> str:
        self.calls += 1
        return f"E{self.calls:025d}"


def append(ledger: PostgresLedger | SqliteLedger, stream: str, expected: int, scope: str) -> None:
    ledger.append(
        stream_id=stream,
        stream_type="core.Record",
        scope=scope,
        expected_version=expected,
        events=[
            NewEvent(event_type="Record.Updated", payload={"n": expected, "t": "é", "f": 1e22})
        ],
        actor="user:dev",
        source="test",
        correlation_id="c",
    )


@pytest.fixture
def engine(pg_db: str) -> Engine:
    eng = pg_engine.make_engine(pg_db)
    PostgresLedger(eng).create_schema()
    return eng


def test_the_hash_chain_is_identical_to_sqlites_for_the_same_events(
    engine: Engine, tmp_path: Path
) -> None:
    pg = PostgresLedger(engine, clock=FakeClock(), id_gen=FakeIds())
    lite_engine = make_sqlite_engine(tmp_path / "lite.db")
    lite = SqliteLedger(lite_engine, clock=FakeClock(), id_gen=FakeIds())
    lite.create_schema()
    for ledger in (pg, lite):
        append(ledger, "a", 0, "project:A")
        append(ledger, "b", 0, "project:B")
        append(ledger, "a", 1, "project:A")
        append(ledger, "a", 2, "project:A")
    shape = [(e.seq, e.event_id, e.prev_hash, e.hash, e.payload) for e in pg.read_after(0)]
    assert shape == [
        (e.seq, e.event_id, e.prev_hash, e.hash, e.payload) for e in lite.read_after(0)
    ]
    assert len(shape) == 4 and shape[3][2] == shape[2][3]
    lite_engine.dispose()


def test_a_payload_survives_the_round_trip_byte_for_byte(engine: Engine) -> None:
    ledger = PostgresLedger(engine)
    append(ledger, "a", 0, "company")
    (event,) = ledger.read_stream("a")
    assert event.payload == {"n": 0, "t": "é", "f": 1e22}
    with engine.connect() as conn:
        stored = conn.execute(text("SELECT payload FROM events")).scalar_one()
    assert stored == '{"f":1e+22,"n":0,"t":"é"}'  # canonical JSON text, not re-rendered JSONB


def test_truncate_is_rejected_like_update_and_delete(engine: Engine) -> None:
    append(PostgresLedger(engine), "a", 0, "company")
    for statement in ("TRUNCATE events", "DELETE FROM events", "UPDATE events SET actor = 'x'"):
        with pytest.raises(IntegrityError, match="append-only"), engine.begin() as conn:
            conn.execute(text(statement))
    assert PostgresLedger(engine).head_seq() == 1


def test_a_rolled_back_append_leaves_no_gap_in_seq(engine: Engine) -> None:
    ledger = PostgresLedger(engine)
    append(ledger, "a", 0, "company")
    with pytest.raises(RuntimeError, match="abort"), pg_engine.write_tx(engine) as conn:
        ledger.append_in(
            conn,
            stream_id="b",
            stream_type="core.Record",
            scope="company",
            expected_version=0,
            events=[NewEvent(event_type="Record.Created", payload={})],
            actor="user:dev",
            source="test",
            correlation_id="c",
        )
        raise RuntimeError("abort")
    append(ledger, "c", 0, "company")
    assert [e.seq for e in ledger.read_after(0)] == [1, 2]


def test_a_write_transaction_holds_everyone_else_off_until_it_commits(engine: Engine) -> None:
    first_in, release, second_in = threading.Event(), threading.Event(), threading.Event()

    def first() -> None:
        with pg_engine.write_tx(engine):
            first_in.set()
            assert release.wait(WAIT)

    def second() -> None:
        with pg_engine.write_tx(engine):
            second_in.set()

    t1 = threading.Thread(target=first, daemon=True)
    t2 = threading.Thread(target=second, daemon=True)
    t1.start()
    assert first_in.wait(WAIT)
    t2.start()
    assert not second_in.wait(0.5), "a second writer entered while the first held the lock"
    release.set()
    assert second_in.wait(WAIT)
    t1.join(WAIT)
    t2.join(WAIT)


def test_a_write_transaction_reads_what_the_previous_writer_committed(engine: Engine) -> None:
    """Guard reads inside a write transaction cannot go stale (LEARNINGS L-P0-I3-O2, fanout A2).

    The lock is taken before the first read, so a writer that waited for another sees that
    writer's commit; no ``SELECT ... FOR UPDATE`` is needed on top.
    """
    with engine.begin() as conn:
        conn.execute(text("CREATE TABLE guard_links (id int PRIMARY KEY)"))
        conn.execute(text("INSERT INTO guard_links VALUES (1)"))
    holding, release = threading.Event(), threading.Event()
    seen: list[int] = []

    def retract() -> None:
        with pg_engine.write_tx(engine) as conn:
            conn.execute(text("DELETE FROM guard_links WHERE id = 1"))
            holding.set()
            assert release.wait(WAIT)

    def guard() -> None:
        with pg_engine.write_tx(engine) as conn:  # blocks until the retraction commits
            seen.append(conn.execute(text("SELECT count(*) FROM guard_links")).scalar_one())

    first = threading.Thread(target=retract, daemon=True)
    second = threading.Thread(target=guard, daemon=True)
    first.start()
    assert holding.wait(WAIT)
    second.start()
    time.sleep(0.3)  # the guard transaction is now waiting for the lock
    release.set()
    first.join(WAIT)
    second.join(WAIT)
    assert seen == [0]


def test_readers_never_wait_for_a_writer(engine: Engine) -> None:
    ledger = PostgresLedger(engine)
    append(ledger, "a", 0, "company")
    done = threading.Event()

    def read() -> None:
        assert ledger.head_seq() == 1  # the writer's uncommitted event is invisible
        done.set()

    with pg_engine.write_tx(engine) as conn:
        ledger.append_in(
            conn,
            stream_id="b",
            stream_type="core.Record",
            scope="company",
            expected_version=0,
            events=[NewEvent(event_type="Record.Created", payload={})],
            actor="user:dev",
            source="test",
            correlation_id="c",
        )
        reader = threading.Thread(target=read, daemon=True)
        reader.start()
        assert done.wait(WAIT), "a reader waited for the writer"
    reader.join(WAIT)
    assert ledger.head_seq() == 2


def test_waiting_for_the_lock_times_out_instead_of_hanging(
    engine: Engine, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(pg_engine, "LOCK_TIMEOUT", "200ms")
    with pg_engine.write_tx(engine):
        started = time.monotonic()
        with pytest.raises(LockTimeoutError), pg_engine.write_tx(engine):
            pass
        assert time.monotonic() - started < WAIT


def test_the_driver_hands_back_what_sqlite_would(engine: Engine) -> None:
    with pg_engine.read_tx(engine) as conn:
        row = conn.execute(
            text(
                "SELECT TIMESTAMPTZ '2026-01-01 02:00:00+02' AS ts, "
                '\'{"bb": 1, "a": [1.5, null], "é": true}\'::jsonb AS j, '
                "TRUE AS b, (SELECT SUM(x) FROM (VALUES (1), (2)) AS t(x)) AS total, "
                "1.5::numeric AS frac"
            )
        ).one()
    assert row.ts == "2026-01-01T00:00:00.000000+00:00"
    assert row.j == '{"a":[1.5,null],"bb":1,"é":true}'  # canonical compact text, like SQLite's
    assert row.b == 1 and type(row.b) is int
    assert row.total == 3 and type(row.total) is int
    assert row.frac == 1.5 and type(row.frac) is float


def test_read_transactions_cannot_write(engine: Engine) -> None:
    with pytest.raises(DBAPIError, match="read-only"), pg_engine.read_tx(engine) as conn:
        conn.execute(text("CREATE TABLE nope (x int)"))


def test_two_schemas_do_not_see_each_other(pg_db: str, pg_base_url: str | None) -> None:
    from tl_adapters.postgres import admin

    assert pg_base_url is not None
    other = admin.schema_url(pg_base_url, "tl_t_other_" + pg_db[-8:].replace("%", "").lower())
    name = other.split("csearch_path%3D")[1]
    admin.create_schema_namespace(pg_base_url, name)
    try:
        a, b = pg_engine.make_engine(pg_db), pg_engine.make_engine(other)
        PostgresLedger(a).create_schema()
        PostgresLedger(b).create_schema()
        append(PostgresLedger(a), "s", 0, "company")
        assert PostgresLedger(a).head_seq() == 1
        assert PostgresLedger(b).head_seq() == 0
        a.dispose()
        b.dispose()
    finally:
        admin.drop_schema_namespace(pg_base_url, name)


def test_a_commit_wakes_a_listener_but_a_rollback_does_not(pg_db: str, engine: Engine) -> None:
    wake = threading.Event()
    ledger = PostgresLedger(engine)
    with NotifyListener(pg_db, wake) as listener:
        wake.clear()
        with pytest.raises(RuntimeError, match="abort"), pg_engine.write_tx(engine) as conn:
            ledger.append_in(
                conn,
                stream_id="x",
                stream_type="core.Record",
                scope="company",
                expected_version=0,
                events=[NewEvent(event_type="Record.Created", payload={})],
                actor="user:dev",
                source="test",
                correlation_id="c",
            )
            assert not wake.wait(0.5), "woken before the commit"
            raise RuntimeError("abort")
        assert not wake.wait(0.5), "woken by a rollback"
        append(ledger, "y", 0, "company")
        assert wake.wait(WAIT)
        assert listener.notifications == 1


def test_a_commit_in_another_schema_does_not_wake_the_listener(
    pg_db: str, pg_base_url: str | None
) -> None:
    from tl_adapters.postgres import admin

    assert pg_base_url is not None
    name = "tl_t_noise_" + pg_db[-6:].replace("%", "").lower()
    admin.create_schema_namespace(pg_base_url, name)
    noisy = pg_engine.make_engine(admin.schema_url(pg_base_url, name))
    try:
        PostgresLedger(noisy).create_schema()
        wake = threading.Event()
        with NotifyListener(pg_db, wake):
            wake.clear()
            append(PostgresLedger(noisy), "n", 0, "company")
            assert not wake.wait(1.0)
    finally:
        noisy.dispose()
        admin.drop_schema_namespace(pg_base_url, name)


def test_a_poller_with_a_wake_event_delivers_promptly_and_loses_nothing(
    pg_db: str, engine: Engine
) -> None:
    ledger = PostgresLedger(engine)
    registry = SubscriptionRegistry()
    seen: list[int] = []
    registry.subscribe(lambda e: seen.append(e.seq), after_seq=0)
    wake = threading.Event()
    writers, per_writer = 3, 15

    def write(name: str) -> None:
        for i in range(per_writer):
            append(ledger, f"{name}-{i}", 0, "company")

    with (
        NotifyListener(pg_db, wake),
        ChangePoller(ledger, registry, after_seq=0, interval_s=30, wake=wake),
    ):
        threads = [threading.Thread(target=write, args=(f"w{n}",)) for n in range(writers)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(WAIT)
        deadline = time.monotonic() + WAIT
        while len(seen) < writers * per_writer and time.monotonic() < deadline:
            time.sleep(0.02)
    # A 30 s interval means only wake-ups could have delivered these in time.
    assert seen == list(range(1, writers * per_writer + 1))


def test_commit_order_is_seq_order_under_concurrent_writers(engine: Engine) -> None:
    """Seq 9 is never visible after seq 10 (LEARNINGS L-P0-I4-A2): a poller can trust its cursor."""
    ledger = PostgresLedger(engine)
    stop = threading.Event()
    violations: list[tuple[int, int]] = []

    def watch() -> None:
        highest = 0
        while not stop.is_set():
            seqs = [e.seq for e in ledger.read_after(0, limit=10_000)]
            if seqs and seqs != list(range(1, len(seqs) + 1)):
                violations.append((highest, len(seqs)))  # a hole: a later seq visible early
            highest = max(highest, len(seqs))

    watcher = threading.Thread(target=watch, daemon=True)
    watcher.start()

    def write(name: str) -> None:
        for i in range(25):
            append(ledger, f"{name}-{i}", 0, "company")

    writers = [threading.Thread(target=write, args=(f"w{n}",)) for n in range(4)]
    for thread in writers:
        thread.start()
    for thread in writers:
        thread.join(WAIT * 3)
    stop.set()
    watcher.join(WAIT)
    assert violations == []
    assert ledger.head_seq() == 100


def test_writers_still_serialise_when_the_server_defaults_to_repeatable_read(
    pg_db: str, pg_base_url: str | None
) -> None:
    """Write transactions pin READ COMMITTED.

    A stricter server default must not make a writer that waited for the lock work from a snapshot
    older than the lock grant (it would fail on the key).
    """
    from sqlalchemy import create_engine
    from sqlalchemy.engine import make_url
    from sqlalchemy.pool import NullPool
    from tl_adapters.postgres.engine import sqlalchemy_url

    assert pg_base_url is not None
    database = make_url(sqlalchemy_url(pg_base_url)).database or ""
    if not database.startswith("tl_pytest_"):
        pytest.skip("changing the server default is only safe in the throw-away test database")
    admin_engine = create_engine(
        sqlalchemy_url(pg_base_url), poolclass=NullPool, isolation_level="AUTOCOMMIT"
    )
    with admin_engine.connect() as conn:
        conn.exec_driver_sql(
            f"ALTER DATABASE \"{database}\" SET default_transaction_isolation = 'repeatable read'"
        )
    admin_engine.dispose()
    engine = pg_engine.make_engine(pg_db)
    ledger = PostgresLedger(engine)
    ledger.create_schema()
    errors: list[BaseException] = []

    def write(name: str) -> None:
        try:
            for i in range(10):
                append(ledger, f"{name}-{i}", 0, "company")
        except BaseException as exc:
            errors.append(exc)

    threads = [threading.Thread(target=write, args=(f"w{n}",)) for n in range(6)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(WAIT * 3)
    assert errors == []
    assert [e.seq for e in ledger.read_after(0, limit=1000)] == list(range(1, 61))
    engine.dispose()


def test_a_listener_reconnects_after_its_backend_is_killed(pg_db: str, engine: Engine) -> None:
    wake = threading.Event()
    ledger = PostgresLedger(engine)
    with NotifyListener(pg_db, wake) as listener:
        assert listener.connections == 1
        with engine.connect() as conn:
            killed = conn.execute(
                text(
                    "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
                    "WHERE application_name = 'tl-listener' AND datname = current_database()"
                )
            ).all()
        assert killed
        deadline = time.monotonic() + WAIT
        while listener.connections < 2 and time.monotonic() < deadline:
            time.sleep(0.05)
        assert listener.connections == 2  # reconnected and listening again
        wake.clear()
        append(ledger, "after", 0, "company")
        assert wake.wait(WAIT)
