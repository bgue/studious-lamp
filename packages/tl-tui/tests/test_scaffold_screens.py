"""The scaffold register and record on `FakeClient`, through the Textual pilot (P2-I4B-T07b).

Model: `test_punch_screens.py`. The register only reads; `x` and `X` write the export under the
working directory, which each test points at its own `tmp_path`.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Any

import pytest
from fakes import SCOPE, FakeClient
from fakes_scaffold import seed_scaffolds
from helpers import run_pilot, screen_text, settle
from textual.pilot import Pilot
from tl_core.services.errors import RecordNotFoundError, ServiceError
from tl_mod_scaffold.views import EXPORT_COLUMNS
from tl_tui.app import TlApp
from tl_tui.widgets.scaffold_register import ScaffoldLogScreen, ScaffoldScreen

SIZES = [(80, 40), (170, 44)]
PROJECT = "P123"
KEY_DESIGNED = "P123-SCF-0001"
KEY_INSPECTED = "P123-SCF-0003"
KEY_IN_USE = "P123-SCF-0004"
KEY_MODIFY = "P123-SCF-0005"
Step = Callable[[Pilot[Any], TlApp], Awaitable[None]]


def make_app() -> tuple[TlApp, FakeClient]:
    client = FakeClient()
    seed_scaffolds(client, PROJECT)
    return TlApp(client, scope=SCOPE, actor="user:kim"), client


def run(app: TlApp, steps: Step, size: tuple[int, int] = (170, 44)) -> None:
    async def go(pilot: Pilot[Any]) -> None:
        await settle(pilot)
        await steps(pilot, app)

    run_pilot(app, go, size=size)


def open_register(app: TlApp) -> None:
    app.push_screen(ScaffoldLogScreen(app.client, PROJECT))


def text_after(keys: list[str], size: tuple[int, int] = (170, 44)) -> str:
    """The screen's text after the register is open and the keys are pressed in order."""
    seen: dict[str, str] = {}

    async def steps(pilot: Pilot[Any], app: TlApp) -> None:
        open_register(app)
        await settle(pilot)
        for key in keys:
            await pilot.press(key)
            await settle(pilot)
        seen["text"] = screen_text(app)

    app, _client = make_app()
    run(app, steps, size=size)
    return seen["text"]


# --- the register ----------------------------------------------------------------------------


@pytest.mark.parametrize("size", SIZES)
def test_the_register_lists_the_seeded_rows_within_the_width(size: tuple[int, int]) -> None:
    text = text_after([], size=size)
    for key in (KEY_DESIGNED, KEY_INSPECTED, KEY_IN_USE, KEY_MODIFY):
        assert key in text
    assert all(len(line) <= size[0] for line in text.splitlines()), f"overflow at {size}"
    header = next(line for line in text.splitlines() if "Number" in line)
    assert header.index("Number") < header.index("State")
    if "Subject" in header:  # a narrow register drops Subject first (SCAFFOLD_DROP is the order)
        assert header.index("Subject") < header.index("State")


def test_the_summary_line_names_the_counts() -> None:
    text = text_after([])
    assert "5 scaffolds: 1 Designed, 1 Erecting, 1 Inspected, 1 In Use, 1 Modify" in text


def test_s_cycles_the_state_filter_to_one_state() -> None:
    # all, then Requested, Designed, Erecting, Inspected, In Use: five presses reach In Use
    text = text_after(["s"] * 5)
    assert KEY_IN_USE in text
    for key in (KEY_DESIGNED, KEY_INSPECTED, KEY_MODIFY):
        assert key not in text
    assert "state In Use" in text


def test_o_narrows_to_the_overdue_scaffolds() -> None:
    text = text_after(["o"])
    assert KEY_INSPECTED in text and KEY_MODIFY in text  # both standing, due before today
    assert KEY_DESIGNED not in text
    assert KEY_IN_USE not in text  # due 2099
    assert "overdue only" in text


def test_enter_opens_the_record_and_esc_returns_to_the_register() -> None:
    seen: dict[str, Any] = {}

    async def steps(pilot: Pilot[Any], app: TlApp) -> None:
        open_register(app)
        await settle(pilot)
        await pilot.press("enter")
        await settle(pilot)
        seen["record"] = app.screen
        seen["record_text"] = screen_text(app)
        await pilot.press("escape")
        await settle(pilot)
        seen["back"] = app.screen

    app, _client = make_app()
    run(app, steps)
    assert isinstance(seen["record"], ScaffoldScreen)
    assert "Inspections" in seen["record_text"]
    assert isinstance(seen["back"], ScaffoldLogScreen)


@pytest.mark.parametrize("size", SIZES)
def test_the_record_lists_the_inspections_oldest_first(size: tuple[int, int]) -> None:
    seen: dict[str, str] = {}

    async def steps(pilot: Pilot[Any], app: TlApp) -> None:
        app.push_screen(ScaffoldScreen(app.client, PROJECT, KEY_MODIFY))
        await settle(pilot)
        seen["text"] = screen_text(app)

    app, _client = make_app()
    run(app, steps, size=size)
    text = seen["text"]
    assert all(len(line) <= size[0] for line in text.splitlines())
    assert "Modify reason" in text and "Cracked toe board" in text
    dated = [line.split()[0] for line in text.splitlines() if " uma " in line]
    assert dated == ["2026-09-01", "2026-10-02"]
    assert "Fail" in text and "Pass" in text


def test_x_writes_the_csv_export_under_the_working_directory(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    seen: dict[str, str] = {}

    async def steps(pilot: Pilot[Any], app: TlApp) -> None:
        open_register(app)
        await settle(pilot)
        await pilot.press("x")
        await settle(pilot)
        seen["status"] = screen_text(app)

    app, _client = make_app()
    run(app, steps)
    target = tmp_path / "scaffolds-P123.csv"
    assert target.exists()
    first = target.read_text(encoding="utf-8").splitlines()[0]
    assert first == ",".join(EXPORT_COLUMNS)
    assert len(target.read_text(encoding="utf-8").splitlines()) == 6  # header and five rows
    assert "Wrote ./scaffolds-P123.csv" in seen["status"]


def test_capital_x_writes_the_jsonl_export(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)

    async def steps(pilot: Pilot[Any], app: TlApp) -> None:
        open_register(app)
        await settle(pilot)
        await pilot.press("X")
        await settle(pilot)

    app, _client = make_app()
    run(app, steps)
    lines = (tmp_path / "scaffolds-P123.jsonl").read_text(encoding="utf-8").splitlines()
    assert len(lines) == 5
    assert lines[0].startswith('{"key": "P123-SCF-0001"')


def test_a_client_error_on_the_register_shows_its_text(monkeypatch: pytest.MonkeyPatch) -> None:
    app, client = make_app()

    def refuse(*args: Any, **kwargs: Any) -> None:
        raise ServiceError("the register is closed")

    monkeypatch.setattr(client, "list_scaffolds", refuse)
    seen: dict[str, str] = {}

    async def steps(pilot: Pilot[Any], app: TlApp) -> None:
        open_register(app)
        await settle(pilot)
        seen["text"] = screen_text(app)

    run(app, steps)
    assert "! the register is closed" in seen["text"]


def test_a_missing_scaffold_shows_one_text_on_the_record() -> None:
    seen: dict[str, str] = {}

    async def steps(pilot: Pilot[Any], app: TlApp) -> None:
        app.push_screen(ScaffoldScreen(app.client, PROJECT, "P123-SCF-0099"))
        await settle(pilot)
        seen["text"] = screen_text(app)

    app, client = make_app()
    with pytest.raises(RecordNotFoundError):
        client.get_scaffold(PROJECT, "P123-SCF-0099")
    run(app, steps)
    assert "No such scaffold." in seen["text"]


def test_a_client_error_on_the_record_shows_its_text(monkeypatch: pytest.MonkeyPatch) -> None:
    app, client = make_app()

    def refuse(*args: Any, **kwargs: Any) -> None:
        raise ServiceError("the record is locked")

    monkeypatch.setattr(client, "get_scaffold", refuse)
    seen: dict[str, str] = {}

    async def steps(pilot: Pilot[Any], app: TlApp) -> None:
        app.push_screen(ScaffoldScreen(app.client, PROJECT, KEY_DESIGNED))
        await settle(pilot)
        seen["text"] = screen_text(app)

    run(app, steps)
    assert "! the record is locked" in seen["text"]
