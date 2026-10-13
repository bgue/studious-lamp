"""The document register screen on the fake client, driven with a pilot (P1-I2-T13b)."""

from __future__ import annotations

from collections.abc import Awaitable, Callable

from fakes import SCOPE, FakeClient
from helpers import run_pilot, screen_text
from textual.pilot import Pilot
from textual.widgets import DataTable, Input, Static
from tl_tui.app import TlApp
from tl_tui.widgets.document_register import DocumentRegisterScreen


def world() -> FakeClient:
    client = FakeClient()
    client.seed_documents("P123")
    return client


def scenario(
    client: FakeClient,
    steps: Callable[[Pilot[None], TlApp, DocumentRegisterScreen], Awaitable[None]],
) -> None:
    app = TlApp(client, scope=SCOPE, actor="user:kim")

    async def go(pilot: Pilot[None]) -> None:
        await pilot.press("f7")
        await pilot.pause()
        assert isinstance(app.screen, DocumentRegisterScreen)
        await steps(pilot, app, app.screen)

    run_pilot(app, go)


def numbers(screen: DocumentRegisterScreen) -> list[str]:
    return [v.number for v in screen.shown]


def status(screen: DocumentRegisterScreen) -> str:
    return str(screen.query_one("#docs-status", Static).render())


def test_f7_lists_the_documents_by_number_and_describes_the_first() -> None:
    async def steps(pilot: Pilot[None], app: TlApp, screen: DocumentRegisterScreen) -> None:
        text = screen_text(app)
        assert "Documents of P123" in text
        assert numbers(screen) == ["ISO-1234", "ISO-2000"]  # the void one is left out
        assert screen.query_one("#docs-table", DataTable).row_count == 2
        assert "B(IFC)" in text and "Registered" in text
        assert "revisions:" in text and "B  Issued  IFC construction 2026-10-10  current" in text
        assert "links (1 stale):" in text and "! 47-FV-1001" in text
        assert "2 of 2 documents" in text
        await pilot.press("escape")
        await pilot.pause()
        assert not isinstance(app.screen, DocumentRegisterScreen)

    scenario(world(), steps)


def test_moving_the_cursor_describes_the_document_it_lands_on() -> None:
    async def steps(pilot: Pilot[None], app: TlApp, screen: DocumentRegisterScreen) -> None:
        await pilot.press("down")
        await pilot.pause()
        assert screen.detail is not None and screen.detail.number == "ISO-2000"
        assert "no revisions yet" in screen_text(app)

    scenario(world(), steps)


def test_a_includes_the_void_documents_and_reads_again() -> None:
    client = world()

    async def steps(pilot: Pilot[None], app: TlApp, screen: DocumentRegisterScreen) -> None:
        before = client.calls.count("list_documents")
        await pilot.press("a")
        await pilot.pause()
        assert numbers(screen) == ["ISO-1234", "ISO-2000", "ISO-3000"]
        assert "incl. void" in status(screen)
        assert client.calls.count("list_documents") == before + 1
        await pilot.press("a")
        await pilot.pause()
        assert numbers(screen) == ["ISO-1234", "ISO-2000"]

    scenario(client, steps)


def test_s_and_y_narrow_the_list_by_state_and_type() -> None:
    async def steps(pilot: Pilot[None], app: TlApp, screen: DocumentRegisterScreen) -> None:
        await pilot.press("s")
        await pilot.pause()
        assert screen.state == "Issued" and numbers(screen) == ["ISO-1234"]
        assert "state Issued" in status(screen)
        await pilot.press("s", "s")
        await pilot.pause()
        assert screen.state is None and len(numbers(screen)) == 2
        await pilot.press("y")
        await pilot.pause()
        assert screen.doc_type == "DAT" and numbers(screen) == ["ISO-2000"]
        await pilot.press("y", "y")
        await pilot.pause()
        assert screen.doc_type is None

    scenario(world(), steps)


def test_the_filter_box_narrows_by_number_or_title_and_escape_clears_it() -> None:
    async def steps(pilot: Pilot[None], app: TlApp, screen: DocumentRegisterScreen) -> None:
        await pilot.press("slash")
        await pilot.press(*"pump")
        await pilot.pause()
        assert numbers(screen) == ["ISO-2000"] and 'filter "pump"' in status(screen)
        await pilot.press("escape")
        await pilot.pause()
        assert screen.query_one("#docs-filter", Input).value == ""
        assert len(numbers(screen)) == 2
        assert isinstance(app.screen, DocumentRegisterScreen)  # the first Escape only cleared it

    scenario(world(), steps)


def test_a_failed_read_is_shown_and_the_screen_stays() -> None:
    client = world()

    async def steps(pilot: Pilot[None], app: TlApp, screen: DocumentRegisterScreen) -> None:
        from tl_mod_documents.errors import DocumentNotFoundError

        def gone(project: str, number: str) -> object:
            raise DocumentNotFoundError(f"no document {number!r}")

        client.get_document = gone  # type: ignore[method-assign,assignment]
        await pilot.press("f5")
        await pilot.pause()
        assert "! no document 'ISO-1234'" in status(screen)
        assert numbers(screen) == ["ISO-1234", "ISO-2000"]  # the listing is still there

    scenario(client, steps)


def test_r_says_so_when_the_highlighted_document_has_no_stale_link() -> None:
    async def steps(pilot: Pilot[None], app: TlApp, screen: DocumentRegisterScreen) -> None:
        await pilot.press("down", "r")
        await pilot.pause()
        assert "ISO-2000 has no stale link to re-pin." in status(screen)
        assert isinstance(app.screen, DocumentRegisterScreen)

    scenario(world(), steps)
