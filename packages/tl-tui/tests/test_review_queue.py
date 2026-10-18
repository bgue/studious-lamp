"""The review queue screen on the fake client, driven with a pilot (P1-I7-T05c). Provided; do not
edit.

The screen lists the values an enricher proposed, accepts or rejects the highlighted one through
the two commands, and shows a refusal without changing anything.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

import rows_integration as rows
from fakes import SCOPE, FakeClient
from helpers import run_pilot, screen_text
from textual.pilot import Pilot
from textual.widgets import DataTable, Input
from tl_tui.app import TlApp
from tl_tui.widgets.prompt import PromptScreen
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
    client: FakeClient, steps: Callable[[Pilot[Any], TlApp, ReviewQueueScreen], Awaitable[None]]
) -> None:
    app = TlApp(client, scope=SCOPE, actor="user:kim")

    async def go(pilot: Pilot[Any]) -> None:
        await pilot.press("ctrl+r")
        await pilot.pause()
        assert isinstance(app.screen, ReviewQueueScreen)
        await steps(pilot, app, app.screen)

    run_pilot(app, go)


def table(screen: ReviewQueueScreen) -> DataTable[str]:
    return screen.query_one("#review-table", DataTable)


def test_ctrl_r_lists_the_values_waiting_and_closes_with_escape() -> None:
    async def steps(pilot: Pilot[Any], app: TlApp, screen: ReviewQueueScreen) -> None:
        text = screen_text(app)
        assert "Values waiting for review (2)" in text
        assert table(screen).row_count == 2
        assert "DOC-0001" in text and "enrich.doc_classifier.doc_type" in text
        assert "Enricher    doc_classifier@1" in text  # the detail of the first row
        assert "Confidence  0.80" in text
        await pilot.press("escape")
        await pilot.pause()
        assert not isinstance(app.screen, ReviewQueueScreen)

    client = client_with_values()
    scenario(client, steps)


def test_s_switches_between_the_waiting_values_and_all_of_them() -> None:
    async def steps(pilot: Pilot[Any], app: TlApp, screen: ReviewQueueScreen) -> None:
        await pilot.press("s")
        await pilot.pause()
        assert table(screen).row_count == 3 and "All values (3)" in screen_text(app)
        await pilot.press("s")
        await pilot.pause()
        assert table(screen).row_count == 2

    scenario(client_with_values(), steps)


def test_an_empty_queue_says_so() -> None:
    async def steps(pilot: Pilot[Any], app: TlApp, screen: ReviewQueueScreen) -> None:
        assert "Nothing is waiting for review." in screen_text(app)
        await pilot.press("a")  # nothing to accept: no command, no crash
        await pilot.pause()

    client = FakeClient()
    scenario(client, steps)
    assert client.integration_calls == []


def test_a_accepts_the_highlighted_value_and_it_leaves_the_queue() -> None:
    client = client_with_values()

    async def steps(pilot: Pilot[Any], app: TlApp, screen: ReviewQueueScreen) -> None:
        await pilot.press("a")
        await pilot.pause()
        assert client.integration_calls == [
            ("AcceptEnrichment", SCOPE, {"value_id": "01JVALUEAAAAAAAAAA1"})
        ]
        assert table(screen).row_count == 1
        assert "Accepted enrich.doc_classifier.doc_type" in screen_text(app)
        await pilot.press("s")  # the accepted value is in the full list
        await pilot.pause()
        assert "✓ accepted" in screen_text(app)

    scenario(client, steps)


def test_x_asks_for_a_reason_and_rejects_with_it() -> None:
    client = client_with_values()

    async def steps(pilot: Pilot[Any], app: TlApp, screen: ReviewQueueScreen) -> None:
        await pilot.press("down", "x")
        await pilot.pause()
        assert isinstance(app.screen, PromptScreen)
        await pilot.press("enter")  # a reason is required: it stays open
        await pilot.pause()
        assert isinstance(app.screen, PromptScreen)
        assert client.integration_calls == []
        app.screen.query_one(Input).value = "wrong sheet"
        await pilot.press("enter")
        await pilot.pause()
        assert isinstance(app.screen, ReviewQueueScreen)
        assert client.integration_calls == [
            (
                "RejectEnrichment",
                SCOPE,
                {"value_id": "01JVALUEBBBBBBBBBB2", "reason": "wrong sheet"},
            )
        ]
        assert table(app.screen).row_count == 1
        assert "Rejected enrich.doc_classifier.discipline" in screen_text(app)

    scenario(client, steps)


def test_cancelling_the_reason_changes_nothing() -> None:
    client = client_with_values()

    async def steps(pilot: Pilot[Any], app: TlApp, screen: ReviewQueueScreen) -> None:
        await pilot.press("x")
        await pilot.pause()
        await pilot.press("escape")
        await pilot.pause()
        assert isinstance(app.screen, ReviewQueueScreen)
        assert client.integration_calls == [] and table(app.screen).row_count == 2

    scenario(client, steps)


def test_a_decided_value_is_not_decided_again() -> None:
    client = client_with_values()

    async def steps(pilot: Pilot[Any], app: TlApp, screen: ReviewQueueScreen) -> None:
        await pilot.press("s", "down", "down", "a")  # the third row is accepted already
        await pilot.pause()
        assert "This value is already accepted." in screen_text(app)
        await pilot.press("x")
        await pilot.pause()
        assert isinstance(app.screen, ReviewQueueScreen)
        assert client.integration_calls == []

    scenario(client, steps)


def test_a_refusal_is_shown_and_the_list_is_read_again() -> None:
    client = client_with_values()

    async def steps(pilot: Pilot[Any], app: TlApp, screen: ReviewQueueScreen) -> None:
        # someone else decided the value after the list was read
        client.integration_calls.clear()
        client._integration["enrichments"][0]["acceptance_state"] = "accepted"  # pyright: ignore
        await pilot.press("a")
        await pilot.pause()
        assert "! the value is accepted, not waiting" in screen_text(app)
        assert table(screen).row_count == 1  # reloaded: it left the queue

    scenario(client, steps)


def test_the_reload_key_reads_the_queue_again() -> None:
    client = client_with_values()

    async def steps(pilot: Pilot[Any], app: TlApp, screen: ReviewQueueScreen) -> None:
        client.seed_integration("enrichments", **rows.enrichment(value_id="01JVALUEDDDDDDDDDD4"))
        await pilot.press("f5")
        await pilot.pause()
        assert table(screen).row_count == 3 and "Reloaded." in screen_text(app)

    scenario(client, steps)
