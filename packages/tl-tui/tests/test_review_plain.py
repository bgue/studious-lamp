"""The review queue in plain words, Enter into the record, and the technical toggle (P1-UX-T07).

Pilot tests on the fake client, built as ``test_review_queue.py`` builds its world. Plain mode
shows no value id, no enricher version and no property path; Enter on a value opens the record
the value is about; Ctrl+D (an admin) brings the technical text back and takes it away again.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

import rows_integration as rows
from fakes import SCOPE, FakeClient
from helpers import run_pilot, screen_text
from textual.pilot import Pilot
from textual.widgets import DataTable
from tl_tui.app import TlApp
from tl_tui.display import find_technical
from tl_tui.integration_text import cells, detail_lines, record_name, state_words
from tl_tui.widgets.record_screen import NO_RECORD, RecordScreen
from tl_tui.widgets.review_queue import ReviewQueueScreen


def client_with_values() -> FakeClient:
    client = FakeClient()
    client.seed_integration("enrichments", **rows.enrichment())
    client.seed_integration(
        "enrichments",
        **rows.enrichment(
            value_id="01JVALUEBBBBBBBBBB2", property_path="enrich.doc_classifier.discipline",
            target={"id": "rec-2", "key": "DOC-0002", "record_type": "document"},
        ),
    )  # fmt: skip
    client.seed_integration(
        "enrichments",
        **rows.enrichment(value_id="01JVALUECCCCCCCCCC3", acceptance_state="accepted"),
    )
    return client


def scenario(
    client: FakeClient,
    steps: Callable[[Pilot[Any], TlApp, ReviewQueueScreen], Awaitable[None]],
    *,
    is_admin: bool = False,
) -> None:
    app = TlApp(client, scope=SCOPE, actor="user:kim", is_admin=is_admin)

    async def go(pilot: Pilot[Any]) -> None:
        await pilot.press("ctrl+r")
        await pilot.pause()
        assert isinstance(app.screen, ReviewQueueScreen)
        await steps(pilot, app, app.screen)

    run_pilot(app, go)


def table(screen: ReviewQueueScreen) -> DataTable[str]:
    return screen.query_one("#review-table", DataTable)


def test_enter_on_a_value_opens_the_target_record_and_escape_returns_to_the_same_row() -> None:
    client = client_with_values()
    client.add_stored_record("rec-2", "DOC-0002", "documents.Document", "Wiring diagram")

    async def steps(pilot: Pilot[Any], app: TlApp, screen: ReviewQueueScreen) -> None:
        await pilot.press("down", "enter")  # the second value is about DOC-0002
        await pilot.pause()
        assert isinstance(app.screen, RecordScreen)
        assert "Wiring diagram" in screen_text(app)
        await pilot.press("escape")
        await pilot.pause()
        assert isinstance(app.screen, ReviewQueueScreen)
        assert table(app.screen).cursor_row == 1  # back on the same row

    scenario(client, steps)


def test_a_target_the_viewer_cannot_read_opens_as_no_record() -> None:
    client = client_with_values()  # rec-1 is never stored: the viewer cannot see it

    async def steps(pilot: Pilot[Any], app: TlApp, screen: ReviewQueueScreen) -> None:
        await pilot.press("enter")
        await pilot.pause()
        assert isinstance(app.screen, RecordScreen)
        text = screen_text(app)
        assert NO_RECORD in text
        assert "rec-1" not in text

    scenario(client, steps)


def test_plain_table_and_panel_have_no_id_version_or_property_path() -> None:
    client = client_with_values()

    async def steps(pilot: Pilot[Any], app: TlApp, screen: ReviewQueueScreen) -> None:
        text = screen_text(app)
        assert "Doc type" in text and "DOC-0001" in text and "Waiting" in text
        assert find_technical(text) == []
        assert "@" not in text and "documents." not in text and "enrich." not in text
        assert "01JVALUE" not in text  # neither the table nor the panel shows the value id

    scenario(client, steps)


def test_technical_mode_restores_the_id_the_version_and_the_path_and_back() -> None:
    client = client_with_values()

    async def steps(pilot: Pilot[Any], app: TlApp, screen: ReviewQueueScreen) -> None:
        assert "enrich.doc_classifier" not in screen_text(app)
        await pilot.press("ctrl+d")  # works under the modal; the screen redraws in place
        await pilot.pause()
        assert app.display_mode.technical is True
        assert table(screen).cursor_row == 0
        text = screen_text(app)
        assert "enrich.doc_classifier.doc_type" in text
        assert "doc_classifier@1" in text
        assert "AAAAAAA1" in text  # the short id column
        assert "Value       01JVALUEAAAAAAAAAA1" in text  # the detail panel's id line
        await pilot.press("ctrl+d")
        await pilot.pause()
        assert app.display_mode.technical is False
        text = screen_text(app)
        assert "enrich.doc_classifier" not in text and "@" not in text
        assert "Doc type" in text

    scenario(client, steps, is_admin=True)


def test_plain_cells_and_detail_lines_for_waiting_accepted_rejected_states() -> None:
    waiting = rows.enrichment()
    assert cells("enrichments", waiting, technical=False) == (
        "… Waiting", "DOC-0001", "Doc type", '"DRW"', "0.80",
    )  # fmt: skip
    accepted = rows.enrichment(acceptance_state="accepted", property_path="enrich.x.discipline")
    assert cells("enrichments", accepted, technical=False)[:3] == (
        "✓ Accepted",
        "DOC-0001",
        "Discipline",
    )
    rejected = rows.enrichment(acceptance_state="rejected", reason="wrong sheet")
    assert cells("enrichments", rejected, technical=False)[0] == "! Rejected"
    assert state_words("auto_accepted", technical=False) == "✓ Accepted automatically"
    # the technical cells are unchanged, id and state word included
    assert cells("enrichments", waiting)[:2] == ("AAAAAAA1", "… proposed")

    lines = detail_lines("enrichments", rejected, technical=False)
    assert lines[0] == f"{'State':<12}! Rejected"
    assert f"{'Enricher':<12}Doc classifier" in lines
    assert f"{'Property':<12}Doc type" in lines
    assert f"{'Reason':<12}wrong sheet" in lines
    assert not any(line.startswith("Value") for line in lines)  # the value id is not shown
    assert not any("@" in line or "enrich." in line for line in lines)

    assert record_name({"id": "r1", "key": None}, technical=False) == "(no number)"
    assert record_name(None, technical=False) == "(no number)"
    assert record_name({"id": "r1", "key": "DOC-1"}, technical=False) == "DOC-1"
