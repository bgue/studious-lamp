"""Fixtures of the permits module tests: SQLite by default, Postgres under the parity run."""

from __future__ import annotations

import sys
from collections.abc import Callable
from pathlib import Path

import pytest
from tl_adapters.db import DbTarget, create_schema

sys.path.insert(0, str(Path(__file__).parent))

from permit_world import World  # noqa: E402
from tl_mod_permits.handlers import common as common_handlers  # noqa: E402
from tl_mod_permits.handlers import permit as permit_handlers  # noqa: E402


@pytest.fixture
def db(new_db: Callable[[], DbTarget]) -> DbTarget:
    """An empty ledger of the adapter under test, with every table (the module's included)."""
    target = new_db()
    create_schema(target)
    return target


@pytest.fixture
def world(db: DbTarget, monkeypatch: pytest.MonkeyPatch) -> World:
    """A ledger with the people and a fixed clock (``world.at``; a test moves it)."""
    w = World(db)
    w.people()
    monkeypatch.setattr(permit_handlers, "now", lambda: w.at)
    monkeypatch.setattr(common_handlers, "now", lambda: w.at)  # the S3 handlers read it here
    return w
