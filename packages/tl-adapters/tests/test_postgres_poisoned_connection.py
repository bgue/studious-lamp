"""A parameter the driver cannot encode does not poison the pool (P1-I0 security re-review).

A lone surrogate in a bound parameter makes pg8000 fail half way through a message. Before the
fix the connection went back to the pool out of step with the server and every later statement on
it failed. The engine now discards that one connection.
"""

from __future__ import annotations

import os

import pytest
from sqlalchemy import text
from tl_adapters.postgres.engine import make_engine

pytestmark = pytest.mark.requires_postgres


def test_an_unencodable_parameter_fails_alone_and_the_pool_stays_usable(
    pg_base_url: str | None,
) -> None:
    if pg_base_url is None:
        if os.environ.get("TL_REQUIRE_POSTGRES") == "1":
            pytest.fail("Postgres is not reachable at TL_PG_URL")
        pytest.skip("Postgres is not reachable at TL_PG_URL")
    engine = make_engine(pg_base_url, pooled=True)
    try:
        for _ in range(7):  # more than the pool size, so a poisoned connection would be reused
            with pytest.raises(UnicodeEncodeError), engine.connect() as conn:
                conn.execute(text("SELECT :x"), {"x": "\ud800"})
        for _ in range(15):
            with engine.connect() as conn:
                assert conn.execute(text("SELECT 1")).scalar() == 1
    finally:
        engine.dispose()
