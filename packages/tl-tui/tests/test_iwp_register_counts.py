"""The IWP log's count columns, its summary with the discipline and text filters, the ``mine``
flag at open, and the backlog's read limit (P2-I5 T06c1), through the Textual pilot over
``FakeClient``."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from fakes import SCOPE, FakeClient
from fakes_iwp import PROJECT, seed_iwp
from helpers import run_pilot, settle
from textual.pilot import Pilot
from textual.widgets import DataTable
from tl_mod_awp.iwp_counts import IwpCountRow
from tl_tui.app import TlApp
from tl_tui.widgets.backlog_screen import BacklogScreen
from tl_tui.widgets.iwp_register import IwpRegisterScreen

WIDTH = 200
HEIGHT = 44
PIP1 = f"{PROJECT}-IWP-PIP-0001"
PIP2 = f"{PROJECT}-IWP-PIP-0002"
CIV1 = f"{PROJECT}-IWP-CIV-0001"
SIGNED_IN = "user:sue"  # the foreman of PIP-0002 and CIV-0001


def seeded() -> FakeClient:
    client = FakeClient()
    seed_iwp(client)
    client.load_counts(
        PROJECT,
        [
            IwpCountRow(
                number=PIP2,
                state_since="2026-10-27",
                ready_ok=2,
                ready_total=3,
                evaluated=True,
                open_blocking=1,
            ),
            IwpCountRow(
                number=CIV1,
                state_since=None,
                ready_ok=0,
                ready_total=0,
                evaluated=False,
                open_blocking=0,
            ),
        ],
    )
    return client


def mount(
    client: FakeClient,
    steps: Callable[[Pilot[None], TlApp, IwpRegisterScreen], Awaitable[None]],
    *,
    actor: str = SIGNED_IN,
    mine: bool = False,
) -> None:
    app = TlApp(client, scope=SCOPE, actor=actor)

    async def go(pilot: Pilot[None]) -> None:
        screen = IwpRegisterScreen(client, PROJECT, mine=mine)
        app.push_screen(screen)
        await settle(pilot)
        await steps(pilot, app, screen)

    run_pilot(app, go, size=(WIDTH, HEIGHT))


def cells_of(screen: IwpRegisterScreen, number: str) -> list[str]:
    table = screen.query_one("#log-table", DataTable)
    return [str(cell) for cell in table.get_row(number)]


def test_log_shows_the_ready_and_blocking_counts() -> None:
    seen: dict[str, Any] = {}

    async def steps(pilot: Pilot[None], app: TlApp, screen: IwpRegisterScreen) -> None:
        seen["pip2"] = cells_of(screen, PIP2)
        seen["civ1"] = cells_of(screen, CIV1)
        table = screen.query_one("#log-table", DataTable)
        seen["header"] = [str(column.label) for column in table.columns.values()]

    mount(seeded(), steps)
    assert seen["header"][-3:] == ["Ready", "Blocking", "Since"]
    assert seen["pip2"][-3:] == ["2/3", "1", "2026-10-27"]
    # a row with no count in the read (never evaluated, no state date) reads as none
    assert seen["civ1"][-3:] == ["—", "0", "—"]


def test_a_missing_count_row_reads_as_no_counts() -> None:
    seen: dict[str, Any] = {}
    client = seeded()
    client.load_counts(PROJECT, [])

    async def steps(pilot: Pilot[None], app: TlApp, screen: IwpRegisterScreen) -> None:
        # the table hides a column whose value is the same on every shown row, so the cells
        # are read from the row hook
        row = next(v for v in screen.views if v.number == PIP2)
        seen["cells"] = list(screen.row_cells(row))

    mount(client, steps)
    assert seen["cells"][-3:] == ["—", "—", "—"]


def test_the_discipline_key_names_the_discipline_in_the_summary() -> None:
    seen: dict[str, str] = {}

    async def steps(pilot: Pilot[None], app: TlApp, screen: IwpRegisterScreen) -> None:
        seen["before"] = screen.summary_text()
        await pilot.press("d")
        await settle(pilot)
        seen["after"] = screen.summary_text()

    mount(seeded(), steps)
    assert seen["before"] == "4 IWPs"
    assert seen["after"].startswith("2 of 4 IWPs, discipline ")
    assert seen["after"] != seen["before"]


def test_the_filter_text_shows_in_the_summary() -> None:
    seen: dict[str, str] = {}

    async def steps(pilot: Pilot[None], app: TlApp, screen: IwpRegisterScreen) -> None:
        await pilot.press("slash")
        await settle(pilot)
        await pilot.press(*"supports")
        await settle(pilot)
        seen["summary"] = screen.summary_text()
        seen["shown"] = ",".join(row.number for row in screen.shown)

    mount(seeded(), steps)
    assert seen["summary"] == "1 of 4 IWPs, filter 'supports'"
    assert seen["shown"] == PIP2


def test_mine_at_open_shows_only_the_actors_iwps() -> None:
    seen: dict[str, Any] = {}

    async def steps(pilot: Pilot[None], app: TlApp, screen: IwpRegisterScreen) -> None:
        seen["mine"] = screen.mine
        seen["shown"] = [row.number for row in screen.shown]
        seen["summary"] = screen.summary_text()

    mount(seeded(), steps, mine=True)
    assert seen["mine"] is True
    assert seen["shown"] == [CIV1, PIP2]  # foreman user:sue, by number
    assert seen["summary"].startswith("2 of 4 IWPs, foreman ")


def test_the_backlog_reads_500_iwps_and_says_so() -> None:
    client = seeded()
    calls: list[dict[str, Any]] = []
    listed = client.list_iwps

    def recording(project: str, **kwargs: Any) -> list[Any]:
        calls.append(kwargs)
        rows = listed(project)
        # the fake clamps at 200; a stand-in for a read that returns the full 500
        return [
            row.model_copy(update={"number": f"{row.number}-{n}"})
            for row in rows
            for n in range(125)
        ][: kwargs["limit"]]

    client.list_iwps = recording  # type: ignore[method-assign]
    seen: dict[str, str] = {}
    app = TlApp(client, scope=SCOPE, actor=SIGNED_IN)

    async def go(pilot: Pilot[None]) -> None:
        screen = BacklogScreen(client, PROJECT)
        app.push_screen(screen)
        await settle(pilot)
        seen["summary"] = screen.summary_text()

    run_pilot(app, go, size=(WIDTH, HEIGHT))
    assert calls and all(call == {"limit": 500} for call in calls)
    assert seen["summary"].startswith("first 500 IWPs · ")
