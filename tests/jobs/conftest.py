"""Fixtures for the job queue tests: a world per adapter and a movable clock."""

from __future__ import annotations

import sys
from collections.abc import Iterator
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent))

from jobsworld import Clock, World  # noqa: E402


@pytest.fixture
def clock() -> Clock:
    return Clock()


@pytest.fixture
def world(db: str | Path, clock: Clock) -> Iterator[World]:
    found = World(db, clock)
    try:
        yield found
    finally:
        found.dispose()
