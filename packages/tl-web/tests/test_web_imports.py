"""What ``tl_web`` may import, and the list of its page modules (S1 l; S4 a; S6 a; R3).

* a fresh interpreter that imports ``tl_web`` and every page module has no ``textual`` loaded;
* the source of ``tl_web`` has no ``sqlalchemy``, no ``cur_*`` name, no ``tl_core`` import beyond
  ``tl_core.auth`` (an import under ``if TYPE_CHECKING`` is only an annotation), and only
  ``present.py`` imports ``tl_tui`` (the one door to the terminal's text);
* ``PAGE_MODULES`` is the list below: a twin ticket that adds a page edits both.
"""

from __future__ import annotations

import ast
import importlib
import re
import subprocess
import sys
from pathlib import Path

import pytest
from tl_web import routers

WEB = Path(__file__).resolve().parents[1] / "src" / "tl_web"
ROOT = Path(__file__).resolve().parents[3]
#: The page modules today, in match order (twin tickets T09 to T14 add theirs here).
PAGE_MODULES = (
    "tl_web.files",
    "tl_web.log",
    "tl_web.actions",
    "tl_web.pages.rfis",
    "tl_web.pages.correspondence",
    "tl_web.pages.documents",
    "tl_web.pages.cwps",
    "tl_web.pages.cwas",
    "tl_web.pages.wbs",
    "tl_web.pages.packages",
    "tl_web.pages.path",
    "tl_web.pages.stock",
    "tl_web.pages.movements",
    "tl_web.pages.receipts",
    "tl_web.pages.mto",
    "tl_web.pages.items",
    "tl_web.pages.locations",
    "tl_web.pages.record",
    "tl_web.pages.viewer",
)


def run_clean(code: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-I", "-c", code], capture_output=True, text=True, cwd=ROOT, check=False
    )


def test_importing_tl_web_pulls_no_textual() -> None:
    code = (
        "import sys, importlib\n"
        "import tl_web, tl_web.app, tl_web.csrf, tl_web.session, tl_web.present\n"
        "from tl_web.routers import PAGE_MODULES, _exists\n"
        "for n in PAGE_MODULES:\n"
        "    if _exists(n): importlib.import_module(n)\n"
        "bad = sorted(m for m in sys.modules if m.split('.')[0] == 'textual')\n"
        "print(bad)\nsys.exit(1 if bad else 0)"
    )
    done = run_clean(code)
    assert done.returncode == 0, done.stdout + done.stderr[-300:]


def test_the_terminals_text_modules_import_without_textual() -> None:
    code = (
        "import sys\n"
        "import tl_tui.record_text, tl_tui.properties_text, tl_tui.links_text, tl_tui.trace_text\n"
        "assert 'textual' not in sys.modules and 'rich' not in sys.modules\n"
        "import tl_web.present\nassert 'textual' not in sys.modules\n"
    )
    done = run_clean(code)
    assert done.returncode == 0, done.stderr[-300:]


def test_the_old_names_of_the_moved_text_modules_still_import() -> None:
    old = (
        "from tl_tui.widgets.record_view import details_lines, event_label, event_summary\n"
        "from tl_tui.widgets.psets_tab import psets_text, rule_text, value_text, unit_text\n"
        "from tl_tui.widgets.links_tab import TableRow, status_text, pin_text, group_title\n"
        "from tl_tui.widgets.trace_tab import node_text, tree_lines, head_text, DIRECTIONS\n"
    )
    done = run_clean(old)
    assert done.returncode == 0, done.stderr[-300:]


def _type_checking_lines(tree: ast.AST) -> set[int]:
    lines: set[int] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.If) and "TYPE_CHECKING" in ast.unparse(node.test):
            for inner in node.body:
                lines.update(range(inner.lineno, (inner.end_lineno or inner.lineno) + 1))
    return lines


def _imports(tree: ast.AST) -> list[tuple[str, int]]:
    found: list[tuple[str, int]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            found += [(a.name, node.lineno) for a in node.names]
        elif isinstance(node, ast.ImportFrom) and not node.level:
            found.append((node.module or "", node.lineno))
    return found


def test_tl_web_has_no_sqlalchemy_no_cur_names_and_no_core_query_import() -> None:
    files = sorted(WEB.rglob("*.py"))
    assert len(files) >= 15  # the scan found the package
    for path in files:
        rel = path.relative_to(WEB)
        text = path.read_text()
        assert not re.search(r"\bcur_\w+", text), f"{rel}: a cur_* name"
        tree = ast.parse(text, str(path))
        annotations = _type_checking_lines(tree)
        for name, line in _imports(tree):
            assert not name.startswith("sqlalchemy"), f"{rel}:{line} imports {name}"
            if name.startswith("tl_core") and line not in annotations:
                assert name.startswith("tl_core.auth"), f"{rel}:{line} imports {name}"
            if name.startswith("tl_tui"):
                assert rel.name == "present.py", f"{rel}:{line} imports {name}"


def test_page_modules_are_the_list_of_routers_py_and_every_name_imports() -> None:
    assert routers.PAGE_MODULES == PAGE_MODULES, (
        "PAGE_MODULES changed: a twin ticket that adds a page edits routers.py and this list"
    )
    for name in PAGE_MODULES:
        assert routers._exists(name), name  # pyright: ignore[reportPrivateUsage]
        module = importlib.import_module(name)
        assert module.router is not None, name


def test_page_routers_returns_one_router_per_module() -> None:
    assert len(routers.page_routers()) == len(PAGE_MODULES)


@pytest.mark.parametrize("name", ["tl_web.pages.nowhere", "tl_web_nowhere.pages"])
def test_a_missing_page_module_is_skipped(name: str) -> None:
    assert routers._exists(name) is False  # pyright: ignore[reportPrivateUsage]
