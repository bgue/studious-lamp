"""Links tab and Thread tab in plain words, and the technical toggle that shows the raw text
(P1-UX-T08b).

Plain mode is the default; ``technical=True`` (and the app's technical flag) keeps today's text.
Every area keeps one technical assertion so the toggle is checked, not just the plain words.
"""

from __future__ import annotations

from typing import Any

from fakes import SCOPE, FakeClient
from helpers import run_pilot, screen_text
from textual.app import App, ComposeResult
from textual.pilot import Pilot
from tl_core.integration.contract import RecordRef
from tl_core.links.expected import ExpectedLink, MissingLink
from tl_core.threads.contract import DispatchOutcome, DispatchResult, ThreadMessageView
from tl_core.threads.queries import ThreadPage, ThreadParticipant
from tl_tui.app import TlApp
from tl_tui.display import DisplayMode, Labels, find_technical
from tl_tui.thread_text import card_lines, header_text, message_lines, person
from tl_tui.widgets.links_tab import missing_line
from tl_tui.widgets.thread_tab import ThreadTab

RECORD = RecordRef(id="R1", key="IWP-0042", record_type="core.Record", version=3)


def missing(*, found: int, needed: int) -> MissingLink:
    return MissingLink(
        expectation=ExpectedLink(
            relation="references", label="supporting record", by_state="Approved"
        ),
        found=found,
        needed=needed,
    )


def page(
    messages: list[ThreadMessageView],
    *,
    record: RecordRef = RECORD,
    enabled: bool = True,
) -> ThreadPage:
    return ThreadPage(
        record=record,
        enabled=enabled,
        dispatch_enabled=True,
        message_count=len(messages),
        participants=[ThreadParticipant(actor="user:p0")],
        messages=messages,
        seqs=list(range(1, len(messages) + 1)),
        kinds=["message"] * len(messages),
    )


def message(n: int, body: str, *, author: str) -> ThreadMessageView:
    return ThreadMessageView(
        message_id=f"M{n}",
        record_id="R1",
        author=author,
        body=body,
        posted_at=f"2026-10-17T07:{n:02d}:30+00:00",
    )


# --- the links tab's missing line -----------------------------------------------------------


def test_missing_line_plain_and_technical() -> None:
    one = missing(found=0, needed=1)
    assert missing_line(one) == (
        "! expected but missing: supporting record (rule: references@Approved)"
    )
    assert missing_line(one, technical=False) == "! expected but missing: supporting record"
    two = missing(found=1, needed=2)
    assert missing_line(two) == (
        "! expected but missing: supporting record (rule: references@Approved, 1 of 2)"
    )
    plain = missing_line(two, technical=False)
    assert plain == "! expected but missing: supporting record (1 of 2 needed)"
    assert "@" not in plain and "rule:" not in plain


# --- the thread text ------------------------------------------------------------------------


def test_thread_text_plain_and_technical() -> None:
    labels = Labels(services={"svc:threads": "Thread service"})
    assert person("agent:planner") == "agent:planner ⚙"
    assert person("agent:planner", technical=False) == "planner ⚙"
    assert person("svc:threads", labels, technical=False) == "Thread service"
    assert person("svc:threads", technical=False) == "a service"
    assert person("svc:threads") == "svc:threads"
    assert person("user:rgarcia", technical=False) == "rgarcia"

    off = page([], enabled=False)
    assert header_text(off) == "IWP-0042 · Thread · threads are off for core.Record"
    named = Labels(type_titles={"core.Record": "Project record"})
    assert header_text(off, named, technical=False) == (
        "IWP-0042 · Thread · threads are off for Project record"
    )
    keyless = page([], enabled=False, record=RecordRef(id="R9", record_type="core.Record"))
    assert header_text(keyless, technical=False) == (
        "this record · Thread · threads are off for Record"
    )

    outcome = DispatchOutcome(
        message_id="M3",
        verb="raise",
        summary="Create record: Clash",
        results=[
            DispatchResult(
                command_type="CreateRecord", stream_id="S1", key="P123-REC-0044", version=1
            ),
            DispatchResult(command_type="AddLink", stream_id="S9", version=1),
        ],
        link_ids=["L1"],
    )
    assert card_lines(outcome) == [
        "▤ raise: Create record: Clash",
        "  CreateRecord P123-REC-0044 v1",
        "  AddLink S9 v1",
        "  1 dispatched-from link added",
    ]
    plain = card_lines(outcome, technical=False)
    assert plain == [
        "▤ raise: Create record: Clash",
        "  Create record P123-REC-0044",
        "  Add link a record",
        "  1 dispatched-from link added",
    ]
    assert "v1" not in "\n".join(plain) and "S1" not in "\n".join(plain)
    lines = message_lines(
        page([message(1, "/raise record Clash", author="agent:planner")]),
        labels,
        technical=False,
    )
    assert lines[0] == "07:01 planner ⚙  /raise record Clash"


# --- the thread tab, drawn and toggled ------------------------------------------------------


class Host(App[None]):
    """A bare app with a display mode, so the tab reads the technical flag the way it does
    inside the real app."""

    def __init__(self, client: FakeClient, record: dict[str, Any]) -> None:
        super().__init__()
        self.client = client
        self.record = record
        self.display_mode = DisplayMode()

    def compose(self) -> ComposeResult:
        yield ThreadTab(self.client, SCOPE, actor="user:me", id="tab")

    def on_mount(self) -> None:
        tab = self.query_one(ThreadTab)
        tab.show_record(self.record)
        tab.focus()


def test_thread_tab_plain_has_no_technical_tokens_and_toggles() -> None:
    client = FakeClient.with_valve_example()
    record = client.get_record(SCOPE, "FV-1001")
    assert record is not None
    client.seed_message(record["id"], "Crew P-07 starting tie-ins")
    client.seed_message(record["id"], "On it", author="agent:planner")
    client.seed_message(record["id"], "Relay ready", author="svc:threads")
    outcome = DispatchOutcome(
        message_id="x",
        verb="raise",
        summary="Create record: Clash",
        results=[
            DispatchResult(command_type="CreateRecord", stream_id="S", key="NEW-1", version=1)
        ],
    )
    client.seed_message(record["id"], "/raise record Clash", kind="dispatch", dispatch=outcome)
    app = Host(client, record)

    async def scenario(pilot: Pilot[Any]) -> None:
        await pilot.pause()
        tab = app.query_one(ThreadTab)
        text = screen_text(app)
        assert "FV-1001 · Thread · 3 participants · dispatch on" in text
        assert "planner ⚙  On it" in text and "Create record NEW-1" in text
        assert "agent:planner" not in text and "CreateRecord" not in text and " v1" not in text
        assert find_technical(text) == []

        app.display_mode.technical = True
        tab.refresh_for_display_mode()
        await pilot.pause()
        raw = screen_text(app)
        assert "agent:planner ⚙  On it" in raw and "CreateRecord NEW-1 v1" in raw

        app.display_mode.technical = False
        tab.refresh_for_display_mode()
        await pilot.pause()
        again = screen_text(app)
        assert "agent:planner" not in again and find_technical(again) == []

    run_pilot(app, scenario)


# --- the links tab redraws on the mode switch -----------------------------------------------


def test_links_tab_missing_line_refreshes_on_the_mode_switch() -> None:
    client = FakeClient.with_valve_example()
    # a raised_against link does not satisfy the data-sheet expectation (references@Installed)
    client.seed_link("FV-1001", "FV-1002", "raised_against")
    app = TlApp(client, is_admin=True)

    async def scenario(pilot: Pilot[Any]) -> None:
        await pilot.pause()
        await pilot.press("enter")  # open FV-1001
        await pilot.pause()
        await pilot.press("3")
        await pilot.pause()
        text = screen_text(app)
        assert "! expected but missing: data sheet" in text and "@Installed" not in text
        assert "FV-1002" in text

        await pilot.press("ctrl+d")  # technical on: the toggle calls the refresh hooks
        await pilot.pause()
        raw = screen_text(app)
        assert "! expected but missing: data sheet (rule: references@Installed)" in raw
        assert "FV-1002" in raw  # the table is kept

        await pilot.press("ctrl+d")  # technical off again
        await pilot.pause()
        assert "@Installed" not in screen_text(app)

    run_pilot(app, scenario, size=(130, 40))
