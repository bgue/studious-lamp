"""Fixtures for the module-role tests (helpers in ``moduleroles.py``). No ``__init__.py`` here."""

from __future__ import annotations

import sys
from collections.abc import Iterator
from pathlib import Path

import pytest
from tl_adapters.db import make_uow_factory

_HERE = str(Path(__file__).parent)
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

from moduleroles import MovingClock, Roles, World  # noqa: E402


@pytest.fixture
def roles(db: str | Path) -> Iterator[Roles]:
    factory = make_uow_factory(db)
    try:
        yield Roles(World(db, factory, MovingClock()))
    finally:
        factory.dispose()
