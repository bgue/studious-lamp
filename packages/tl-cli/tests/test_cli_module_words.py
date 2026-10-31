"""Every module handler call in `tl_cli` is preceded by the module word check (RM-S4).

The finder is the one the sweep tool uses, loaded by path (``dev/tools/gate_sweep.py`` is a script,
not a package): a call with a command as its second argument to a ``handle_*`` name imported from a
``tl_mod_*`` module (or ``.handler``) must have an earlier ``require_command(uow, <that command>)``
in the same function; a bulk helper (``apply_plan``, ``load_standards``) needs the pre-flight
``require_commands`` first. This is the pin that keeps a sixth path from running a module handler
without the check (roles-mvp.md risk R1).
"""

from __future__ import annotations

import importlib.util
import re
import sys
from pathlib import Path
from types import ModuleType

import pytest

ROOT = Path(__file__).resolve().parents[3]
CLI_DIR = ROOT / "packages" / "tl-cli" / "src" / "tl_cli"


def load_sweep() -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        "gate_sweep", ROOT / "dev" / "tools" / "gate_sweep.py"
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["gate_sweep"] = module  # dataclasses look the module up by name
    spec.loader.exec_module(module)
    return module


sweep = load_sweep()


def cli_files() -> list[Path]:
    return [p for p in sweep.target_files() if p.name != "embedded.py"]


def relative(path: Path) -> str:
    return str(path.relative_to(ROOT))


def test_the_sweep_scans_every_cli_module_but_the_two_it_skips() -> None:
    scanned = {p.name for p in cli_files()}
    assert {"doc.py", "corr.py", "xer.py", "tag.py", "cost.py", "standards.py"} <= scanned
    assert {"admin_roles.py", "main.py"}.isdisjoint(scanned)
    assert scanned == {p.name for p in CLI_DIR.rglob("*.py")} - {"admin_roles.py", "main.py"}


def test_no_module_handler_call_in_tl_cli_is_ungated() -> None:
    total = 0
    for path in cli_files():
        calls = sweep.find_calls(path.read_text(encoding="utf-8"), relative(path))
        total += len(calls)
        ungated = [(c.file, c.line, c.function) for c in calls if not c.gated]
        assert not ungated, ungated
    assert total > 100  # the sweep placed 109 gates in 24 files


def test_no_bulk_helper_call_in_tl_cli_lacks_its_pre_flight() -> None:
    helpers = 0
    for path in cli_files():
        calls = sweep.find_helper_calls(path.read_text(encoding="utf-8"), relative(path))
        helpers += len(calls)
        ungated = [(c.file, c.line, c.variable) for c in calls if not c.gated]
        assert not ungated, ungated
    assert helpers >= 3  # doc import, tag import, standards


def test_every_cli_module_with_a_handler_call_imports_its_gate() -> None:
    for path in cli_files():
        source = path.read_text(encoding="utf-8")
        if sweep.find_calls(source, relative(path)):
            assert re.search(r"\brequire_command\b", source), relative(path)


# --- the finder itself: what it counts as gated ---------------------------------------------------

HEAD = "from tl_mod_x.handlers import handle_do, Do\nfrom tl_cli.session import require_command\n"


def calls_of(body: str) -> list[tuple[int, bool]]:
    found = sweep.find_calls(HEAD + body)
    return [(c.line, c.gated) for c in found]


def test_a_call_with_the_gate_before_it_is_gated() -> None:
    body = "def f(uow):\n    cmd = Do()\n    require_command(uow, cmd)\n    handle_do(uow, cmd)\n"
    assert calls_of(body) == [(6, True)]


def test_a_call_with_no_gate_is_reported() -> None:
    body = "def f(uow):\n    cmd = Do()\n    handle_do(uow, cmd)\n"
    assert calls_of(body) == [(5, False)]


def test_a_gate_after_the_call_does_not_count() -> None:
    body = "def f(uow):\n    cmd = Do()\n    handle_do(uow, cmd)\n    require_command(uow, cmd)\n"
    assert calls_of(body) == [(5, False)]


def test_a_gate_for_another_command_does_not_count() -> None:
    body = (
        "def f(uow):\n    one = Do()\n    two = Do()\n    require_command(uow, one)\n"
        "    handle_do(uow, two)\n"
    )
    assert calls_of(body) == [(7, False)]


def test_a_gate_in_another_function_does_not_count() -> None:
    body = (
        "def g(uow, cmd):\n    require_command(uow, cmd)\n\n\n"
        "def f(uow):\n    cmd = Do()\n    handle_do(uow, cmd)\n"
    )
    assert calls_of(body) == [(9, False)]


def test_a_handler_reference_and_a_handler_parameter_are_found() -> None:
    body = "def f(uow, spec, cmd):\n    spec.handler(uow, cmd)\n"
    assert calls_of(body) == [(4, False)]
    body = "def f(uow, cmd, handler):\n    handler(uow, cmd)\n"
    assert calls_of(body) == [(4, False)]


def test_a_bulk_helper_needs_its_pre_flight() -> None:
    head = "from tl_mod_x.imports import apply_plan\nfrom tl_cli.session import require_commands\n"
    bare = head + "def f(uow, plan):\n    apply_plan(uow, plan)\n"
    assert [(c.line, c.gated) for c in sweep.find_helper_calls(bare)] == [(4, False)]
    covered = (
        head
        + "def f(uow, plan):\n    require_commands(uow, (Do,), actor='a', scope='s')\n"
        + "    apply_plan(uow, plan)\n"
    )
    assert [(c.line, c.gated) for c in sweep.find_helper_calls(covered)] == [(5, True)]


@pytest.mark.parametrize(
    ("file", "marker"),
    [
        ("doc.py", "doc"),
        ("corr_clock.py", "correspondence clocks"),
        ("xer.py", "schedule"),
        ("tag.py", "engineering"),
        ("schema_pkg.py", "schemareg"),
        ("cost.py", "cost"),
    ],
)
def test_removing_one_gate_per_module_is_reported(file: str, marker: str) -> None:
    """The mutant the security review reads for: the first gate of a file taken out."""
    path = CLI_DIR / file
    source = path.read_text(encoding="utf-8")
    mutant = re.sub(r"^\s*require_command\([^\n]*\)\n", "", source, count=1, flags=re.M)
    assert mutant != source, marker
    before = [c for c in sweep.find_calls(source, file) if not c.gated]
    after = [c for c in sweep.find_calls(mutant, file) if not c.gated]
    assert before == [] and len(after) >= 1, marker
