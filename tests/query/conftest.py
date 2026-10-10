"""Fixtures for the query-language tests: a seeded ledger and a read-only unit of work.

The data is described in ``query_seed.py``. This directory is put on ``sys.path`` so tests can write
``from query_seed import record_id`` (pytest runs in importlib mode, which does not do it for us).
"""

from __future__ import annotations

import sys
from collections.abc import Callable, Iterator
from pathlib import Path

import pytest
from tl_adapters._unit import BaseUnitOfWork
from tl_adapters.db import DbTarget, open_uow

sys.path.insert(0, str(Path(__file__).parent))

from query_seed import build_db  # noqa: E402


@pytest.fixture
def db(new_db: Callable[[], DbTarget]) -> DbTarget:
    path = new_db()
    build_db(path)
    return path


@pytest.fixture
def uow(db: DbTarget) -> Iterator[BaseUnitOfWork]:
    with open_uow(db, readonly=True) as opened:
        yield opened
