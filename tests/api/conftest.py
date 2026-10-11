"""Fixtures for the API round-trip test. This directory is put on ``sys.path`` (importlib mode)."""

from __future__ import annotations

import sys
from collections.abc import Callable, Iterator
from pathlib import Path

import pytest
from tl_adapters.db import DbTarget

sys.path.insert(0, str(Path(__file__).parent))

from support import Pair, build_pair  # noqa: E402


@pytest.fixture
def pair(
    tmp_path: Path, new_db: Callable[[], DbTarget], monkeypatch: pytest.MonkeyPatch
) -> Iterator[Pair]:
    monkeypatch.delenv("TL_SCHEMA_DIR", raising=False)  # the repository's fixture schema
    built = build_pair(tmp_path, new_db())
    try:
        yield built
    finally:
        built.close()
