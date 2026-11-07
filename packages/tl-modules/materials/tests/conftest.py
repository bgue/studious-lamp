"""Fixtures of the materials module tests (SQLite, and Postgres under the parity run)."""

from __future__ import annotations

import sys
from collections.abc import Callable
from pathlib import Path

import pytest
from tl_adapters.db import DbTarget, create_schema

sys.path.insert(0, str(Path(__file__).parent))

import acc_s2  # noqa: E402
import acc_s3  # noqa: E402
import acc_s4  # noqa: E402


@pytest.fixture
def db(new_db: Callable[[], DbTarget]) -> DbTarget:
    """An empty ledger of the adapter under test, with every table (the module's included)."""
    target = new_db()
    create_schema(target)
    return target


@pytest.fixture
def world2(db: DbTarget) -> acc_s2.World:
    """The S2 world: item library, locations, PO lines on an empty ledger."""
    return acc_s2.World(db)


@pytest.fixture
def world3(db: DbTarget, tmp_path: Path) -> acc_s3.World:
    """The S3 world: a project, receipts, stock and movements on an empty ledger."""
    return acc_s3.World(db, tmp_path / "objects")


@pytest.fixture
def world4(db: DbTarget, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> acc_s4.World:
    """The S4 world: documents helpers and the MTO publish target on an empty ledger."""
    monkeypatch.delenv("TL_SCHEMA_DIR", raising=False)
    return acc_s4.World(db, tmp_path / "objects")
