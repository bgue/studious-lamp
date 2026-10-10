"""The actor interface is the fanout plan's, and the simulator stays outside tl_core.

Brief 29.1: bootstrap loaders and the simulator use only the public API and MCP. The imports of
``src/tl_sim`` are read with ``ast``: no ledger, unit of work, projection, adapter or SQL, and no
command handler (``handle_*``); command models, error classes and the HTTP client are allowed.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
SRC = REPO / "packages" / "tl-sim" / "src" / "tl_sim"
FORBIDDEN_MODULES = (
    "tl_adapters",
    "sqlalchemy",
    "tl_core.uow",
    "tl_core.ledger",
    "tl_core.projection",
    "tl_core.bus",
    "tl_core.changefeed",
    "tl_core.files",
    "tl_core.numbering",
)
FORBIDDEN_NAMES = re.compile(r"^(handle_|open_|create_schema|make_)")


def test_types_py_is_the_contract_of_the_fanout_plan_verbatim() -> None:
    fanout = (REPO / "docs" / "tickets" / "P0-I6" / "FANOUT.md").read_text()
    match = re.search(r"```python\n# packages/tl-sim/src/tl_sim/types.py\n(.*?)```", fanout, re.S)
    assert match is not None
    assert match.group(1).strip() in (SRC / "types.py").read_text()


def imports_of(path: Path) -> list[tuple[str, str | None]]:
    found: list[tuple[str, str | None]] = []
    for node in ast.walk(ast.parse(path.read_text())):
        if isinstance(node, ast.Import):
            found += [(alias.name, None) for alias in node.names]
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            found += [(node.module, alias.name) for alias in node.names]
    return found


def test_the_simulator_never_reaches_the_ledger_or_a_handler() -> None:
    problems: list[str] = []
    for path in sorted(SRC.rglob("*.py")):
        for module, name in imports_of(path):
            if module.startswith(FORBIDDEN_MODULES):
                problems.append(f"{path.name}: imports {module}")
            if name is not None and module.startswith("tl_core") and FORBIDDEN_NAMES.match(name):
                problems.append(f"{path.name}: imports {module}.{name}")
    assert problems == []


def test_the_scan_sees_the_imports_it_is_meant_to_forbid(tmp_path: Path) -> None:
    sample = tmp_path / "bad.py"
    sample.write_text(
        "from tl_core.services.records import handle_create_record\nimport sqlalchemy\n"
    )
    seen = imports_of(sample)
    assert ("tl_core.services.records", "handle_create_record") in seen
    assert ("sqlalchemy", None) in seen
    assert FORBIDDEN_NAMES.match("handle_create_record")
