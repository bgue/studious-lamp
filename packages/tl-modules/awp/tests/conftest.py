"""Fixtures of the awp module tests: SQLite by default, Postgres under the parity run."""

from __future__ import annotations

import sqlite3
import sys
from collections.abc import Callable
from pathlib import Path

import pytest
from tl_adapters.db import DbTarget, as_target, create_schema

sys.path.insert(0, str(Path(__file__).parent))

from awp_world import World  # noqa: E402


@pytest.fixture
def db(new_db: Callable[[], DbTarget]) -> DbTarget:
    """An empty ledger of the adapter under test, with every table (the module's included)."""
    target = new_db()
    create_schema(target)
    return target


@pytest.fixture
def world(db: DbTarget) -> World:
    """A ledger with the four people, the standards editions and cost codes loaded."""
    w = World(db)
    w.people()
    w.editions()
    return w


@pytest.fixture(scope="session")
def seed_file(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """The S4 seed ledger on SQLite, built once per session: 3-level WBS with 6 leaves (two mapped
    to cost codes), 4 CWAs, path version 1, 6 CWPs in 3 states, no rollup rows and no packages."""
    path = tmp_path_factory.mktemp("awp-seed") / "seed.db"
    target = as_target(str(path))
    create_schema(target)
    world = World(target)
    world.people()
    world.editions()
    world.seed()
    return path


def _copy(source: Path, tmp_path: Path) -> DbTarget:
    copy = tmp_path / "ledger.db"
    src = sqlite3.connect(source)
    dst = sqlite3.connect(copy)
    try:
        src.backup(dst)
    finally:
        dst.close()
        src.close()
    return as_target(str(copy))


@pytest.fixture
def seeded(seed_file: Path, tmp_path: Path) -> World:
    """A private copy of the seed ledger (a test may write to it)."""
    return World(_copy(seed_file, tmp_path))


@pytest.fixture
def rolled(seeded: World) -> World:
    """The seed copy after the rollup ran (D25: queue, then the worker on the copy)."""
    from tl_mod_awp.worker import build_worker, requeue_orphans

    requeue_orphans(seeded.db)
    with build_worker(seeded.db) as worker:
        worker.runner.run_until_idle()
    return seeded
