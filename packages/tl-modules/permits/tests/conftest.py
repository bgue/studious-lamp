"""Fixtures of the permits module tests: SQLite by default, Postgres under the parity run."""

from __future__ import annotations

from collections.abc import Callable

import pytest
from tl_adapters.db import DbTarget, create_schema


@pytest.fixture
def db(new_db: Callable[[], DbTarget]) -> DbTarget:
    """An empty ledger of the adapter under test, with every table (the module's included)."""
    target = new_db()
    create_schema(target)
    return target
