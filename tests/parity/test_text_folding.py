"""Case-insensitive matching folds ASCII only, on both adapters (P0-I5, README-A D13).

SQLite's ``LOWER`` folds ASCII letters only. Generated Postgres ``TEXT`` columns are
``COLLATE "C"``, whose ctype is ASCII-only too, so ``LOWER``, ``LIKE`` over ``LOWER`` and the
query language's ``~`` behave the same on both: ``Weld`` matches ``weld``, but ``É`` does not
match ``é``.
"""

from __future__ import annotations

from collections.abc import Callable

import pytest
from tl_adapters.db import DbTarget, create_schema, open_uow
from tl_core.query import QuerySpec, parse, run_query
from tl_core.services.commands import CreateRecord
from tl_core.services.records import handle_create_record

SCOPE = "project:P1"
TITLES = {"R-1": "Weld ÉCLAIR", "R-2": "weld éclair", "R-3": "WELD", "R-4": "other"}


@pytest.fixture
def seeded(new_db: Callable[[], DbTarget]) -> DbTarget:
    target = new_db()
    create_schema(target)
    with open_uow(target) as uow:
        for key, title in TITLES.items():
            handle_create_record(
                uow,
                CreateRecord(
                    actor="user:t",
                    source="test",
                    scope=SCOPE,
                    record_type="core.Record",
                    title=title,
                    key=key,
                ),
            )
    return target


def keys_for(target: DbTarget, query: str) -> list[str]:
    with open_uow(target, readonly=True) as uow:
        found = run_query(uow, QuerySpec(scope=SCOPE, where=parse(query)))
    return sorted(str(record["key"]) for record in found)


def test_ascii_case_is_folded(seeded: DbTarget) -> None:
    assert keys_for(seeded, "title~weld") == ["R-1", "R-2", "R-3"]
    assert keys_for(seeded, "title~WELD") == ["R-1", "R-2", "R-3"]


def test_non_ascii_case_is_not_folded(seeded: DbTarget) -> None:
    # The pattern is lower-cased by Python (Unicode), the column by the database (ASCII only):
    # an upper-case É in the stored title never matches, on either adapter.
    assert keys_for(seeded, "title~éclair") == ["R-2"]
    assert keys_for(seeded, "title~ÉCLAIR") == ["R-2"]
