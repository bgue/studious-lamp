"""Enter on a package row of the schema workbench opens its record; Esc returns (P1-UX-T09d).

The workbench runs on the fake client with a pilot. A package row's id is the record id the record
screen reads, so each package version is stored with ``add_stored_record`` before Enter.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

import pytest
from fakes import SCOPE, FakeClient
from fakes_schemareg import make_package
from helpers import run_pilot, screen_text
from textual.pilot import Pilot
from textual.screen import ModalScreen
from textual.widgets import DataTable
from tl_mod_schemareg.testing import fixture_text
from tl_tui.app import TlApp
from tl_tui.client import ClientInterface
from tl_tui.details import details_for
from tl_tui.display import DisplayMode, Labels, find_technical
from tl_tui.widgets import schema_review_screen
from tl_tui.widgets.record_screen import RecordScreen
from tl_tui.widgets.schema_screen import SchemaWorkbenchScreen

PROJECT = "P123"
ENGINEERING_KEY = "co.acme.engineering@3.3.0"
ENGINEERING_ID = "PKG-co.acme.engineering-3.3.0"
ENGINEERING_TITLE = "Engineering standard"

Steps = Callable[[Pilot[Any], TlApp], Awaitable[None]]


def seeded_client(*, store: bool = True) -> FakeClient:
    """Three package versions, seeded as the workbench test seeds them. With ``store`` each one
    is also a stored record under its package id, so Enter can open it."""
    client = FakeClient()
    client.seed_schema_package(
        make_package(
            "co.acme.engineering",
            "3.2.0",
            "Published",
            content=fixture_text("co.acme.engineering"),
            worst_class="additive",
            analysed=True,
        )
    )
    client.seed_schema_package(
        make_package(
            "co.acme.engineering",
            "3.3.0",
            content=fixture_text("co.acme.engineering"),
            diff="--- co.acme.engineering@3.2.0\n+++ co.acme.engineering@3.3.0\n+  seat_leak\n",
            classification=None,
            title=ENGINEERING_TITLE,
            submitted_by="user:kim",
            approved_by="user:boss",
            changelog="Adds seat leak",
        )
    )
    client.seed_schema_package(
        make_package(
            "x.P123",
            "1.4.0",
            kind="extension",
            scope="project:P123",
            project="P123",
            content=fixture_text("x.P123"),
        )
    )
    if store:
        for detail in list(client._schema_packages.values()):  # noqa: SLF001
            client.add_stored_record(
                detail.id, detail.key, "schemareg.SchemaPackage", detail.title or detail.package
            )
    return client


def scenario(client: FakeClient, steps: Steps) -> None:
    app = TlApp(client, scope=SCOPE, actor="user:boss", is_admin=False)

    async def go(pilot: Pilot[Any]) -> None:
        await pilot.press("ctrl+o")
        await pilot.pause()
        assert isinstance(app.screen, SchemaWorkbenchScreen)
        await steps(pilot, app)

    run_pilot(app, go)


def table(app: TlApp) -> DataTable[str]:
    screen = app.screen
    assert isinstance(screen, SchemaWorkbenchScreen)
    return screen.query_one("#schema-table", DataTable)


def test_enter_on_a_package_row_opens_the_record_and_escape_returns_to_the_same_row() -> None:
    async def steps(pilot: Pilot[Any], app: TlApp) -> None:
        await pilot.press("down")  # the second row: co.acme.engineering 3.3.0
        await pilot.pause()
        assert table(app).cursor_row == 1
        await pilot.press("enter")
        await pilot.pause()
        assert isinstance(app.screen, RecordScreen)
        text = screen_text(app)
        assert ENGINEERING_TITLE in text
        assert ENGINEERING_ID not in text
        await pilot.press("escape")
        await pilot.pause()
        assert isinstance(app.screen, SchemaWorkbenchScreen)
        assert table(app).cursor_row == 1

    scenario(seeded_client(), steps)


def test_a_package_the_viewer_cannot_read_opens_as_no_record() -> None:
    client = seeded_client(store=False)
    client.add_stored_record(
        ENGINEERING_ID, ENGINEERING_KEY, "schemareg.SchemaPackage", ENGINEERING_TITLE
    )

    async def steps(pilot: Pilot[Any], app: TlApp) -> None:
        await pilot.press("enter")  # row 0 is x.P123 1.4.0, which has no stored record
        await pilot.pause()
        assert isinstance(app.screen, RecordScreen)
        text = screen_text(app)
        assert "No record" in text
        assert "PKG-x.P123-1.4.0" not in text and "x.P123@1.4.0" not in text
        await pilot.press("escape")
        await pilot.pause()
        assert isinstance(app.screen, SchemaWorkbenchScreen)

    scenario(client, steps)


def test_package_details_plain_have_no_key_or_hash_and_technical_adds_them() -> None:
    client = seeded_client()
    stored = client.get_record(SCOPE, ENGINEERING_KEY)
    assert stored is not None
    labels = Labels()

    plain_rows = details_for(client, PROJECT, stored, labels, DisplayMode())
    plain = "\n".join(f"{row.label}  {row.value}" for row in plain_rows)
    assert "Engineering, version 3.3.0" in plain
    assert ENGINEERING_TITLE in plain
    assert "Submitted by" in plain and "Approved by" in plain
    assert "Changelog  Adds seat leak" in plain
    assert find_technical(plain) == []
    labels_shown = [row.label for row in plain_rows]
    assert "Key" not in labels_shown and "Content hash" not in labels_shown

    technical_mode = DisplayMode()
    technical_mode.technical = True
    technical_rows = details_for(client, PROJECT, stored, labels, technical_mode)
    technical = "\n".join(f"{row.label}  {row.value}" for row in technical_rows)
    assert f"Key  {ENGINEERING_KEY}" in technical
    assert f"Content hash  {'a' * 64}" in technical
    assert ENGINEERING_KEY in find_technical(technical)


def test_enter_does_not_steal_the_review_key(monkeypatch: pytest.MonkeyPatch) -> None:
    opened: list[tuple[str, str, str]] = []

    class Review(ModalScreen[None]):
        def __init__(self, client: ClientInterface, scope: str, actor: str, ref: str) -> None:
            super().__init__()
            opened.append((scope, actor, ref))

    monkeypatch.setattr(schema_review_screen, "SchemaReviewScreen", Review)

    async def steps(pilot: Pilot[Any], app: TlApp) -> None:
        await pilot.press("enter")  # row 0 opens its record
        await pilot.pause()
        assert isinstance(app.screen, RecordScreen)
        await pilot.press("escape")
        await pilot.pause()
        assert isinstance(app.screen, SchemaWorkbenchScreen)
        await pilot.press("down", "v")  # 3.3.0 is the second row
        await pilot.pause()
        assert isinstance(app.screen, Review)
        assert opened == [(SCOPE, "user:boss", ENGINEERING_ID)]

    scenario(seeded_client(), steps)
