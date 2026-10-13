"""The transmittal composer on the fake client, driven with a pilot (P1-I2-T13d)."""

from __future__ import annotations

from collections.abc import Awaitable, Callable

from fakes import SCOPE, FakeClient
from helpers import run_pilot, screen_text
from textual.pilot import Pilot
from textual.widgets import Input, SelectionList, Static
from tl_mod_documents.handlers.transmittals import CreateTransmittal
from tl_tui.app import TlApp
from tl_tui.widgets.transmittal_composer import TransmittalComposerScreen

Steps = Callable[[Pilot[None], TlApp, TransmittalComposerScreen, list[str | None]], Awaitable[None]]


def world() -> FakeClient:
    client = FakeClient()
    client.seed_documents("P123")
    return client


def scenario(client: FakeClient, steps: Steps, *, document: str | None = "ISO-1234") -> None:
    app = TlApp(client, scope=SCOPE, actor="user:kim")
    results: list[str | None] = []

    async def go(pilot: Pilot[None]) -> None:
        app.push_screen(
            TransmittalComposerScreen(client, "P123", "user:kim", document=document),
            results.append,
        )
        await pilot.pause()
        assert isinstance(app.screen, TransmittalComposerScreen)
        await steps(pilot, app, app.screen, results)

    run_pilot(app, go)


def status(screen: TransmittalComposerScreen) -> str:
    return str(screen.query_one("#tc-status", Static).render())


def fill(screen: TransmittalComposerScreen, **fields: str) -> None:
    for name, value in fields.items():
        screen.query_one(f"#tc-{name}", Input).value = value


def ticked(screen: TransmittalComposerScreen) -> list[str]:
    return list(screen.query_one("#tc-revisions", SelectionList).selected)


def test_the_composer_offers_the_issued_revisions_and_ticks_the_current_one() -> None:
    async def steps(
        pilot: Pilot[None], app: TlApp, screen: TransmittalComposerScreen, results: list[str | None]
    ) -> None:
        text = screen_text(app)
        assert "New transmittal in P123" in text
        assert "ISO-1234@B IFC" in text and "ISO-1234@A IFR" in text
        assert "ISO-2000" not in text  # a document with no issued revision offers nothing
        assert screen.choices == [
            ("ISO-1234@B IFC", "REV-ISO-1234-B"),
            ("ISO-1234@A IFR", "REV-ISO-1234-A"),
        ]
        assert ticked(screen) == ["REV-ISO-1234-B"]

    scenario(world(), steps)


def test_nothing_is_ticked_without_a_document() -> None:
    async def steps(
        pilot: Pilot[None], app: TlApp, screen: TransmittalComposerScreen, results: list[str | None]
    ) -> None:
        assert ticked(screen) == [] and len(screen.choices) == 2

    scenario(world(), steps, document=None)


def test_ctrl_s_drafts_the_transmittal_and_closes_with_its_number() -> None:
    client = world()

    async def steps(
        pilot: Pilot[None], app: TlApp, screen: TransmittalComposerScreen, results: list[str | None]
    ) -> None:
        fill(
            screen,
            subject="Isometrics for site",
            to="Site:Acme:site@acme.test; Ana",
            due="2026-12-01",
        )
        await pilot.press("ctrl+s")
        await pilot.pause()
        (cmd,) = client.document_commands
        assert isinstance(cmd, CreateTransmittal)
        assert (cmd.subject, cmd.purpose, cmd.due_date) == (
            "Isometrics for site",
            "for_construction",
            "2026-12-01",
        )
        assert [(r.name, r.organisation, r.email) for r in cmd.recipients] == [
            ("Site", "Acme", "site@acme.test"),
            ("Ana", None, None),
        ]
        assert cmd.revision_ids == ["REV-ISO-1234-B"]
        assert (cmd.actor, cmd.source, cmd.scope) == ("user:kim", "tui", "project:P123")
        assert results == ["P123-TRN-0001"] and not isinstance(
            app.screen, TransmittalComposerScreen
        )
        sent = client.get_transmittal("P123", "P123-TRN-0001")
        assert (sent.state, sent.title) == ("Draft", "Isometrics for site")

    scenario(client, steps)


def test_a_space_ticks_more_revisions() -> None:
    client = world()

    async def steps(
        pilot: Pilot[None], app: TlApp, screen: TransmittalComposerScreen, results: list[str | None]
    ) -> None:
        await pilot.press("down", "down", "space")  # the second option, A
        await pilot.pause()
        assert sorted(ticked(screen)) == ["REV-ISO-1234-A", "REV-ISO-1234-B"]
        fill(screen, subject="Both", to="Site")
        await pilot.press("ctrl+s")
        await pilot.pause()
        (cmd,) = client.document_commands
        assert isinstance(cmd, CreateTransmittal)
        assert sorted(cmd.revision_ids) == ["REV-ISO-1234-A", "REV-ISO-1234-B"]

    scenario(client, steps)


def test_a_missing_field_is_shown_and_the_composer_stays_open() -> None:
    client = world()

    async def steps(
        pilot: Pilot[None], app: TlApp, screen: TransmittalComposerScreen, results: list[str | None]
    ) -> None:
        await pilot.press("ctrl+s")  # no subject and no recipient
        await pilot.pause()
        assert "subject" in status(screen) and client.document_commands == []
        fill(screen, subject="s", to="Site", purpose="for_fun")
        await pilot.press("ctrl+s")
        await pilot.pause()
        assert "purpose" in status(screen)
        fill(screen, purpose="for_review", due="soon")
        await pilot.press("ctrl+s")
        await pilot.pause()
        assert "due_date" in status(screen)
        assert results == [] and isinstance(app.screen, TransmittalComposerScreen)

    scenario(client, steps)


def test_unticking_everything_is_refused_by_the_model() -> None:
    client = world()

    async def steps(
        pilot: Pilot[None], app: TlApp, screen: TransmittalComposerScreen, results: list[str | None]
    ) -> None:
        screen.query_one("#tc-revisions", SelectionList).deselect_all()
        fill(screen, subject="s", to="Site")
        await pilot.press("ctrl+s")
        await pilot.pause()
        assert "revision_ids" in status(screen) and client.document_commands == []

    scenario(client, steps)


def test_escape_cancels() -> None:
    client = world()

    async def steps(
        pilot: Pilot[None], app: TlApp, screen: TransmittalComposerScreen, results: list[str | None]
    ) -> None:
        await pilot.press("escape")
        await pilot.pause()
        assert results == [None] and client.document_commands == []
        assert not isinstance(app.screen, TransmittalComposerScreen)

    scenario(client, steps)
