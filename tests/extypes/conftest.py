"""Fixtures of the extension type tests (P0-I8 workstream B).

The tests share one helper module, ``extworld``; pytest runs in importlib mode, so this directory is
put on ``sys.path`` (pyright finds it through ``extraPaths``).
"""

from __future__ import annotations

import sys
from collections.abc import Callable, Iterator
from pathlib import Path

import pytest

_HERE = str(Path(__file__).parent)
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

from extworld import World, build_world  # noqa: E402
from tl_core.schema_provider import DirectorySchemaProvider, use_provider  # noqa: E402


@pytest.fixture
def world(new_db: Callable[[], str | Path], tmp_path: Path) -> Iterator[World]:
    """A ledger on the adapter under test with the example packages copied beside it."""
    with use_provider(DirectorySchemaProvider()):
        built = build_world(new_db(), tmp_path)
        try:
            yield built
        finally:
            built.factory.dispose()
