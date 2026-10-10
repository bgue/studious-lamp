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

# The API's test harness (a real app on a real SQLite file) is shared with the cross-surface tests;
# its module name `harness` is unique in the repository.
_API_TESTS = str(Path(__file__).resolve().parents[2] / "packages" / "tl-api" / "tests")
if _API_TESTS not in sys.path:
    sys.path.insert(1, _API_TESTS)
_TUI_TESTS = str(Path(__file__).resolve().parents[2] / "packages" / "tl-tui" / "tests")
if _TUI_TESTS not in sys.path:  # `helpers` (run_pilot, screen_text) for the remote TUI test
    sys.path.insert(2, _TUI_TESTS)

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
