"""The publish preview with a pilot (P1-I3-T07c). Provided; do not edit."""

from __future__ import annotations

from collections.abc import Awaitable, Callable

from fakes import SCOPE, FakeClient
from helpers import run_pilot, screen_text
from textual.pilot import Pilot
from textual.widgets import DataTable, Static
from tl_tui.app import TlApp
from tl_tui.widgets.derived_documents import DerivedDocumentsScreen
from tl_tui.widgets.publish_preview import PublishPreviewScreen

GOOD = "ISD-001@A/instrument-index"
BAD = "ISD-002@A/instrument-index"


def world() -> FakeClient:
    client = FakeClient()
    client.seed_derivation("P123")
    return client


def scenario(
    client: FakeClient,
    steps: Callable[[Pilot[None], TlApp, PublishPreviewScreen], Awaitable[None]],
    *,
    admin: bool = True,
    controller: bool = False,
    down: int = 0,
) -> None:
    app = TlApp(client, scope=SCOPE, actor="user:kim", is_admin=admin, is_controller=controller)

    async def go(pilot: Pilot[None]) -> None:
        await pilot.press("f11")
        await pilot.pause()
        assert isinstance(app.screen, DerivedDocumentsScreen)
        await pilot.press(*["down"] * down, "p")
        await pilot.pause()
        assert isinstance(app.screen, PublishPreviewScreen)
        await steps(pilot, app, app.screen)

    run_pilot(app, go)


def status(screen: PublishPreviewScreen) -> str:
    return str(screen.query_one("#pp-status", Static).render())


def test_the_preview_shows_the_counts_the_rows_and_what_it_asks() -> None:
    async def steps(pilot: Pilot[None], app: TlApp, screen: PublishPreviewScreen) -> None:
        text = screen_text(app)
        assert f"Publish {GOOD}" in text
        assert f"{GOOD} pass 2 to tags (instrument-index@1.0.0)" in text
        assert "create 2  exists 1  differs 0  invalid 0" in text
        assert "rows exist already: publishing needs 'skip existing'" in text
        assert screen.query_one("#pp-table", DataTable).row_count == 3
        assert "47-FV-1001" in text and "exists" in text
        assert "press s to skip them" in text

    scenario(world(), steps)


def test_s_says_to_skip_the_rows_that_exist_and_p_then_asks_twice() -> None:
    client = world()

    async def steps(pilot: Pilot[None], app: TlApp, screen: PublishPreviewScreen) -> None:
        await pilot.press("p")  # not while rows exist and are not skipped
        await pilot.pause()
        assert status(screen).startswith("! ") and client.calls.count("publish_derived_tags") == 0
        await pilot.press("s")
        await pilot.pause()
        assert screen.skip_existing and "Press p twice to create 2 tags" in screen_text(app)
        await pilot.press("p")
        await pilot.pause()
        assert "Press p again to confirm" in status(screen)
        assert client.calls.count("publish_derived_tags") == 0  # the first press only asks
        await pilot.press("p")
        await pilot.pause()
        assert client.calls.count("publish_derived_tags") == 1
        command = client.derivation_commands[-1]
        assert command.skip_existing is True and command.expected_content_rev == 2  # type: ignore[attr-defined]
        assert command.actor == "user:kim" and command.source == "tui"  # type: ignore[attr-defined]
        assert "Published 2 tags." in status(screen)
        assert client.get_derived_document("P123", GOOD).state == "Published"

    scenario(client, steps)


def test_escape_after_the_first_p_leaves_without_publishing_and_closes_on_the_next() -> None:
    client = world()

    async def steps(pilot: Pilot[None], app: TlApp, screen: PublishPreviewScreen) -> None:
        await pilot.press("s", "p")
        await pilot.pause()
        await pilot.press("escape")
        await pilot.pause()
        assert status(screen) == "Not confirmed." and isinstance(app.screen, PublishPreviewScreen)
        assert client.calls.count("publish_derived_tags") == 0
        await pilot.press("escape")
        await pilot.pause()
        assert isinstance(app.screen, DerivedDocumentsScreen)

    scenario(client, steps)


def test_someone_without_the_admin_role_is_not_offered_tags() -> None:
    client = world()

    async def steps(pilot: Pilot[None], app: TlApp, screen: PublishPreviewScreen) -> None:
        await pilot.press("s")
        await pilot.pause()
        assert "needs the admin role: not offered to you" in screen_text(app)
        await pilot.press("p")
        await pilot.pause()
        assert status(screen) == "! Publishing into tags needs the admin role."
        assert client.calls.count("publish_derived_tags") == 0

    scenario(client, steps, admin=False, controller=True)  # a controller is not an admin


def test_a_derived_document_that_cannot_be_published_says_so() -> None:
    client = world()

    async def steps(pilot: Pilot[None], app: TlApp, screen: PublishPreviewScreen) -> None:
        assert screen.plan is None
        assert "! " in status(screen) and "nothing to publish" in status(screen)
        await pilot.press("p")
        await pilot.pause()
        assert "There is no plan to publish." in status(screen)
        assert client.calls.count("publish_derived_tags") == 0

    scenario(client, steps, down=1)  # ISD-002 is Invalid


def test_c_shows_the_compensation_and_u_takes_the_publication_back_after_asking() -> None:
    client = world()

    async def steps(pilot: Pilot[None], app: TlApp, screen: PublishPreviewScreen) -> None:
        await pilot.press("u")  # nothing is published yet
        await pilot.pause()
        assert "no publication that can be taken back" in status(screen)
        await pilot.press("s", "p", "p")
        await pilot.pause()
        assert client.get_derived_document("P123", GOOD).state == "Published"
        await pilot.press("c")
        await pilot.pause()
        text = screen_text(app)
        assert "delete_tag 47-FV-1001 Active  reversible" in text and "correlation COR" in text
        await pilot.press("u")
        await pilot.pause()
        assert "Press u again to confirm" in status(screen)
        assert client.calls.count("compensate_publication") == 0
        await pilot.press("u")
        await pilot.pause()
        assert client.calls.count("compensate_publication") == 1
        assert "Publication taken back." in status(screen)
        assert client.get_derived_document("P123", GOOD).state == "Valid"

    scenario(client, steps)


def test_closing_after_a_change_tells_the_list_to_read_again() -> None:
    client = world()

    async def steps(pilot: Pilot[None], app: TlApp, screen: PublishPreviewScreen) -> None:
        before = client.calls.count("list_derived_documents")
        await pilot.press("s", "p", "p")
        await pilot.pause()
        await pilot.press("escape")
        await pilot.pause()
        assert isinstance(app.screen, DerivedDocumentsScreen)
        assert client.calls.count("list_derived_documents") == before + 1
        assert [v.state for v in app.screen.shown][0] == "Published"

    scenario(client, steps)
