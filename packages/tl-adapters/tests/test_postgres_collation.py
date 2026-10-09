"""Text sorts the same on Postgres as on SQLite, whatever locale the cluster defaults to (P0-I5).

SQLite orders text bytewise. A Postgres database created with a locale-aware default (as most
server images are: ``en_US.utf8``) would put ``apple`` before ``Banana``. The generated DDL pins
``TEXT`` columns to ``COLLATE "C"``; this test builds such a database and checks the result.
"""

from __future__ import annotations

import os
import uuid
from collections.abc import Iterator

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from tl_adapters.db import create_schema, open_uow
from tl_adapters.postgres import admin
from tl_core.services.commands import CreateRecord
from tl_core.services.records import handle_create_record

pytestmark = pytest.mark.requires_postgres

TITLES = ["banana", "Banana", "apple", "Zed", "zed", "Éclair", "10", "9", "_x", "~y"]


@pytest.fixture
def icu_url(pg_base_url: str | None) -> Iterator[str]:
    server = os.environ.get("TL_PG_URL")
    if pg_base_url is None or server is None:
        pytest.skip("Postgres is not reachable at TL_PG_URL")
    name = "tl_pytest_icu_" + uuid.uuid4().hex[:8]
    try:
        admin.create_database(server, name, icu_locale="en-US")
    except DBAPIError:
        pytest.skip("this server cannot create an ICU-locale database")
    try:
        yield admin.database_url(server, name)
    finally:
        admin.drop_database(server, name)


def test_the_locale_database_really_sorts_differently_without_the_pin(icu_url: str) -> None:
    from sqlalchemy import create_engine
    from tl_adapters.postgres.engine import sqlalchemy_url

    engine = create_engine(sqlalchemy_url(icu_url))
    with engine.connect() as conn:
        rows = conn.execute(text("SELECT v FROM (VALUES ('Banana'), ('apple')) AS t(v) ORDER BY v"))
        assert [r.v for r in rows] == [
            "apple",
            "Banana",
        ]  # locale order; bytewise gives the reverse
    engine.dispose()


def test_generated_tables_order_text_bytewise_in_a_locale_aware_database(icu_url: str) -> None:
    create_schema(icu_url)
    with open_uow(icu_url) as uow:
        for n, title in enumerate(TITLES):
            handle_create_record(
                uow,
                CreateRecord(
                    actor="user:t",
                    source="test",
                    scope="project:P1",
                    record_type="core.Record",
                    title=title,
                    key=f"K-{n}",
                ),
            )
    with open_uow(icu_url, readonly=True) as uow:
        titles = [
            r.title
            for r in uow.conn().execute(text("SELECT title FROM cur_core_record ORDER BY title"))
        ]
    assert titles == sorted(TITLES)  # Python compares code points, which is UTF-8 byte order
