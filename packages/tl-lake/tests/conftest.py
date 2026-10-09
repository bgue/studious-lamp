"""Fixtures for the lake tests. ``builder`` is importable as a sibling module (L-P0-I2-B4)."""

from __future__ import annotations

import sys
from collections.abc import Iterator
from pathlib import Path

import pytest
from tl_core.schema_provider import DirectorySchemaProvider, use_provider
from tl_lake.config import LakeConfig

sys.path.insert(0, str(Path(__file__).parent))

from builder import LedgerBuilder  # noqa: E402

FIXTURES = Path(__file__).resolve().parents[3] / "schema" / "fixtures"


@pytest.fixture(autouse=True)
def fixture_schemas() -> Iterator[None]:
    with use_provider(DirectorySchemaProvider(FIXTURES)):
        yield


@pytest.fixture
def ledger(tmp_path: Path) -> LedgerBuilder:
    return LedgerBuilder.create(tmp_path / "tl.db")


@pytest.fixture
def lake(tmp_path: Path) -> LakeConfig:
    return LakeConfig.at(tmp_path / "lake")
