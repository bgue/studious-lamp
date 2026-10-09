"""tl-api test configuration: puts this directory on ``sys.path`` so tests can import ``harness``.

pytest runs in importlib mode (root pyproject), so sibling helpers are not importable by default
(L-P0-I2-B1). Do not add ``__init__.py`` here.
"""

from __future__ import annotations

import sys
from collections.abc import Iterator
from pathlib import Path

import pytest

_HERE = str(Path(__file__).parent)
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

from harness import Harness  # noqa: E402


@pytest.fixture
def harness(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Harness]:
    """A fresh SQLite ledger, an app over it, two dev tokens and an fs object store."""
    monkeypatch.delenv("TL_SCHEMA_DIR", raising=False)  # the repository's fixture schema
    built = Harness.build(tmp_path)
    try:
        yield built
    finally:
        built.close()
