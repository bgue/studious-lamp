"""Fixtures of the legacy module tests: SQLite and, under the parity run, Postgres."""

from __future__ import annotations

from collections.abc import Callable, Iterator
from pathlib import Path

import pytest
from tl_adapters.db import DbTarget, create_schema
from tl_core.schema_provider import DirectorySchemaProvider, use_provider
from tl_lake import LakeConfig
from tl_mod_legacy.model import use_loaders
from tl_mod_legacy.testing import LegacyWorld, document_loader, tag_loader

FIXTURES = Path(__file__).resolve().parents[4] / "schema" / "fixtures"


@pytest.fixture(autouse=True)
def fixture_schemas() -> Iterator[None]:
    with use_provider(DirectorySchemaProvider(FIXTURES)):
        yield


@pytest.fixture(autouse=True)
def loaders() -> Iterator[None]:
    with use_loaders({"test-tags": tag_loader(), "test-docs": document_loader()}):
        yield


@pytest.fixture
def db(new_db: Callable[[], DbTarget]) -> DbTarget:
    target = new_db()
    create_schema(target)
    return target


@pytest.fixture
def lake(tmp_path: Path) -> LakeConfig:
    return LakeConfig.at(tmp_path / "lake")


@pytest.fixture
def world(db: DbTarget, tmp_path: Path, lake: LakeConfig) -> LegacyWorld:
    made = LegacyWorld(db, tmp_path / "objects", lake)
    made.load_standards()
    return made
