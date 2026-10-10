"""Fixtures for the settings tests.

pytest runs in importlib mode, so a sibling helper is not importable by default; this directory is
put on ``sys.path`` so tests can write ``from settings_world import World`` (pyright resolves it
through ``extraPaths``).
"""

from __future__ import annotations

import sys
from collections.abc import Callable, Iterator
from pathlib import Path

import pytest
from tl_adapters.db import DbTarget

sys.path.insert(0, str(Path(__file__).parent))

from settings_world import World, definitions_in_force  # noqa: E402


@pytest.fixture(autouse=True)
def definitions() -> Iterator[None]:
    with definitions_in_force():
        yield


@pytest.fixture
def world(new_db: Callable[[], DbTarget]) -> World:
    return World(new_db())
