"""tl-mcp test configuration: puts this directory on `sys.path` for `import mcp_harness`.

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

from mcp_harness import McpHarness  # noqa: E402


@pytest.fixture
def env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[McpHarness]:
    """A fresh SQLite ledger and an MCP server acting as ``agent:triage`` over it."""
    monkeypatch.delenv("TL_SCHEMA_DIR", raising=False)  # the repository's fixture schema
    built = McpHarness.build(tmp_path)
    try:
        yield built
    finally:
        built.close()
