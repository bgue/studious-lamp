"""Fixtures of the quality module tests: SQLite by default, Postgres under the parity run."""

from __future__ import annotations

import sys
from collections.abc import Callable
from pathlib import Path

import pytest
from tl_adapters.db import DbTarget, create_schema

sys.path.insert(0, str(Path(__file__).parent))

from punch_world import World  # noqa: E402


@pytest.fixture
def db(new_db: Callable[[], DbTarget]) -> DbTarget:
    """An empty ledger of the adapter under test, with every table (the module's included)."""
    target = new_db()
    create_schema(target)
    return target


@pytest.fixture
def world(db: DbTarget) -> World:
    """A ledger with the people."""
    w = World(db)
    w.people()
    return w
