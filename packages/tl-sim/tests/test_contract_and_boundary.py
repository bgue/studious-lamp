"""The actor interface is the fanout plan's, and the simulator stays outside tl_core.

Brief 29.1: bootstrap loaders and the simulator use only the public API and MCP. The code of
``src/tl_sim`` is read with ``ast``. It may not import a ledger, unit of work, projection, adapter,
SQL or a module of command handlers and readers, in any spelling (``import x``, ``import x as y``,
``from x import y`` where ``x.y`` is the module, ``from x import y as z``), may not reach one
through an alias (``alias.ledger``), may not name a handler (``handle_*``, ``open_*`` ...), and may
not load a module by string (``importlib``, ``__import__``). Command models, error classes and
``tl_api.tokens`` are allowed.
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
    # command handlers and readers; the model modules (commands, links, psets, workflow, feed) stay
    "tl_core.services.records",
    "tl_core.services.edit",
    "tl_core.services.queries",
    "tl_core.services.link_queries",
    "tl_core.services.link_trace",
    "tl_core.services.feed_queries",
    "tl_core.services.feed_actions",
    "tl_core.services.feed_completion",
    "tl_core.services.schema_events",
)
FORBIDDEN_NAMES = re.compile(r"^(handle_|open_|create_schema|make_)")
LOADERS = {"__import__", "import_module"}


def forbidden(dotted: str) -> bool:
    return any(dotted == m or dotted.startswith(m + ".") for m in FORBIDDEN_MODULES)


def problems_in(source: str) -> list[str]:
    """What ``source`` imports, reaches or names that the simulator may not."""
    problems: list[str] = []
    aliases: dict[str, str] = {}  # local name -> the dotted module or object it stands for
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                aliases[alias.asname or alias.name.split(".")[0]] = (
                    alias.name if alias.asname else alias.name.split(".")[0]
                )
                if forbidden(alias.name):
                    problems.append(f"imports {alias.name}")
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            if forbidden(node.module):
                problems.append(f"imports from {node.module}")
            for alias in node.names:
                dotted = f"{node.module}.{alias.name}"
                aliases[alias.asname or alias.name] = dotted
                if forbidden(dotted):
                    problems.append(f"imports {dotted}")
                if node.module.startswith("tl_core") and FORBIDDEN_NAMES.match(alias.name):
                    problems.append(f"imports the handler {dotted}")
    for node in ast.walk(tree):
        if isinstance(node, ast.Attribute):
            chain: list[str] = [node.attr]
            inner: ast.expr = node.value
            while isinstance(inner, ast.Attribute):
                chain.append(inner.attr)
                inner = inner.value
            if FORBIDDEN_NAMES.match(node.attr) and not node.attr.startswith(("make_", "open_")):
                problems.append(f"calls the handler .{node.attr}")
            if isinstance(inner, ast.Name) and inner.id in aliases:
                dotted = ".".join([aliases[inner.id], *reversed(chain)])
                if forbidden(dotted):
                    problems.append(f"reaches {dotted}")
        elif isinstance(node, ast.Call):
            func = node.func
            name = func.id if isinstance(func, ast.Name) else getattr(func, "attr", "")
            if name in LOADERS:
                problems.append(f"loads a module by name with {name}")
    return sorted(set(problems))


def test_types_py_is_the_contract_of_the_fanout_plan_verbatim() -> None:
    fanout = (REPO / "docs" / "tickets" / "P0-I6" / "FANOUT.md").read_text()
    match = re.search(r"```python\n# packages/tl-sim/src/tl_sim/types.py\n(.*?)```", fanout, re.S)
    assert match is not None
    assert match.group(1).strip() in (SRC / "types.py").read_text()


def test_the_simulator_never_reaches_the_ledger_or_a_handler() -> None:
    found = {
        f"{path.name}: {problem}"
        for path in sorted(SRC.rglob("*.py"))
        for problem in problems_in(path.read_text())
    }
    assert found == set()


# --- the scan has to see every spelling of a forbidden import (negative fixtures) ---------------


def test_the_scan_catches_the_direct_and_aliased_spellings() -> None:
    assert "imports tl_core.ledger" in problems_in("import tl_core.ledger\n")
    assert "imports tl_core.ledger" in problems_in("import tl_core.ledger as ledger\n")
    assert "imports tl_adapters.sqlite.uow" in problems_in("import tl_adapters.sqlite.uow\n")
    assert "imports sqlalchemy" in problems_in("import sqlalchemy as sa\n")
    assert "imports from tl_core.ledger" in problems_in("from tl_core.ledger import Event\n")


def test_the_scan_catches_from_x_import_a_forbidden_module() -> None:
    assert "imports tl_core.ledger" in problems_in("from tl_core import ledger\n")
    assert "imports tl_core.services.records" in problems_in(
        "from tl_core.services import records\n"
    )
    assert "imports tl_core.uow" in problems_in("from tl_core import uow as u\n")
    assert "imports tl_adapters.sqlite" in problems_in("from tl_adapters import sqlite\n")


def test_the_scan_catches_attribute_access_through_an_alias() -> None:
    assert "reaches tl_core.ledger.Event" in problems_in("import tl_core as c\nc.ledger.Event\n")
    assert "reaches tl_core.services.records" in problems_in(
        "from tl_core import services as s\ns.records\n"
    )
    assert "reaches tl_core.ledger" in problems_in("import tl_core\ntl_core.ledger\n")


def test_the_scan_catches_a_handler_by_name_and_a_module_loaded_by_string() -> None:
    assert "imports the handler tl_core.services.links.handle_add_link" in problems_in(
        "from tl_core.services.links import handle_add_link\n"
    )
    assert "calls the handler .handle_add_link" in problems_in(
        "from tl_core.services import links\nlinks.handle_add_link(None, None)\n"
    )
    assert "loads a module by name with import_module" in problems_in(
        "import importlib\nimportlib.import_module('tl_core.ledger')\n"
    )
    assert "loads a module by name with __import__" in problems_in("__import__('sqlalchemy')\n")


def test_the_scan_allows_what_the_simulator_needs() -> None:
    allowed = (
        "from tl_core.services.commands import CreateRecord\n"
        "from tl_core.services.links import AddLink\n"
        "from tl_core.services.psets import SetPsetValues\n"
        "from tl_core.services.workflow import TransitionWorkflow\n"
        "from tl_core.services.feed import PostToFeed\n"
        "from tl_core.services.errors import GuardFailedError\n"
        "from tl_api.client import ApiClient\n"
        "from tl_api.tokens import add_token\n"
        "import tl_core.services.errors as errors\nerrors.GuardFailedError\n"
    )
    assert problems_in(allowed) == []
