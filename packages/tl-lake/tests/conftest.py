"""Fixtures for the lake tests. ``builder`` is importable as a sibling module (L-P0-I2-B4)."""

from __future__ import annotations

import sys
from collections.abc import Callable, Iterator
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
def new_ledger(new_db: Callable[[], str | Path]) -> Callable[[], LedgerBuilder]:
    """Call it for an empty ledger on the adapter under test (Postgres too in parity runs)."""
    return lambda: LedgerBuilder.create(new_db())


@pytest.fixture
def ledger(new_ledger: Callable[[], LedgerBuilder]) -> LedgerBuilder:
    """One ledger on the adapter under test. Tests using it run on both under `just test-parity`."""
    return new_ledger()


@pytest.fixture
def lake(tmp_path: Path) -> LakeConfig:
    return LakeConfig.at(tmp_path / "lake")
