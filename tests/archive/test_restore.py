"""Restore from an archive: verbatim events, rebuilt projections, identical on both dialects.

The history is made with the real services, sealed into a store, and restored into an empty
database. ``cur_*`` tables and event hashes of the restored database must equal the original's,
whichever of SQLite and Postgres each side is.
"""

from __future__ import annotations

import re
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy import text
from tl_adapters import postgres, sqlite
from tl_adapters.db import DbTarget, create_schema, make_engine, open_uow, read_tx, write_tx
from tl_adapters.restore import restore_from_archive
from tl_core.archive import (
    Ed25519Signer,
    RestoreError,
    generate_signer,
    seal_segment,
    verify_archive,
)
from tl_core.archive.segments import NDJSON
from tl_core.projection.defaults import default_registry
from tl_core.schema_provider import DirectorySchemaProvider, use_provider
from tl_core.services.commands import CreateRecord, UpdateRecord, VoidRecord
from tl_core.services.links import AddLink, SuggestLink, handle_add_link, handle_suggest_link
from tl_core.services.psets import SetPsetValues, handle_set_pset_values
from tl_core.services.records import (
    handle_create_record,
    handle_update_record,
    handle_void_record,
)

FIXTURES = Path(__file__).resolve().parents[2] / "schema" / "fixtures"
SCOPE = "project:P123"
Store = Any


@pytest.fixture(autouse=True)
def fixture_schemas() -> Iterator[None]:
    with use_provider(DirectorySchemaProvider(FIXTURES)):
        yield


def populate(db: DbTarget) -> None:
    """Records in three scopes, an update, a void, pset values and two links."""

    def create(key: str, scope: str = SCOPE) -> Any:
        cmd = CreateRecord(
            actor="user:u-1",
            source="test",
            scope=scope,
            record_type="core.Record",
            title=f"Record {key}",
            key=key,
        )
        with open_uow(db) as uow:
            return handle_create_record(uow, cmd)

    first, second, third, fourth = (create(f"R-{n}") for n in range(1, 5))
    create("Q-1", "project:P2")
    create("C-1", "company")
    with open_uow(db) as uow:
        handle_set_pset_values(
            uow,
            SetPsetValues(
                actor="user:u-1",
                source="test",
                scope=SCOPE,
                stream_id=first.stream_id,
                expected_version=first.version,
                pset="valve_data",
                layer="standard",
                values={"size_in": 4, "manufacturer": "Acme"},
            ),
        )
    with open_uow(db) as uow:
        handle_update_record(
            uow,
            UpdateRecord(
                actor="user:u-2",
                source="test",
                scope=SCOPE,
                stream_id=second.stream_id,
                expected_version=second.version,
                changes={"title": "Café – renamed"},
            ),
        )
    with open_uow(db) as uow:
        handle_void_record(
            uow,
            VoidRecord(
                actor="user:u-2",
                source="test",
                scope=SCOPE,
                stream_id=third.stream_id,
                expected_version=third.version,
                reason="duplicate",
            ),
        )
    with open_uow(db) as uow:
        handle_add_link(
            uow,
            AddLink(
                actor="user:u-1",
                source="test",
                scope=SCOPE,
                from_id=first.stream_id,
                to_id=second.stream_id,
            ),
        )
    with open_uow(db) as uow:
        handle_suggest_link(
            uow,
            SuggestLink(
                actor="user:u-1",
                source="test",
                scope=SCOPE,
                from_id=first.stream_id,
                to_id=fourth.stream_id,
                confidence=0.5,
            ),
        )


def seal_all(db: DbTarget, store: Store, signer: Ed25519Signer, *, max_events: int = 5) -> int:
    engine = make_engine(db)
    try:
        sealed = 0
        while True:
            with read_tx(engine) as conn:
                if seal_segment(conn, store, signer, max_events=max_events) is None:
                    return sealed
            sealed += 1
    finally:
        engine.dispose()


def current_tables(dialect: str) -> list[str]:
    names: list[str] = []
    for projector in default_registry().all():
        for statement in projector.ddl(dialect):
            found = re.match(r"\s*CREATE TABLE IF NOT EXISTS (cur_\w+)", statement)
            if found:
                names.append(found.group(1))
    return sorted(set(names))


def snapshot(db: DbTarget) -> dict[str, list[tuple[Any, ...]]]:
    """Every ``cur_*`` table's rows, sorted, plus the ledger's (seq, hash) pairs."""
    dialect = "postgres" if str(db).startswith("postgresql://") else "sqlite"
    engine = make_engine(db)
    try:
        with read_tx(engine) as conn:
            out: dict[str, list[tuple[Any, ...]]] = {}
            for table in current_tables(dialect):
                found = conn.execute(text(f"SELECT * FROM {table}")).mappings().all()
                rows = [tuple(sorted(dict(row).items())) for row in found]
                out[table] = sorted(rows, key=repr)
            out["events"] = [
                tuple(row)
                for row in conn.execute(
                    text("SELECT seq, hash, prev_hash FROM events ORDER BY seq")
                )
            ]
            return out
    finally:
        engine.dispose()


def event_rows(db: DbTarget) -> list[tuple[Any, ...]]:
    engine = make_engine(db)
    try:
        with read_tx(engine) as conn:
            return [
                tuple(row) for row in conn.execute(text("SELECT * FROM events ORDER BY seq")).all()
            ]
    finally:
        engine.dispose()


def test_a_restore_reproduces_the_projections_and_the_hash_chain(
    new_db: Callable[[], DbTarget], memory_store: Callable[..., Any]
) -> None:
    signer = generate_signer()
    original = new_db()
    create_schema(original)
    populate(original)
    store = memory_store()
    segments = seal_all(original, store, signer)
    assert segments >= 3

    restored = new_db()
    result = restore_from_archive(store, restored, public_key=signer.public_key)

    assert result.segments == segments
    before, after = snapshot(original), snapshot(restored)
    assert before.keys() == after.keys() and len(before["cur_core_record"]) == 6
    assert before == after
    assert event_rows(original) == event_rows(restored)  # verbatim: every column, not just hashes


@pytest.mark.requires_postgres
@pytest.mark.parametrize(("source", "target"), [("sqlite", "postgres"), ("postgres", "sqlite")])
def test_restore_across_dialects_gives_identical_tables_and_hashes(
    source: str, target: str, tmp_path: Path, pg_db: str, memory_store: Callable[..., Any]
) -> None:
    targets: dict[str, DbTarget] = {"sqlite": tmp_path / "s.db", "postgres": pg_db}
    other_sqlite = tmp_path / "t.db"
    signer = generate_signer()
    original = targets[source]
    create_schema(original)
    populate(original)
    store = memory_store()
    seal_all(original, store, signer, max_events=9)

    # The same archive restores into the other dialect and into a second database of its own.
    into_other = other_sqlite if target == "sqlite" else _fresh_postgres(pg_db)
    restore_from_archive(store, into_other, public_key=signer.public_key)

    assert snapshot(original) == snapshot(into_other)
    assert event_rows(original) == event_rows(into_other)
    engine = make_engine(into_other)
    try:
        with read_tx(engine) as conn:
            assert verify_archive(store, public_key=signer.public_key, conn=conn) == []
    finally:
        engine.dispose()


def _fresh_postgres(url: str) -> str:
    """Another empty schema next to ``url``'s (the fixture drops only its own)."""
    import uuid

    from tl_adapters.postgres import admin

    schema = "tl_t_" + uuid.uuid4().hex[:16]
    base = re.sub(r"\?.*$", "", url)
    admin.create_schema_namespace(base, schema)
    _extra_schemas.append((base, schema))
    return admin.schema_url(base, schema)


_extra_schemas: list[tuple[str, str]] = []


@pytest.fixture(autouse=True)
def _drop_extra_schemas() -> Iterator[None]:
    yield
    from tl_adapters.postgres import admin

    while _extra_schemas:
        base, schema = _extra_schemas.pop()
        admin.drop_schema_namespace(base, schema)


def test_restore_refuses_a_database_that_already_has_events(
    new_db: Callable[[], DbTarget], memory_store: Callable[..., Any]
) -> None:
    signer = generate_signer()
    original = new_db()
    create_schema(original)
    populate(original)
    store = memory_store()
    seal_all(original, store, signer)
    with pytest.raises(RestoreError, match="not empty"):
        restore_from_archive(store, original, public_key=signer.public_key)


def test_restore_refuses_a_tampered_archive_and_writes_nothing(
    new_db: Callable[[], DbTarget], memory_store: Callable[..., Any]
) -> None:
    signer = generate_signer()
    original = new_db()
    create_schema(original)
    populate(original)
    store = memory_store()
    seal_all(original, store, signer)
    key = next(k for k in store.list_keys("segments/") if k.endswith(NDJSON))
    store.overwrite(key, store.get_bytes(key).replace(b"Record", b"Recorp", 1))

    target = new_db()
    with pytest.raises(RestoreError) as caught:
        restore_from_archive(store, target, public_key=signer.public_key)
    assert caught.value.issue is not None and caught.value.issue.kind == "file_hash"
    engine = make_engine(target)
    try:
        # create_schema never ran: a refused archive leaves the target untouched.
        with pytest.raises(Exception, match="events"):
            with read_tx(engine) as conn:
                conn.execute(text("SELECT COUNT(*) FROM events"))
    finally:
        engine.dispose()


def test_restore_events_demands_gap_free_seqs_from_one(
    new_db: Callable[[], DbTarget], memory_store: Callable[..., Any]
) -> None:
    signer = generate_signer()
    original = new_db()
    create_schema(original)
    populate(original)
    store = memory_store()
    seal_all(original, store, signer)
    from tl_core.archive import iter_segment_events

    events = list(iter_segment_events(store))
    target = new_db()
    create_schema(target)
    engine = make_engine(target)
    insert = (
        postgres.admin.restore_events
        if str(target).startswith("postg")
        else sqlite.admin.restore_events
    )
    try:
        with pytest.raises(RestoreError, match="seq 2 next"):
            with write_tx(engine) as conn:
                insert(conn, [events[0], events[2]])
        with write_tx(engine) as conn:  # the failed attempt rolled back completely
            assert insert(conn, events) == len(events)
        with pytest.raises(RestoreError, match="not empty"):
            with write_tx(engine) as conn:
                insert(conn, events)
    finally:
        engine.dispose()


# --- review round: one transaction, provider checked first, schema warnings -----------------


class Bomb:
    """A projector that fails on the third record, to force a failure during the replay."""

    name = "bomb"
    handles = frozenset({"Record.Created"})

    def __init__(self) -> None:
        self.seen = 0

    def ddl(self, dialect: str) -> list[str]:
        return []

    def reset(self, conn: Any) -> None:
        self.seen = 0

    def apply(self, conn: Any, event: Any) -> None:
        self.seen += 1
        if self.seen == 3:
            raise RuntimeError("boom")


def sealed_original(
    new_db: Callable[[], DbTarget], memory_store: Callable[..., Any]
) -> tuple[DbTarget, Store, Ed25519Signer]:
    signer = generate_signer()
    original = new_db()
    create_schema(original)
    populate(original)
    store = memory_store()
    seal_all(original, store, signer)
    return original, store, signer


def count_events(db: DbTarget) -> int:
    engine = make_engine(db)
    try:
        with read_tx(engine) as conn:
            return int(conn.execute(text("SELECT COUNT(*) FROM events")).scalar_one())
    finally:
        engine.dispose()


def test_a_failure_during_the_replay_rolls_everything_back_and_a_rerun_works(
    new_db: Callable[[], DbTarget], memory_store: Callable[..., Any]
) -> None:
    original, store, signer = sealed_original(new_db, memory_store)
    target = new_db()
    registry = default_registry()
    registry.register(Bomb())
    with pytest.raises(RuntimeError, match="boom"):
        restore_from_archive(store, target, public_key=signer.public_key, registry=registry)
    assert count_events(target) == 0  # the events went back with the failed replay

    result = restore_from_archive(store, target, public_key=signer.public_key)
    assert result.events == count_events(original)
    assert snapshot(target) == snapshot(original)


class Refusing:
    def effective(self, scope: str) -> Any:
        raise ValueError(f"no packages for {scope}")

    def scopes(self) -> list[str]:
        return []


def test_an_unloadable_schema_is_found_before_anything_is_written(
    new_db: Callable[[], DbTarget], memory_store: Callable[..., Any]
) -> None:
    _, store, signer = sealed_original(new_db, memory_store)
    target = new_db()
    with pytest.raises(RestoreError, match="nothing was written"):
        restore_from_archive(
            store, target, public_key=signer.public_key, schema_provider=Refusing()
        )
    if not str(target).startswith("postgresql://"):
        assert not Path(str(target)).exists()  # not even the SQLite file was created


class OtherHashes:
    """The real provider, but every effective schema reports a different hash."""

    def __init__(self, inner: Any) -> None:
        self.inner = inner

    def effective(self, scope: str) -> Any:
        return self.inner.effective(scope).model_copy(update={"hash": "f" * 64})

    def scopes(self) -> list[str]:
        return self.inner.scopes()


def test_restore_reports_the_schema_hashes_and_warns_when_they_differ_from_the_ledger(
    new_db: Callable[[], DbTarget], memory_store: Callable[..., Any]
) -> None:
    from tl_core.schema_provider import get_provider

    _, store, signer = sealed_original(new_db, memory_store)
    same = restore_from_archive(store, new_db(), public_key=signer.public_key)
    assert same.warnings == ()
    assert set(same.schema_hashes) == {"company", SCOPE, "project:P2"}
    assert same.ledger_schema_hashes == {SCOPE: same.schema_hashes[SCOPE]}  # one pset write

    other = restore_from_archive(
        store, new_db(), public_key=signer.public_key, schema_provider=OtherHashes(get_provider())
    )
    [warning] = other.warnings
    assert warning.startswith(f"scope {SCOPE}: the ledger last recorded effective schema ")
    assert "TL_SCHEMA_DIR" in warning
    assert other.schema_hashes[SCOPE] == "f" * 64
