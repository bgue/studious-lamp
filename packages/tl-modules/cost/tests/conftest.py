"""Fixtures of the cost module tests: they run on SQLite and, under the parity run, on Postgres."""

from __future__ import annotations

import sys
from collections.abc import Callable
from pathlib import Path

import pytest
from tl_adapters.db import DbTarget, create_schema

sys.path.insert(0, str(Path(__file__).parent))

from tl_mod_cost.testing import CostWorld  # noqa: E402


@pytest.fixture
def db(new_db: Callable[[], DbTarget]) -> DbTarget:
    """An empty ledger of the adapter under test, with every table (the module's included)."""
    target = new_db()
    create_schema(target)
    return target


@pytest.fixture
def world(db: DbTarget) -> CostWorld:
    return CostWorld(db)
