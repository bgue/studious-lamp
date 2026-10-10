"""tl-tui test configuration.

pytest runs in importlib mode (root pyproject), so sibling test helpers are not importable by
default. Putting this directory on `sys.path` lets tests write `from fakes import FakeClient`;
pyright resolves the same import from the file's own directory.
"""

from __future__ import annotations

import sys
from pathlib import Path

_HERE = str(Path(__file__).parent)
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)
# The API's test harness (a real app on a real SQLite file, served on loopback) is shared with the
# remote-mode tests; its module name `harness` is unique in the repository.
_API_TESTS = str(Path(__file__).resolve().parents[2] / "tl-api" / "tests")
if _API_TESTS not in sys.path:
    sys.path.insert(1, _API_TESTS)

from collections.abc import Iterator  # noqa: E402

import pytest  # noqa: E402
from harness import Harness  # noqa: E402


@pytest.fixture
def harness(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Harness]:
    """A real API app over a fresh SQLite ledger with two dev tokens (the tl-api test harness)."""
    monkeypatch.delenv("TL_SCHEMA_DIR", raising=False)  # the repository's fixture schema
    built = Harness.build(tmp_path)
    try:
        yield built
    finally:
        built.close()
