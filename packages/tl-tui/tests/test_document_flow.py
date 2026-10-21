"""The document screens together: register, re-pin dialog and transmittal composer (P1-I2).

Supervisor-owned: it needs all three screens, so it runs after their tickets have merged.
"""

from __future__ import annotations

from fakes import SCOPE, FakeClient
from helpers import run_pilot, screen_text
from textual.pilot import Pilot
from textual.widgets import Input, Static
from tl_tui.app import TlApp
from tl_tui.widgets.document_register import DocumentRegisterScreen
from tl_tui.widgets.repin_dialog import RepinScreen
from tl_tui.widgets.transmittal_composer import TransmittalComposerScreen


def test_r_opens_the_dialog_and_a_yes_clears_the_stale_mark() -> None:
    client = FakeClient()
    client.seed_documents("P123")
    app = TlApp(client, scope=SCOPE, actor="user:kim")

    async def go(pilot: Pilot[None]) -> None:
        await pilot.press("f7")
        await pilot.pause()
        register = app.screen
        assert isinstance(register, DocumentRegisterScreen)
        assert "links (1 stale):" in screen_text(app)
        await pilot.press("r")
        await pilot.pause()
        assert isinstance(app.screen, RepinScreen)
        assert "What changed:" in screen_text(app)
        await pilot.press("enter")
        await pilot.pause()
        assert app.screen is register
        text = screen_text(app)
        assert "Link re-pinned." in text and "links (1 stale)" not in text
        assert "47-FV-1001 (Record) pin B" in text
        await pilot.press("r")
        await pilot.pause()
        assert "has no stale link to re-pin" in str(
            register.query_one("#docs-status", Static).render()
        )

    run_pilot(app, go)


def test_t_opens_the_composer_and_ctrl_s_reports_the_draft_in_the_register() -> None:
    client = FakeClient()
    client.seed_documents("P123")
    app = TlApp(client, scope=SCOPE, actor="user:kim")

    async def go(pilot: Pilot[None]) -> None:
        await pilot.press("f7")
        await pilot.pause()
        register = app.screen
        await pilot.press("t")
        await pilot.pause()
        composer = app.screen
        assert isinstance(composer, TransmittalComposerScreen)
        composer.query_one("#tc-subject", Input).value = "To site"
        composer.query_one("#tc-to", Input).value = "Site"
        await pilot.press("ctrl+s")
        await pilot.pause()
        assert app.screen is register
        assert "Drafted transmittal P123-TRN-0001." in screen_text(app)

    run_pilot(app, go)


def test_f7_needs_a_project_scope() -> None:
    client = FakeClient(scope="company")
    app = TlApp(client, scope="company", actor="user:kim")

    async def go(pilot: Pilot[None]) -> None:
        await pilot.press("f7")
        await pilot.pause()
        assert not isinstance(app.screen, DocumentRegisterScreen)

    run_pilot(app, go)


def test_a_controller_drafts_and_issues_from_the_register() -> None:
    client = FakeClient()
    client.seed_documents("P123")
    app = TlApp(client, scope=SCOPE, actor="user:dora", is_controller=True)

    async def go(pilot: Pilot[None]) -> None:
        await pilot.press("f7")
        await pilot.pause()
        register = app.screen
        assert isinstance(register, DocumentRegisterScreen) and register.is_controller
        await pilot.press("t")
        await pilot.pause()
        composer = app.screen
        assert isinstance(composer, TransmittalComposerScreen) and composer.is_controller
        composer.query_one("#tc-subject", Input).value = "To site"
        composer.query_one("#tc-to", Input).value = "Site"
        await pilot.press("ctrl+t")
        await pilot.pause()
        assert app.screen is register
        assert "Drafted and issued transmittal P123-TRN-0001." in screen_text(app)

    run_pilot(app, go)


def test_a_plain_user_gets_no_issue_key_in_the_register_flow() -> None:
    client = FakeClient()
    client.seed_documents("P123")
    app = TlApp(client, scope=SCOPE, actor="user:kim")  # not a controller

    async def go(pilot: Pilot[None]) -> None:
        await pilot.press("f7")
        await pilot.pause()
        assert isinstance(app.screen, DocumentRegisterScreen) and not app.screen.is_controller
        await pilot.press("t")
        await pilot.pause()
        composer = app.screen
        assert isinstance(composer, TransmittalComposerScreen) and not composer.is_controller
        assert "Ctrl+T" not in screen_text(app)

    run_pilot(app, go)


def test_an_admin_app_is_a_controller_app() -> None:
    app = TlApp(FakeClient(), scope=SCOPE, actor="user:boss", is_admin=True)
    assert app.is_controller
    assert not TlApp(FakeClient(), scope=SCOPE, actor="user:kim").is_controller
