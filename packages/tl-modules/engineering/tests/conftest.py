"""Fixtures of the engineering module tests.

The tests run on SQLite by default and on Postgres under ``just test-parity`` (they use
``new_engine``). Putting this directory on ``sys.path`` lets them write ``from engworld import ...``
(pytest imports test files by path here).
"""

from __future__ import annotations

import sys
from collections.abc import Callable, Iterator
from pathlib import Path

import pytest
from sqlalchemy import Engine
from tl_adapters.db import DbTarget, create_schema
from tl_core.schema_provider import DirectorySchemaProvider, use_provider

sys.path.insert(0, str(Path(__file__).parent))

from engworld import FIXTURES, Events, install  # noqa: E402


@pytest.fixture
def engine(new_engine: Callable[[], Engine], dialect: str) -> Iterator[Engine]:
    """An engine on an empty database of the adapter under test, with every table installed."""
    eng = new_engine()
    install(eng, dialect)
    yield eng
    eng.dispose()


@pytest.fixture
def events() -> Events:
    return Events()


@pytest.fixture
def fixture_schemas() -> Iterator[None]:
    """The committed fixture packages (``schema/fixtures``) as the effective schema."""
    with use_provider(DirectorySchemaProvider(FIXTURES)):
        yield


@pytest.fixture
def db(new_db: Callable[[], DbTarget]) -> DbTarget:
    """An empty ledger of the adapter under test, with every table (the module's included)."""
    target = new_db()
    create_schema(target)
    return target
