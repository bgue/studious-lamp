"""Fixtures of the integration-layer tests: a world per adapter."""

from __future__ import annotations

import sys
from collections.abc import Callable, Iterator
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent))

from intworld import World  # noqa: E402


@pytest.fixture
def world(new_db: Callable[[], str | Path]) -> Iterator[World]:
    found = World(new_db())
    try:
        yield found
    finally:
        found.dispose()
