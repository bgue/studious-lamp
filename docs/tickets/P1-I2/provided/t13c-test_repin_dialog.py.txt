"""The re-pin dialog on the fake client, driven with a pilot (P1-I2-T13c)."""

from __future__ import annotations

from collections.abc import Awaitable, Callable

from fakes import SCOPE, FakeClient
from helpers import run_pilot, screen_text
from textual.pilot import Pilot
from textual.widgets import Static
from tl_mod_documents.errors import InvalidPinError
from tl_mod_documents.resolver import RepinDocumentLink
from tl_mod_documents.views import DocumentLinkView
from tl_tui.app import TlApp
from tl_tui.widgets.repin_dialog import RepinScreen


def world() -> FakeClient:
    client = FakeClient()
    client.seed_documents("P123")
    return client


def scenario(
    client: FakeClient,
    link: DocumentLinkView,
    steps: Callable[[Pilot[None], TlApp, RepinScreen, list[bool | None]], Awaitable[None]],
    *,
    number: str = "ISO-1234",
) -> None:
    app = TlApp(client, scope=SCOPE, actor="user:kim")
    results: list[bool | None] = []

    async def go(pilot: Pilot[None]) -> None:
        screen = RepinScreen(client, "P123", number, link, "user:kim")
        app.push_screen(screen, results.append)
        await pilot.pause()
        assert isinstance(app.screen, RepinScreen)
        await steps(pilot, app, screen, results)

    run_pilot(app, go)


def stale_link(client: FakeClient) -> DocumentLinkView:
    return client.get_document("P123", "ISO-1234").links[0]


def body(screen: RepinScreen) -> str:
    return str(screen.query_one("#repin-body", Static).render())


def status(screen: RepinScreen) -> str:
    return str(screen.query_one("#repin-status", Static).render())


def test_the_dialog_shows_what_changed_before_anything_is_moved() -> None:
    client = world()

    async def steps(
        pilot: Pilot[None], app: TlApp, screen: RepinScreen, results: list[bool | None]
    ) -> None:
        text = screen_text(app)
        assert "Re-pin 47-FV-1001 to ISO-1234" in text
        assert "from A (IFR) to B (IFC)" in text
        assert "What changed:" in text and "status IFR to IFC" in text
        assert "pdf changed: sheet-A.pdf" in text
        assert screen.target == "B" and client.document_commands == []
        assert results == []  # still open

    scenario(client, stale_link(client), steps)


def test_enter_moves_the_link_to_the_current_revision_and_closes() -> None:
    client = world()

    async def steps(
        pilot: Pilot[None], app: TlApp, screen: RepinScreen, results: list[bool | None]
    ) -> None:
        await pilot.press("enter")
        await pilot.pause()
        (cmd,) = client.document_commands
        assert isinstance(cmd, RepinDocumentLink)
        assert (cmd.link_id, cmd.pin, cmd.source, cmd.actor) == (
            "LINK-STALE",
            "B",
            "tui",
            "user:kim",
        )
        assert cmd.scope == "project:P123"
        assert results == [True] and not isinstance(app.screen, RepinScreen)
        assert client.get_document("P123", "ISO-1234").links[0].link_status == "active"

    scenario(client, stale_link(client), steps)


def test_y_confirms_too() -> None:
    client = world()

    async def steps(
        pilot: Pilot[None], app: TlApp, screen: RepinScreen, results: list[bool | None]
    ) -> None:
        await pilot.press("y")
        await pilot.pause()
        assert results == [True] and len(client.document_commands) == 1

    scenario(client, stale_link(client), steps)


def leaves_the_link_alone(key: str) -> None:
    client = world()

    async def steps(
        pilot: Pilot[None], app: TlApp, screen: RepinScreen, results: list[bool | None]
    ) -> None:
        await pilot.press(key)
        await pilot.pause()
        assert results == [False] and client.document_commands == []
        assert not isinstance(app.screen, RepinScreen)
        assert client.get_document("P123", "ISO-1234").links[0].link_status == "stale"

    scenario(client, stale_link(client), steps)


def test_escape_leaves_the_link_alone() -> None:
    leaves_the_link_alone("escape")


def test_n_leaves_the_link_alone() -> None:
    leaves_the_link_alone("n")


def test_a_refusal_is_shown_and_the_dialog_stays_open() -> None:
    client = world()

    def refuse(cmd: RepinDocumentLink) -> object:
        raise InvalidPinError("'B' is not an issued revision of ISO-1234")

    client.repin_document_link = refuse  # type: ignore[method-assign,assignment]

    async def steps(
        pilot: Pilot[None], app: TlApp, screen: RepinScreen, results: list[bool | None]
    ) -> None:
        await pilot.press("enter")
        await pilot.pause()
        assert status(screen) == "'B' is not an issued revision of ISO-1234"
        assert results == [] and isinstance(app.screen, RepinScreen)

    scenario(client, stale_link(client), steps)


def test_a_floating_link_has_nothing_to_move_and_enter_says_so() -> None:
    client = world()
    floating = client.get_document("P123", "ISO-1234").links[1]

    async def steps(
        pilot: Pilot[None], app: TlApp, screen: RepinScreen, results: list[bool | None]
    ) -> None:
        assert body(screen) == "This link floats; nothing to re-pin."
        await pilot.press("enter")
        await pilot.pause()
        assert status(screen) == "Nothing to re-pin."
        assert client.document_commands == [] and results == []

    scenario(client, floating, steps)


def test_a_link_that_already_points_to_the_current_revision_is_left_alone() -> None:
    client = world()
    current = stale_link(client).model_copy(update={"pin": "B", "pin_state": "current"})

    async def steps(
        pilot: Pilot[None], app: TlApp, screen: RepinScreen, results: list[bool | None]
    ) -> None:
        assert body(screen) == "The link already points to B."
        assert screen.target is None

    scenario(client, current, steps)


def test_a_diff_that_cannot_be_read_is_shown_and_blocks_the_move() -> None:
    client = world()
    stale = stale_link(client).model_copy(update={"pin": "Z"})  # no stored diff for Z

    async def steps(
        pilot: Pilot[None], app: TlApp, screen: RepinScreen, results: list[bool | None]
    ) -> None:
        assert screen.target is None
        await pilot.press("enter")
        await pilot.pause()
        assert client.document_commands == []

    def unreadable(project: str, number: str, from_code: str, to_code: str) -> object:
        raise InvalidPinError(f"{from_code!r} is not an issued revision of {number}")

    client.document_diff = unreadable  # type: ignore[method-assign,assignment]
    scenario(client, stale, steps)
