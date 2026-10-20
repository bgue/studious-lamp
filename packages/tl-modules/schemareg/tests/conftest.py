"""Fixtures of the schema registry module tests: SQLite and, under the parity run, Postgres."""

from __future__ import annotations

from collections.abc import Callable, Generator

import pytest
from tl_adapters.db import DbTarget, create_schema
from tl_mod_schemareg.testing import RegistryWorld


@pytest.fixture
def db(new_db: Callable[[], DbTarget]) -> DbTarget:
    """An empty ledger of the adapter under test, with every table (the module's included)."""
    target = new_db()
    create_schema(target)
    return target


@pytest.fixture
def world(db: DbTarget) -> Generator[RegistryWorld]:
    """A world whose schema provider is the process provider for the test."""
    made = RegistryWorld(db)
    with made.installed():
        yield made
