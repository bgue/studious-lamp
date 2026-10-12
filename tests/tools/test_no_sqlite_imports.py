"""No service entry point opens SQLite directly (P1-I0 workstream B, decision B1).

The API, the TUI, the MCP server, the simulator and the `tl` commands take their database from
`tl_adapters.db` / `tl_adapters.backend`, which pick the adapter from the target (a SQLite path or
a `postgresql://` URL). An import of `tl_adapters.sqlite` in one of them would turn a Postgres URL
back into a file name for that path, so this test fails on it, in every spelling: `import
tl_adapters.sqlite.x`, `from tl_adapters.sqlite.x import y`, `from tl_adapters import sqlite` (also
`from tl_adapters.db import sqlite`, with or without an alias), `x.sqlite` reached through an
imported module, and `importlib.import_module("tl_adapters.sqlite...")` or `__import__(...)` with a
string literal. `tl backup sqlite` is the one command that is SQLite-only by nature.

Deliberately out of scope: `tl-lake` (it reads the ledger through the caller's connection),
`tl-modules` (scaffolded modules and their tests) and `tl_mcp/dev` (the dev MCP server is
SQLite-only by decision C4 and guarded by its own tests). The scan covers the `src` tree of the five
packages in `TREES`, not their tests.
"""

from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
TREES = ("tl-api", "tl-cli", "tl-mcp", "tl-sim", "tl-tui")
ALLOWED = {"packages/tl-cli/src/tl_cli/backup.py"}
ADAPTER_MODULES = ("tl_adapters", "tl_adapters.db")
LOADERS = {"import_module", "__import__"}


def loader_name(call: ast.Call) -> str:
    if isinstance(call.func, ast.Name):
        return call.func.id
    if isinstance(call.func, ast.Attribute):
        return call.func.attr
    return ""


def problems_in(source: str) -> list[str]:
    """What ``source`` imports, reaches or loads of the SQLite adapter."""
    found: list[str] = []
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.ImportFrom):
            module = node.module or ""
            if module.startswith("tl_adapters.sqlite"):
                found.append(f"line {node.lineno}: from {module} import ...")
            if module in ADAPTER_MODULES:
                found.extend(
                    f"line {node.lineno}: from {module} import {alias.name}"
                    for alias in node.names
                    if alias.name == "sqlite" or alias.name.startswith("sqlite.")
                )
        elif isinstance(node, ast.Import):
            found.extend(
                f"line {node.lineno}: import {alias.name}"
                for alias in node.names
                if alias.name.startswith("tl_adapters.sqlite")
            )
        elif isinstance(node, ast.Attribute) and node.attr == "sqlite":
            found.append(f"line {node.lineno}: .sqlite reached through a module")
        elif isinstance(node, ast.Call) and loader_name(node) in LOADERS and node.args:
            first = node.args[0]
            if (
                isinstance(first, ast.Constant)
                and isinstance(first.value, str)
                and first.value.startswith("tl_adapters.sqlite")
            ):
                found.append(f"line {node.lineno}: {loader_name(node)}({first.value!r})")
    return found


def sqlite_imports(path: Path) -> list[str]:
    return [f"{path.relative_to(ROOT)}:{p}" for p in problems_in(path.read_text(encoding="utf-8"))]


def test_no_service_or_command_imports_the_sqlite_adapter_directly() -> None:
    problems: list[str] = []
    for tree in TREES:
        for path in sorted((ROOT / "packages" / tree / "src").rglob("*.py")):
            if str(path.relative_to(ROOT)) in ALLOWED:
                continue
            problems.extend(sqlite_imports(path))
    assert problems == [], "use tl_adapters.db or tl_adapters.backend instead:\n" + "\n".join(
        problems
    )


def test_the_allowed_exception_is_still_needed() -> None:
    assert sqlite_imports(ROOT / "packages/tl-cli/src/tl_cli/backup.py") != []


def test_the_scan_sees_every_spelling_of_the_import() -> None:
    bad = [
        "import tl_adapters.sqlite.uow\n",
        "import tl_adapters.sqlite.uow as u\n",
        "from tl_adapters.sqlite.uow import open_uow\n",
        "from tl_adapters.sqlite import factory\n",
        "from tl_adapters import sqlite\n",
        "from tl_adapters import sqlite as lite\n",
        "from tl_adapters.db import sqlite\n",
        "from tl_adapters.db import sqlite as lite\n",
        "from tl_adapters import db\nx = db.sqlite.engine\n",
        "import importlib\nimportlib.import_module('tl_adapters.sqlite.uow')\n",
        "from importlib import import_module\nimport_module('tl_adapters.sqlite')\n",
        "__import__('tl_adapters.sqlite.engine')\n",
    ]
    for source in bad:
        assert problems_in(source), source


def test_the_scan_leaves_the_neutral_imports_alone() -> None:
    good = [
        "from tl_adapters.db import DbTarget, open_uow, make_uow_factory\n",
        "from tl_adapters.backend import open_backend\n",
        "from tl_adapters import db\n",
        "from tl_adapters.postgres.engine import split_url\n",
        "import importlib\nimportlib.import_module('tl_api.app')\n",
    ]
    for source in good:
        assert problems_in(source) == [], source
