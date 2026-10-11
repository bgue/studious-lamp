"""Fixtures for the authentication tests: a unit-of-work factory per adapter and a movable clock.

The tests run on SQLite by default and on Postgres under ``just test-parity`` (they use ``db``).
"""

from __future__ import annotations

import sys
from collections.abc import Iterator
from pathlib import Path

import pytest
from tl_adapters.db import make_uow_factory

sys.path.insert(0, str(Path(__file__).parent))

from authworld import MovingClock, World  # noqa: E402


@pytest.fixture
def world(db: str | Path) -> Iterator[World]:
    factory = make_uow_factory(db)
    try:
        yield World(db, factory, MovingClock())
    finally:
        factory.dispose()
