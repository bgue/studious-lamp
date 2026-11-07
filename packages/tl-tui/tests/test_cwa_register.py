"""The CWA register screen (T05e, D51)."""

from __future__ import annotations

from typing import Any

import pytest
from fakes import SCOPE, FakeClient
from fakes_awp import PROJECT, seed_awp
from helpers import panel_of, run_pilot, screen_text, settle, static_of
from tl_core.services.errors import RecordNotFoundError
from tl_mod_awp.views import CwaRow
from tl_tui.app import TlApp
from tl_tui.cwa_text import (
    CwaLine,
    cwa_cells,
    cwa_lines,
    cwa_page,
    cwa_summary,
    visible_lines,
)
from tl_tui.layout import plain_lines
from tl_tui.widgets.cwa_register import CwaRegisterScreen

WIDTHS = (80, 170)


def need(ok: bool, what: str) -> None:
    assert ok, what


def seeded_client() -> FakeClient:
    client = FakeClient()
    seed_awp(client)
    return client


def by_code(lines: list[CwaLine], code: str) -> CwaLine:
    return next(line for line in lines if line.row.code == code)


def check_lines(client: FakeClient) -> None:
    cwas = client.list_cwas(PROJECT)
    path = client.get_path(PROJECT)
    cwps = client.list_cwps(PROJECT)
    lines = cwa_lines(cwas, path, cwps)
    codes = [line.row.code for line in lines]
    need(codes == ["A1", "A2"], f"order {codes}")
    need(by_code(lines, "A1").position == 1 and by_code(lines, "A2").position == 2, "positions")
    need(by_code(lines, "A1").steps == 2, "the path of version 2 has two steps")
    need(len(by_code(lines, "A1").cwps) == 2 and len(by_code(lines, "A2").cwps) == 1, "CWPs")
    need(cwa_cells(by_code(lines, "A1"))[3] == "2", "CWP count cell")
    need(len(visible_lines(lines, False)) == 1, "the retired A2 is hidden by default")
    need(len(visible_lines(lines, True)) == 2, "show_retired keeps every area")
    extra = CwaRow(id="CWA-A0", code="A0", title="Area A0", location_text=None, retired=False)
    off = cwa_lines([extra, *cwas], path, cwps)
    need([line.row.code for line in off] == ["A1", "A2", "A0"], "an area off the path is last")
    need(cwa_cells(off[-1])[2] == "—", "an area off the path reads — for its position")
    bare = cwa_lines(cwas, None, [])
    need([line.row.code for line in bare] == ["A1", "A2"], "no path: order by code")
    need(all(line.position is None and line.steps == 0 for line in bare), "no path: no positions")


def check_page(client: FakeClient) -> None:
    lines = cwa_lines(
        client.list_cwas(PROJECT), client.get_path(PROJECT), client.list_cwps(PROJECT)
    )
    a1 = by_code(lines, "A1")
    need(cwa_summary(a1) == "Position 1 of 2 · 2 CWPs · 65.5 h", f"summary {cwa_summary(a1)!r}")
    for width in WIDTHS:
        text = plain_lines(cwa_page(a1, panel=True), width=width)
        for heading in ("Location", "CWPs"):
            need(heading in [line.strip() for line in text], f"no heading {heading!r}")
        need(not any(line.strip() in ("Files", "Links") for line in text), "Files shown")
    technical = plain_lines(cwa_page(a1, technical=True), width=80)
    need(any("CWA-A1" in line for line in technical), "technical mode lacks the id")
    plain = plain_lines(cwa_page(a1), width=80)
    need(not any("CWA-A1" in line for line in plain), "plain mode shows the id")
    empty = CwaLine(row=by_code(lines, "A2").row, position=None, cwps=(), steps=2)
    need("No CWPs in this area" in plain_lines(cwa_page(empty), width=80), "no note when empty")


def check_retired(client: FakeClient) -> None:
    # the seed has one retired area (A2); the screen hides it until r is pressed
    app = TlApp(client, scope=SCOPE, actor="user:kim")

    async def steps(pilot: Any, screen: CwaRegisterScreen) -> None:
        need(len(screen.shown) == 1, f"retired hidden at first: {len(screen.shown)} rows")
        await pilot.press("r")
        await settle(pilot)
        need(len(screen.shown) == 2, f"r shows the retired area: {len(screen.shown)} rows")
        await pilot.press("r")
        await settle(pilot)
        need(len(screen.shown) == 1, "r again hides it")

    async def go(pilot: Any) -> None:
        screen = CwaRegisterScreen(client, PROJECT)
        app.push_screen(screen)
        await settle(pilot)
        need(isinstance(app.screen, CwaRegisterScreen), "the CWA register did not open")
        await steps(pilot, screen)

    run_pilot(app, go, size=(120, 40))


def check_mount(client: FakeClient, width: int) -> None:
    app = TlApp(client, scope=SCOPE, actor="user:kim")

    async def go(pilot: Any) -> None:
        screen = CwaRegisterScreen(client, PROJECT)
        app.push_screen(screen)
        await settle(pilot)
        need(isinstance(app.screen, CwaRegisterScreen), "the CWA register did not open")
        lines = screen_text(pilot.app).splitlines()
        too_wide = [line for line in lines if len(line) > width]
        need(not too_wide, f"lines wider than {width}: {too_wide[:1]}")
        header = next((line for line in lines if "Number" in line and "Subject" in line), "")
        need(bool(header), "no header row with Number and Subject")
        need(header.index("Subject") < header.index("Position"), "Subject starts after column 3")
        need("Area A1" in "\n".join(lines), "no subject shown")
        if width >= 170:
            panel = panel_of(screen)
            need("A1 · Area A1" in panel and "Active" in panel, f"panel {panel!r}")
            need("Position 1 of 2 · 2 CWPs · 65.5 h" in panel, f"panel summary {panel!r}")
        status = static_of(screen, "#log-status")
        need(not status.startswith("!"), f"an error in the status line: {status!r}")

    run_pilot(app, go, size=(width, 40))


def test_missing() -> None:
    client = seeded_client()

    def no_path(project: str, version: int | None = None) -> None:
        raise RecordNotFoundError(f"no path {project!r} at version {version!r}")

    client.get_path = no_path  # type: ignore[method-assign]
    app = TlApp(client, scope=SCOPE, actor="user:kim")

    async def go(pilot: Any) -> None:
        screen = CwaRegisterScreen(client, PROJECT)
        app.push_screen(screen)
        await settle(pilot)
        need(len(screen.shown) == 1, f"the area list is empty without a path: {len(screen.shown)}")
        need(cwa_cells(screen.shown[0])[2] == "—", "no path: the position reads —")
        status = static_of(screen, "#log-status")
        need(not status.startswith("!"), f"no path is an error: {status!r}")

    run_pilot(app, go, size=(120, 40))


def test_lines() -> None:
    check_lines(seeded_client())


def test_page() -> None:
    check_page(seeded_client())


def test_retired() -> None:
    check_retired(seeded_client())


@pytest.mark.parametrize("width", WIDTHS)
def test_mount(width: int) -> None:
    check_mount(seeded_client(), width)


def test_the_state_words_are_active_and_retired_and_the_position_says_of_how_many() -> None:
    client = seeded_client()
    lines = cwa_lines(
        client.list_cwas(PROJECT), client.get_path(PROJECT), client.list_cwps(PROJECT)
    )
    a1, a2 = by_code(lines, "A1"), by_code(lines, "A2")
    assert "Active" in plain_lines(cwa_page(a1), width=80)[1]
    assert "Retired" in plain_lines(cwa_page(a2), width=80)[1]
    assert cwa_summary(a1).startswith("Position 1 of 2")
    assert cwa_summary(a2).startswith("Position 2 of 2")  # M is the steps of the path


def test_with_no_path_the_positions_read_a_dash() -> None:
    client = seeded_client()

    def no_path(project: str, version: int | None = None) -> None:
        raise RecordNotFoundError(f"no path {project!r} at version {version!r}")

    client.get_path = no_path  # type: ignore[method-assign]
    app = TlApp(client, scope=SCOPE, actor="user:kim")
    seen: dict[str, Any] = {}

    async def go(pilot: Any) -> None:
        screen = CwaRegisterScreen(client, PROJECT)
        app.push_screen(screen)
        await settle(pilot)
        seen["cells"] = [cwa_cells(line) for line in screen.shown]

    run_pilot(app, go, size=(120, 40))
    assert seen["cells"]
    assert all(cells[2] == "—" for cells in seen["cells"])


def test_enter_does_nothing_on_the_cwa_register_and_f5_reads_again() -> None:
    client = seeded_client()
    reads: list[str] = []
    read = client.list_cwas

    def counted(project: str) -> list[CwaRow]:
        reads.append(project)
        return read(project)

    client.list_cwas = counted  # type: ignore[method-assign]
    app = TlApp(client, scope=SCOPE, actor="user:kim")

    async def go(pilot: Any) -> None:
        screen = CwaRegisterScreen(client, PROJECT)
        app.push_screen(screen)
        await settle(pilot)
        before = len(reads)
        await pilot.press("enter")
        await settle(pilot)
        assert app.screen is screen  # no record opens
        assert len(reads) == before
        await pilot.press("f5")
        await settle(pilot)
        assert len(reads) == before + 1

    run_pilot(app, go, size=(120, 40))
