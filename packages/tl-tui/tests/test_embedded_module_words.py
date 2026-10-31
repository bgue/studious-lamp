"""Every module handler call in `tl_tui/embedded.py` follows `self._command_gate` (RM-S4).

The same finder as the CLI pin (``dev/tools/gate_sweep.py``, loaded by path): a call with a command
as its second argument to a ``handle_*`` name imported from a ``tl_mod_*`` module, to ``.handler``
or to a ``handler`` parameter needs an earlier ``self._command_gate(uow, <that command>)`` in the
same function. The embedded client is the TUI's way to the services, so a missed gate is a way
round the module roles (roles-mvp.md risk R1).
"""

from __future__ import annotations

import importlib.util
import re
import sys
from pathlib import Path
from types import ModuleType

ROOT = Path(__file__).resolve().parents[3]
EMBEDDED = ROOT / "packages" / "tl-tui" / "src" / "tl_tui" / "embedded.py"


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
SOURCE = EMBEDDED.read_text(encoding="utf-8")


def test_the_sweep_scans_embedded_py() -> None:
    assert EMBEDDED in sweep.target_files()


def test_no_module_handler_call_in_embedded_py_is_ungated() -> None:
    calls = sweep.find_calls(SOURCE, "embedded.py")
    assert len(calls) >= 10  # the sweep gated 16 handler calls in this file
    ungated = [(c.line, c.function) for c in calls if not c.gated]
    assert not ungated, ungated


def test_no_bulk_helper_call_in_embedded_py_lacks_its_pre_flight() -> None:
    calls = sweep.find_helper_calls(SOURCE, "embedded.py")
    assert [(c.line, c.variable) for c in calls if not c.gated] == []


def test_the_gate_is_the_embedded_clients_own_method() -> None:
    assert sweep.EMBEDDED_GATE == "_command_gate"
    assert re.search(r"def _command_gate\(self, uow: UnitOfWork, cmd: Command\)", SOURCE)
    assert len(re.findall(r"self\._command_gate\(", SOURCE)) >= 10


def test_the_old_controller_gate_does_not_stand_in_for_a_module_command() -> None:
    """`_controller_gate` is still defined (the allowed-actions table asks for it) but no module
    handler call is gated by it alone: the finder counts `_command_gate` only."""
    mutant = SOURCE.replace("self._command_gate(", "self._controller_gate(")
    assert mutant != SOURCE
    ungated = [c for c in sweep.find_calls(mutant, "embedded.py") if not c.gated]
    assert len(ungated) >= 10


def test_removing_one_gate_is_reported() -> None:
    mutant = re.sub(r"^\s*self\._command_gate\([^\n]*\)\n", "", SOURCE, count=1, flags=re.M)
    assert mutant != SOURCE
    before = [c for c in sweep.find_calls(SOURCE, "embedded.py") if not c.gated]
    after = [c for c in sweep.find_calls(mutant, "embedded.py") if not c.gated]
    assert before == [] and len(after) >= 1


def test_a_gate_moved_after_its_call_is_reported() -> None:
    body = (
        "from tl_mod_x.handlers import handle_do, Do\n\n\n"
        "class C:\n    def f(self, uow):\n        cmd = Do()\n"
        "        handle_do(uow, cmd)\n        self._command_gate(uow, cmd)\n"
    )
    assert [(c.line, c.gated) for c in sweep.find_calls(body)] == [(7, False)]
    fixed = body.replace(
        "        handle_do(uow, cmd)\n        self._command_gate(uow, cmd)\n",
        "        self._command_gate(uow, cmd)\n        handle_do(uow, cmd)\n",
    )
    assert [(c.line, c.gated) for c in sweep.find_calls(fixed)] == [(8, True)]
