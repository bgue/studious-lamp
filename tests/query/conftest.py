"""Fixtures for the query-language tests: a seeded ledger and a read-only unit of work.

The data is described in ``query_seed.py``. This directory is put on ``sys.path`` so tests can write
``from query_seed import record_id`` (pytest runs in importlib mode, which does not do it for us).
"""

from __future__ import annotations

import sys
from collections.abc import Iterator
from pathlib import Path

import pytest
from tl_adapters.sqlite.uow import SqliteUnitOfWork, open_uow

sys.path.insert(0, str(Path(__file__).parent))

from query_seed import build_db  # noqa: E402


@pytest.fixture
def db(tmp_path: Path) -> Path:
    path = tmp_path / "ledger.db"
    build_db(path)
    return path


@pytest.fixture
def uow(db: Path) -> Iterator[SqliteUnitOfWork]:
    with open_uow(db, readonly=True) as opened:
        yield opened
