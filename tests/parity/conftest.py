"""Fixtures for the webhook parity tests: the webhook test world on SQLite or Postgres.

The shared helper modules live in tests/webhooks; this directory puts them on ``sys.path`` (pyright
finds them through ``extraPaths``).
"""

from __future__ import annotations

import sys
from collections.abc import Callable, Iterator
from pathlib import Path

import pytest
from tl_adapters.db import DbTarget, create_schema, make_uow_factory
from tl_core.webhooks.testing import FakeClock, ScriptedTransport

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "webhooks"))

from world import World  # noqa: E402


@pytest.fixture
def pworld(new_db: Callable[[], DbTarget]) -> Iterator[World]:
    """A webhook world on the adapter under test (``--adapters sqlite,postgres``)."""
    target = new_db()
    create_schema(target)
    factory = make_uow_factory(target)
    yield World(target, factory, FakeClock(), ScriptedTransport())
    factory.dispose()
