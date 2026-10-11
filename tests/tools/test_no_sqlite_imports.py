"""No service entry point opens SQLite directly (P1-I0 workstream B, decision B1).

The API, the TUI, the MCP server, the simulator and the `tl` commands take their database from
`tl_adapters.db` / `tl_adapters.backend`, which pick the adapter from the target (a SQLite path or
a `postgresql://` URL). An import of `tl_adapters.sqlite` in one of them would turn a Postgres URL
back into a file name for that path, so this test fails on it. `tl backup sqlite` is the one
command that is SQLite-only by nature.
"""

from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
TREES = ("tl-api", "tl-cli", "tl-mcp", "tl-sim", "tl-tui")
ALLOWED = {"packages/tl-cli/src/tl_cli/backup.py"}


def sqlite_imports(path: Path) -> list[str]:
    found: list[str] = []
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.ImportFrom) and (node.module or "").startswith(
            "tl_adapters.sqlite"
        ):
            found.append(f"{path.relative_to(ROOT)}:{node.lineno} from {node.module} import ...")
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name.startswith("tl_adapters.sqlite"):
                    found.append(f"{path.relative_to(ROOT)}:{node.lineno} import {alias.name}")
    return found


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
