"""Housekeeping for throw-away test databases (P0-I5)."""

from __future__ import annotations

import os
import time

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.pool import NullPool
from tl_adapters.postgres import admin
from tl_adapters.postgres.engine import sqlalchemy_url

pytestmark = pytest.mark.requires_postgres


def exists(server: str, name: str) -> bool:
    engine = create_engine(sqlalchemy_url(server), poolclass=NullPool)
    try:
        with engine.connect() as conn:
            return bool(
                conn.execute(
                    text("SELECT 1 FROM pg_database WHERE datname = :n"), {"n": name}
                ).first()
            )
    finally:
        engine.dispose()


def test_names_record_their_age_and_are_unique() -> None:
    first, second = admin.test_database_name(), admin.test_database_name("icu")
    assert first != second
    assert first.startswith("tl_pytest_") and second.startswith("tl_pytest_icu_")


def test_the_sweep_drops_only_old_idle_test_databases(pg_base_url: str | None) -> None:
    server = os.environ.get("TL_PG_URL", admin.DEFAULT_URL)
    if pg_base_url is None:
        pytest.skip("Postgres is not reachable at TL_PG_URL")
    old = f"tl_pytest_{int(time.time()) - 10 * 3600:08x}_abcdef"
    busy = f"tl_pytest_{int(time.time()) - 10 * 3600:08x}_abcde0"
    fresh = admin.test_database_name()
    stranger = "tl_pytest_not_made_by_us"
    for name in (old, busy, fresh, stranger):
        admin.create_database(server, name)
    holder = create_engine(
        sqlalchemy_url(admin.database_url(server, busy)), poolclass=NullPool
    ).connect()
    try:
        dropped = admin.sweep_stale_databases(server)
        assert old in dropped and busy not in dropped
        assert not exists(server, old)
        assert exists(server, busy) and exists(server, fresh) and exists(server, stranger)
    finally:
        holder.close()
        for name in (old, busy, fresh, stranger):
            admin.drop_database(server, name)
