"""``rebuild_projections``: resets dev projectors and replays the ledger; never writes events."""

from __future__ import annotations

import sqlite3
from contextlib import closing
from pathlib import Path
from typing import Any

import pytest
from dev_harness import DevHarness
from mcp.server.mcpserver.exceptions import ToolError
from sqlalchemy import text
from tl_adapters.db import make_engine, open_uow, read_tx, write_tx
from tl_core.services.commands import CreateRecord
from tl_core.services.records import handle_create_record
from tl_mcp.dev.guard import DevTarget


def sqlite_exec(path: Path, sql: str, *params: Any) -> None:
    with closing(sqlite3.connect(path)) as con, con:
        con.execute(sql, params)


def core_keys(env: DevHarness) -> list[str]:
    rows = env.structured("query_db", sql="SELECT key FROM cur_core_record ORDER BY key")["rows"]
    return [row[0] for row in rows]


def count(env: DevHarness, table: str) -> int:
    rows = env.structured("query_db", sql=f"SELECT count(*) FROM {table}")["rows"]
    return int(rows[0][0])


def damage_core_records(env: DevHarness) -> None:
    sqlite_exec(env.db, "DELETE FROM cur_core_record")


def insert_pset_sentinel(env: DevHarness) -> None:
    """One ``cur_pset_values`` row that no ledger event produced: it survives unless reset."""
    sqlite_exec(
        env.db,
        "INSERT INTO cur_pset_values (record_id, scope, path, pset, property_name, layer, "
        "value_type, value_text, last_seq, updated_at) "
        "VALUES ('sentinel', 'project:P123', 'p', 'ps', 'pn', 'l', 'text', 'x', 0, "
        "'2026-10-10T00:00:00Z')",
    )


@pytest.fixture
def ledger(dev_env: DevHarness) -> DevHarness:
    dev_env.create_record("K-1", "Record 1")
    dev_env.create_record("K-2", "Record 2")
    return dev_env


def test_a_rebuild_restores_the_projections_from_the_ledger(ledger: DevHarness) -> None:
    events_before = count(ledger, "events")
    damage_core_records(ledger)
    assert core_keys(ledger) == []

    out = ledger.structured("rebuild_projections")

    assert out["replayed"] >= 2
    assert "core_record" in out["projectors"]
    assert out["dialect"] == "sqlite"
    assert core_keys(ledger) == ["K-1", "K-2"]
    assert count(ledger, "events") == events_before


def test_only_the_named_projector_is_rebuilt(ledger: DevHarness) -> None:
    insert_pset_sentinel(ledger)
    damage_core_records(ledger)

    out = ledger.structured("rebuild_projections", only=["core_record"])

    assert out["projectors"] == ["core_record"]
    assert core_keys(ledger) == ["K-1", "K-2"]
    assert count(ledger, "cur_pset_values") == 1  # not rebuilt, so the sentinel stays


def test_an_unknown_projector_is_refused_and_changes_nothing(ledger: DevHarness) -> None:
    damage_core_records(ledger)
    events_before = count(ledger, "events")

    with pytest.raises(ToolError) as caught:
        ledger.call("rebuild_projections", only=["nope"])

    assert "core_record" in str(caught.value)
    assert core_keys(ledger) == []  # nothing was rebuilt
    assert count(ledger, "events") == events_before


def test_a_missing_database_is_reported_and_not_created(tmp_path: Path) -> None:
    env = DevHarness.build(tmp_path, create=False)

    with pytest.raises(ToolError, match="does not exist"):
        env.call("rebuild_projections")

    assert not (tmp_path / "tl.db").exists()
    assert env.audit_lines()[-1]["outcome"] == "error"


def test_the_list_of_names_is_bounded(ledger: DevHarness) -> None:
    with pytest.raises(ToolError):
        ledger.call("rebuild_projections", only=["core_record"] * 21)
    with pytest.raises(ToolError):
        ledger.call("rebuild_projections", only=["x" * 65])


def test_every_call_is_audited_with_its_outcome(ledger: DevHarness) -> None:
    ledger.structured("rebuild_projections")
    with pytest.raises(ToolError):
        ledger.call("rebuild_projections", only=["nope"])

    lines = ledger.audit_lines()
    assert [(line["tool"], line["outcome"]) for line in lines] == [
        ("rebuild_projections", "ok"),
        ("rebuild_projections", "error"),
    ]


def create_postgres_record(url: str, key: str) -> None:
    with open_uow(url) as uow:
        handle_create_record(
            uow,
            CreateRecord(
                actor="user:seed",
                source="test",
                scope="project:P123",
                record_type="core.Record",
                title=f"Record {key}",
                key=key,
            ),
        )


def pg_keys(url: str) -> list[str]:
    engine = make_engine(url)
    try:
        with read_tx(engine) as conn:
            rows = conn.execute(text("SELECT key FROM cur_core_record ORDER BY key")).all()
    finally:
        engine.dispose()
    return [str(row[0]) for row in rows]


def pg_count(url: str, table: str) -> int:
    engine = make_engine(url)
    try:
        with read_tx(engine) as conn:
            return int(conn.execute(text(f"SELECT count(*) FROM {table}")).scalar_one())
    finally:
        engine.dispose()


@pytest.mark.requires_postgres
def test_postgres_rebuild_restores_the_projections_from_the_ledger(
    tmp_path: Path, dev_pg_target: DevTarget
) -> None:
    url = str(dev_pg_target.db_arg)
    create_postgres_record(url, "PG-1")
    create_postgres_record(url, "PG-2")
    engine = make_engine(url)
    try:
        with write_tx(engine) as conn:
            conn.execute(text("DELETE FROM cur_core_record"))
    finally:
        engine.dispose()
    env = DevHarness.build(tmp_path, target=dev_pg_target)
    # query_db is SQLite only (deviation C4): read the Postgres tables directly
    assert pg_keys(url) == []
    events_before = pg_count(url, "events")

    out = env.structured("rebuild_projections", only=["core_record"])

    assert out["dialect"] == "postgres" and out["replayed"] >= 2
    assert out["projectors"] == ["core_record"]
    assert pg_keys(url) == ["PG-1", "PG-2"]
    assert pg_count(url, "events") == events_before
