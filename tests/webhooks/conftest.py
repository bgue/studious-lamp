"""Fixtures for the webhook tests.

pytest runs in importlib mode, so sibling helpers are not importable by default; this directory
is put on ``sys.path`` so tests can write ``from world import World``; pyright resolves it too.
"""

from __future__ import annotations

import sys
from collections.abc import Iterator
from pathlib import Path

import pytest
from tl_adapters.sqlite.factory import SqliteUowFactory
from tl_adapters.sqlite.uow import create_schema
from tl_core.webhooks.testing import FakeClock, ScriptedTransport

sys.path.insert(0, str(Path(__file__).parent))

from world import World  # noqa: E402


@pytest.fixture
def world(tmp_path: Path) -> Iterator[World]:
    path = tmp_path / "ledger.db"
    create_schema(path)
    factory = SqliteUowFactory(path)
    yield World(path, factory, FakeClock(), ScriptedTransport())
    factory.dispose()
