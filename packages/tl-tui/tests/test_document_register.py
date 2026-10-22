"""The document register screen on the fake client, driven with a pilot (P1-I2-T13b)."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from pathlib import Path

import pytest
from doc_support import pdf_bytes, settle
from fakes import SCOPE, FakeClient
from helpers import run_pilot, screen_text
from textual.pilot import Pilot
from textual.widgets import DataTable, Input, Static
from tl_tui.app import TlApp
from tl_tui.widgets import file_panel
from tl_tui.widgets.action_form import ActionFormScreen
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
        await settle(pilot)
        assert isinstance(app.screen, DocumentRegisterScreen)
        await steps(pilot, app, app.screen)

    run_pilot(app, go)


def numbers(screen: DocumentRegisterScreen) -> list[str]:
    return [v.number for v in screen.shown]


def status(screen: DocumentRegisterScreen) -> str:
    return str(screen.query_one("#log-status", Static).render())


def test_f7_lists_the_documents_by_number_and_describes_the_first() -> None:
    async def steps(pilot: Pilot[None], app: TlApp, screen: DocumentRegisterScreen) -> None:
        text = screen_text(app)
        assert "P123 › Documents › ISO-1234: Isometric, line 47-P-101" in text  # the breadcrumb
        assert numbers(screen) == ["ISO-1234", "ISO-2000"]  # the void one is left out
        assert screen.query_one("#log-table", DataTable).row_count == 2
        assert "B(IFC)" in text and "Registered" in text
        assert "revisions:" in text and "B  Issued  IFC construction 2026-10-10  current" in text
        assert "links (1 stale):" in text and "! 47-FV-1001" in text
        assert "2 of 2 documents" in text
        await pilot.press("escape")
        await settle(pilot)
        assert not isinstance(app.screen, DocumentRegisterScreen)

    scenario(world(), steps)


def test_moving_the_cursor_describes_the_document_it_lands_on() -> None:
    async def steps(pilot: Pilot[None], app: TlApp, screen: DocumentRegisterScreen) -> None:
        await pilot.press("down")
        await settle(pilot)
        assert screen.detail is not None and screen.detail.number == "ISO-2000"
        assert "no revisions yet" in screen_text(app)

    scenario(world(), steps)


def test_a_includes_the_void_documents_and_reads_again() -> None:
    client = world()

    async def steps(pilot: Pilot[None], app: TlApp, screen: DocumentRegisterScreen) -> None:
        before = client.calls.count("list_documents")
        await pilot.press("a")
        await settle(pilot)
        assert numbers(screen) == ["ISO-1234", "ISO-2000", "ISO-3000"]
        assert "incl. void" in status(screen)
        assert client.calls.count("list_documents") == before + 1
        await pilot.press("a")
        await settle(pilot)
        assert numbers(screen) == ["ISO-1234", "ISO-2000"]

    scenario(client, steps)


def test_s_and_y_narrow_the_list_by_state_and_type() -> None:
    async def steps(pilot: Pilot[None], app: TlApp, screen: DocumentRegisterScreen) -> None:
        await pilot.press("s")
        await settle(pilot)
        assert screen.state == "Issued" and numbers(screen) == ["ISO-1234"]
        assert "state Issued" in status(screen)
        await pilot.press("s", "s")
        await settle(pilot)
        assert screen.state is None and len(numbers(screen)) == 2
        await pilot.press("y")
        await settle(pilot)
        assert screen.doc_type == "DAT" and numbers(screen) == ["ISO-2000"]
        await pilot.press("y", "y")
        await settle(pilot)
        assert screen.doc_type is None

    scenario(world(), steps)


def test_the_filter_box_narrows_by_number_or_title_and_escape_clears_it() -> None:
    async def steps(pilot: Pilot[None], app: TlApp, screen: DocumentRegisterScreen) -> None:
        await pilot.press("slash")
        await pilot.press(*"pump")
        await settle(pilot)
        assert numbers(screen) == ["ISO-2000"] and 'filter "pump"' in status(screen)
        await pilot.press("escape")
        await settle(pilot)
        assert screen.query_one("#log-filter", Input).value == ""
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
        await settle(pilot)
        assert "! no document 'ISO-1234'" in status(screen)
        assert numbers(screen) == ["ISO-1234", "ISO-2000"]  # the listing is still there

    scenario(client, steps)


def bar(screen: DocumentRegisterScreen) -> str:
    return str(screen.query_one("#log-actions", Static).render())


def test_the_actions_bar_follows_what_the_server_offers_the_viewer() -> None:
    controller = world()
    controller.set_actions(
        "DOC-ISO-1234", ("SupersedeDocument", "Supersede"), ("VoidDocument", "Void")
    )
    controller.set_actions(
        "REV-ISO-1234-B",
        ("SupersedeRevision", "Supersede"),
        ("CreateTransmittal", "Create transmittal"),
    )
    reader = world()  # the server offers a plain reader nothing

    async def steps(pilot: Pilot[None], app: TlApp, screen: DocumentRegisterScreen) -> None:
        await settle(pilot)
        text = bar(screen)
        assert "[x] Supersede document" in text and "[d] Void document" in text
        assert "[u] Supersede revision" in text and "[t] Create transmittal" in text
        assert "[r] Re-pin" in text  # ISO-1234 has a stale link
        assert "[Enter] Open record" in text

    scenario(controller, steps)

    async def reader_steps(pilot: Pilot[None], app: TlApp, screen: DocumentRegisterScreen) -> None:
        await settle(pilot)
        text = bar(screen)
        assert "Void" not in text and "Supersede" not in text and "[t]" not in text
        assert "[Enter] Open record" in text

    scenario(reader, reader_steps)


def test_a_draft_revision_is_offered_issue_and_the_form_sends_the_command() -> None:
    client = world()
    docs = client.get_document("P123", "ISO-1234")
    draft = docs.revisions[1].model_copy(
        update={"id": "REV-ISO-1234-C", "code": "C", "state": "Draft", "issue_status": None,
                "is_current": False, "renditions": []}
    )  # fmt: skip
    client._documents["P123"]["ISO-1234"] = docs.model_copy(
        update={"revisions": [*docs.revisions, draft]}
    )
    client.set_actions("REV-ISO-1234-C", ("IssueRevision", "Issue"))

    async def steps(pilot: Pilot[None], app: TlApp, screen: DocumentRegisterScreen) -> None:
        await settle(pilot)
        assert "[i] Issue" in bar(screen)
        await pilot.press("i")
        await settle(pilot)
        assert isinstance(app.screen, ActionFormScreen)
        await pilot.press(*"IFC")
        await pilot.press("enter")
        await settle(pilot)
        assert app.screen is screen
        sent = [c for _, name, c in client.module_commands if name == "IssueRevision"]
        assert len(sent) == 1 and sent[0].stream_id == "REV-ISO-1234-C"  # type: ignore[attr-defined]
        assert sent[0].issue_status == "IFC"  # type: ignore[attr-defined]

    scenario(client, steps)


def test_a_refusal_from_the_server_lands_in_the_status_line() -> None:
    client = world()
    client.is_module_controller = False  # the offer was advice; the command still checks
    client.set_actions("DOC-ISO-1234", ("VoidDocument", "Void"))

    async def steps(pilot: Pilot[None], app: TlApp, screen: DocumentRegisterScreen) -> None:
        await settle(pilot)
        await pilot.press("d")
        await settle(pilot)
        await pilot.press(*"wrong")
        await pilot.press("enter")
        await settle(pilot)
        assert "! this action needs the document_controller or admin role" in status(screen)
        assert not client.module_commands

    scenario(client, steps)


def test_r_is_not_offered_when_the_highlighted_document_has_no_stale_link() -> None:
    async def steps(pilot: Pilot[None], app: TlApp, screen: DocumentRegisterScreen) -> None:
        await pilot.press("down")
        await settle(pilot)
        assert "[r]" not in bar(screen)
        await pilot.press("r")
        await settle(pilot)
        assert isinstance(app.screen, DocumentRegisterScreen)  # nothing opened

    scenario(world(), steps)


def test_v_opens_the_current_revisions_pdf_in_the_viewer(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    client = world()
    data = pdf_bytes()
    client.add_record_file("REV-ISO-1234-B", "sheet-B.pdf", data)
    opened: list[Path] = []
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path / "cache"))
    monkeypatch.setenv("TL_IMAGES", "off")
    monkeypatch.setattr(
        file_panel, "open_in_viewer", lambda path, launcher=None: opened.append(path)
    )

    async def steps(pilot: Pilot[None], app: TlApp, screen: DocumentRegisterScreen) -> None:
        await settle(pilot)
        assert "[v] Open file" in bar(screen)
        assert "sheet-B.pdf  PDF document" in screen_text(app)
        await pilot.press("v")
        await settle(pilot)
        assert [p.name for p in opened] == ["sheet-B.pdf"]
        assert "Opened sheet-B.pdf." in status(screen)
        await pilot.press("down")  # ISO-2000 has no revision, so no file and no key
        await settle(pilot)
        assert "[v]" not in bar(screen)

    scenario(client, steps)


def test_a_hidden_document_record_offers_no_actions_and_says_so() -> None:
    client = world()
    client.hide_record("DOC-ISO-1234")

    async def steps(pilot: Pilot[None], app: TlApp, screen: DocumentRegisterScreen) -> None:
        await settle(pilot)
        assert bar(screen) == ""
        assert "! no record" in status(screen)

    scenario(client, steps)
