"""P2-X4 T02a: `tl new module` emits a loadable spec with the command hook and its entry point.

Provided by the supervisor; the ticket copies it byte-identical to
``packages/tl-cli/tests/test_new_module_spec.py``.
"""

from __future__ import annotations

import importlib
import sys
from collections.abc import Iterator
from pathlib import Path

import pytest
from scaffold_support import tl_new
from tl_core.modules import ModuleSpec, resolve_hook, use_modules

PACKAGE = "tl_mod_inspection"


@pytest.fixture
def spec(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[ModuleSpec]:
    assert tl_new(tmp_path, "module", "inspection").exit_code == 0
    monkeypatch.syspath_prepend(str(tmp_path / "packages/tl-modules/inspection/src"))
    module = importlib.import_module(f"{PACKAGE}.module")
    yield module.spec()
    for name in [n for n in sys.modules if n == PACKAGE or n.startswith(PACKAGE + ".")]:
        del sys.modules[name]


def test_the_spec_names_the_module_and_the_commands_hook(spec: ModuleSpec) -> None:
    assert spec.name == "inspection"
    assert spec.commands == f"{PACKAGE}.commands:COMMANDS"


def test_the_commands_hook_resolves_to_no_rows_until_the_author_adds_one(spec: ModuleSpec) -> None:
    assert resolve_hook(spec, "commands") == ()
    with use_modules([spec]):
        assert spec.record_types == frozenset()


def test_the_entry_point_names_the_spec(tmp_path: Path) -> None:
    tl_new(tmp_path, "module", "inspection")
    text = (tmp_path / "packages/tl-modules/inspection/pyproject.toml").read_text()
    assert '[project.entry-points."throughline.modules"]' in text
    assert f'inspection = "{PACKAGE}.module:spec"' in text
