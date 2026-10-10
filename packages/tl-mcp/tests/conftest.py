"""tl-mcp test configuration: puts this directory on `sys.path` for `import mcp_harness`.

pytest runs in importlib mode (root pyproject), so sibling helpers are not importable by default
(L-P0-I2-B1). Do not add ``__init__.py`` here.
"""

from __future__ import annotations

import os
import sys
import uuid
from collections.abc import Iterator
from pathlib import Path

import pytest
from tl_adapters.postgres import admin
from tl_mcp.dev.errors import DevGuardError
from tl_mcp.dev.guard import DevTarget, find_repo_root, resolve_target

_HERE = str(Path(__file__).parent)
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

from dev_harness import DevHarness  # noqa: E402
from mcp_harness import McpHarness  # noqa: E402

REPO = find_repo_root()


@pytest.fixture
def env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[McpHarness]:
    """A fresh SQLite ledger and an MCP server acting as ``agent:triage`` over it."""
    monkeypatch.delenv("TL_SCHEMA_DIR", raising=False)  # the repository's fixture schema
    built = McpHarness.build(tmp_path)
    try:
        yield built
    finally:
        built.close()


@pytest.fixture
def dev_env(tmp_path: Path) -> Iterator[DevHarness]:
    """The dev MCP server over a fresh SQLite ledger in ``tmp_path``."""
    yield DevHarness.build(tmp_path)


@pytest.fixture
def dev_pg_target() -> Iterator[DevTarget]:
    """A throw-away schema in the ``tl_test`` database of ``TL_PG_URL`` (the guard's own rule)."""
    server = os.environ.get("TL_PG_URL", admin.DEFAULT_URL)
    if not admin.reachable(server):
        if os.environ.get("TL_REQUIRE_POSTGRES") == "1":
            pytest.fail("Postgres is not reachable at TL_PG_URL")
        pytest.skip("Postgres is not reachable at TL_PG_URL")
    schema = "tl_t_" + uuid.uuid4().hex[:16]
    admin.create_schema_namespace(server, schema)
    try:
        url = admin.schema_url(server, schema)
        try:
            target = resolve_target(url, repo_root=REPO)
        except DevGuardError:
            pytest.skip("TL_PG_URL names a database that is not tl_test* or tl_dev*")
        from tl_adapters.db import create_schema

        create_schema(url)
        yield target
    finally:
        admin.drop_schema_namespace(server, schema)
