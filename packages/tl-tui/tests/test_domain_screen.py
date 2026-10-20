"""The RFI log, the Commercial register and the evidence trail on the fake client (P1-I6).

Opened with Ctrl+G, driven with a pilot. The text of the rows is tested in `test_rfi_text.py`,
`test_commercial_text.py` and `test_evidence_text.py`; here the keys, the filters, the plain
person's empty register and the day stepping of the evidence view.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from datetime import timedelta

from fakes import SCOPE, FakeClient
from fakes_correspondence import seed_domains
from helpers import run_pilot, screen_text
from textual.pilot import Pilot
from textual.widgets import DataTable, Static
from tl_tui.app import TlApp
from tl_tui.widgets.domain_screen import DomainScreen


def world(*, controller: bool = True) -> FakeClient:
    client = FakeClient()
    seed_domains(client)
    client.is_corr_controller = controller
    return client


def scenario(
    client: FakeClient,
    steps: Callable[[Pilot[None], TlApp, DomainScreen], Awaitable[None]],
) -> None:
    app = TlApp(client, scope=SCOPE, actor="user:kim")

    async def go(pilot: Pilot[None]) -> None:
        await pilot.press("ctrl+g")
        await pilot.pause()
        assert isinstance(app.screen, DomainScreen)
        await steps(pilot, app, app.screen)

    run_pilot(app, go)


def status(screen: DomainScreen) -> str:
    return str(screen.query_one("#dom-status", Static).render())


def numbers(screen: DomainScreen) -> list[str]:
    table = screen.query_one("#dom-table", DataTable)
    return [str(table.get_row_at(i)[0]) for i in range(table.row_count)]


def test_ctrl_g_opens_the_rfi_log_with_a_summary_and_the_first_rfi_in_full() -> None:
    async def steps(pilot: Pilot[None], app: TlApp, screen: DomainScreen) -> None:
        text = screen_text(app)
        assert "RFI log of P123" in text
        assert numbers(screen) == ["P123-RFI-0001", "P123-RFI-0002", "P123-RFI-0003"]
        assert "3 items | answered 1 | open 2 | overdue 1 | impact yes 1" in text
        assert "overdue 1d" in text and "on time" in text and "C:yes S:no" in text
        assert "answer (2026-10-12): Re-route above the beam." in text
        await pilot.press("down")
        await pilot.pause()
        assert "question: Please confirm: Cable tray height" in screen_text(app)
        await pilot.press("escape")
        await pilot.pause()
        assert not isinstance(app.screen, DomainScreen)

    scenario(world(), steps)


def test_the_filters_narrow_the_log_and_say_so() -> None:
    async def steps(pilot: Pilot[None], app: TlApp, screen: DomainScreen) -> None:
        await pilot.press("o")
        await pilot.pause()
        assert numbers(screen) == ["P123-RFI-0002", "P123-RFI-0003"]  # the answered one is out
        assert "filter: open" in status(screen)
        await pilot.press("v")
        await pilot.pause()
        assert numbers(screen) == ["P123-RFI-0002"]
        assert "filter: open, overdue" in status(screen)
        await pilot.press("o", "v", "i")
        await pilot.pause()
        assert numbers(screen) == ["P123-RFI-0001"]  # the answerer said yes to a cost
        assert status(screen).endswith("filter: impact")
        await pilot.press("i")
        await pilot.pause()
        assert len(numbers(screen)) == 3 and "filter" not in status(screen)

    scenario(world(), steps)


def test_view_two_lists_the_notices_with_the_late_bar_and_the_totals_line() -> None:
    async def steps(pilot: Pilot[None], app: TlApp, screen: DomainScreen) -> None:
        await pilot.press("2")
        await pilot.pause()
        text = screen_text(app)
        assert "Commercial register of P123" in text
        assert numbers(screen) == ["P123-EW-0001", "P123-CN-0001"]
        assert "LATE" in text and "2 notices | time bars running 0, late 1" in text
        assert "escalated from P123-RFI-0001" in text
        await pilot.press("v")
        await pilot.pause()
        assert "filter: time bars" in status(screen)
        await pilot.press("i")  # impact is for the RFI log only
        await pilot.pause()
        assert not screen.impact

    scenario(world(), steps)


def test_a_person_below_a_controller_gets_an_empty_register_and_is_told_why() -> None:
    async def steps(pilot: Pilot[None], app: TlApp, screen: DomainScreen) -> None:
        await pilot.press("2")
        await pilot.pause()
        assert numbers(screen) == []
        assert "for document controllers and admins" in status(screen)
        assert "Nothing here." in screen_text(app)

    scenario(world(controller=False), steps)


def test_e_opens_the_evidence_trail_of_the_highlighted_item_as_of_today() -> None:
    client = world()

    async def steps(pilot: Pilot[None], app: TlApp, screen: DomainScreen) -> None:
        await pilot.press("2", "e")
        await pilot.pause()
        text = screen_text(app)
        assert screen.mode == "evidence" and screen.number == "P123-EW-0001"
        assert "Evidence for P123-EW-0001 as of 2026-10-20 (Tuesday)" in text
        assert numbers(screen) == ["P123-EW-0001", "  P123-RFI-0001"]
        assert "2 records in the trail" in text
        await pilot.press("down")
        await pilot.pause()
        assert "reached by derived from (active) since 2026-10-12" in screen_text(app)
        assert "cost_impact: yes" in screen_text(app)
        assert client.trail_requests == [("P123-EW-0001", screen.today)]

    scenario(client, steps)


def test_the_day_keys_step_the_trail_back_and_never_past_today() -> None:
    client = world()

    async def steps(pilot: Pilot[None], app: TlApp, screen: DomainScreen) -> None:
        await pilot.press("2", "e", "left_square_bracket", "left_square_bracket")
        await pilot.pause()
        earlier = screen.today - timedelta(days=2)
        assert screen.as_of == earlier
        assert client.trail_requests[-1] == ("P123-EW-0001", earlier)
        await pilot.press("right_square_bracket", "right_square_bracket", "right_square_bracket")
        await pilot.pause()
        assert screen.as_of == screen.today  # never later than today
        await pilot.press("left_square_bracket", "0")
        await pilot.pause()
        assert screen.as_of == screen.today
        assert client.trail_requests[-1] == ("P123-EW-0001", screen.today)

    scenario(client, steps)


def test_an_item_the_trail_cannot_show_says_so_and_keeps_the_screen() -> None:
    async def steps(pilot: Pilot[None], app: TlApp, screen: DomainScreen) -> None:
        await pilot.press("down", "e")  # P123-RFI-0002 has no trail in the fake
        await pilot.pause()
        assert status(screen).startswith("! no item 'P123-RFI-0002'")
        assert isinstance(app.screen, DomainScreen)

    scenario(world(), steps)


def test_view_three_without_an_item_asks_for_one_and_tab_goes_round() -> None:
    async def steps(pilot: Pilot[None], app: TlApp, screen: DomainScreen) -> None:
        assert numbers(screen) == [] and "0 items" in status(screen)  # nothing is listed
        await pilot.press("e")
        await pilot.pause()
        assert "Highlight an RFI or a notice in view 1 or 2 first." in status(screen)
        assert screen.mode == "rfi"
        await pilot.press("3")
        await pilot.pause()
        assert "Highlight an RFI or a notice and press e." in status(screen)
        assert "Evidence for - as of" in screen_text(app)
        await pilot.press("tab")
        await pilot.pause()
        assert screen.mode == "rfi"  # evidence, then round to the log
        await pilot.press("tab", "tab")
        await pilot.pause()
        assert screen.mode == "evidence"

    scenario(FakeClient(), steps)
