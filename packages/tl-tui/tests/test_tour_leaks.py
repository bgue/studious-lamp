"""The tour checks its own screens as strictly as the plain walk does (P1-UX-S5, S4 review F2).

A plain screenshot that carries a record-type key, a package reference or a ULID prints a
``LEAK <shot> ...`` line and makes the run exit 1; a clean one passes.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from typing import Any

import pytest
from fakes import SCOPE, FakeClient
from helpers import run_pilot
from textual.pilot import Pilot
from tl_tui.app import TlApp


def _load_tourkit() -> Any:
    """``dev/tour/tourkit.py`` is a script helper, not a package: load it by path."""
    path = Path(__file__).resolve().parents[3] / "dev" / "tour" / "tourkit.py"
    spec = importlib.util.spec_from_file_location("tourkit_under_test", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module  # its dataclasses look their module up by name
    spec.loader.exec_module(module)
    return module


tk: Any = _load_tourkit()

CLEAN = "Valve data  Body material  Structural  Design  Control valve"
ULID = "01JC3XQ8Z4V5N7R9T2K6M8P0QW"


class _Workspace:
    """Stands in for the tour's ``Workspace``: it only remembers what was saved."""

    def __init__(self) -> None:
        self.saved: list[str] = []

    def save(self, name: str, svg: str) -> None:
        self.saved.append(name)


@pytest.fixture(autouse=True)
def _no_leaks_before() -> None:
    tk.LEAKS.clear()


def _shoot(text: str, name: str = "99-test") -> _Workspace:
    """Take one plain shot of a signed-in app whose screen text is ``text``."""
    ws = _Workspace()
    app = TlApp(FakeClient(), scope=SCOPE, actor="user:kim", is_admin=False)

    async def scenario(pilot: Pilot[Any]) -> None:
        await pilot.pause()
        original = tk.screen_text
        tk.screen_text = lambda _app: text
        try:
            tk.shot_tui(ws, app, name, "test")
        finally:
            tk.screen_text = original

    run_pilot(app, scenario)
    return ws


def test_a_clean_plain_shot_passes() -> None:
    ws = _shoot(CLEAN)
    assert ws.saved == ["99-test"]
    assert tk.LEAKS == []
    assert tk.report_leaks() == 0


@pytest.mark.parametrize(
    ("leak", "token"),
    [
        ("core.Record", "core.Record"),
        ("co.acme.engineering@3.2.0", "co.acme.engineering@3.2.0"),
        (ULID, ULID),
        ("valve_data.body_material", "valve_data.body_material"),
    ],
    ids=["type-key", "package-ref", "ulid", "property-key"],
)
def test_a_plain_shot_with_technical_text_prints_leak_and_exits_1(
    leak: str, token: str, capsys: pytest.CaptureFixture[str]
) -> None:
    _shoot(f"{CLEAN}\nType {leak} here", "99-leaky")
    assert tk.LEAKS == [f"99-leaky {token!r}"]
    assert tk.report_leaks() == 1
    assert capsys.readouterr().out == f"LEAK 99-leaky {token!r}\n"


def test_a_technical_shot_is_not_checked() -> None:
    ws = _Workspace()
    app = TlApp(FakeClient(), scope=SCOPE, actor="user:kim", is_admin=True)

    async def scenario(pilot: Pilot[Any]) -> None:
        await pilot.pause()
        original = tk.screen_text
        tk.screen_text = lambda _app: "core.Record " + ULID
        try:
            tk.shot_tui(ws, app, "99-tech", "test", technical=True)
        finally:
            tk.screen_text = original

    run_pilot(app, scenario)
    assert tk.LEAKS == []
    assert tk.report_leaks() == 0
