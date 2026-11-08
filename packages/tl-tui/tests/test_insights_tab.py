"""The Insights tab (P2-INS T03) on ``FakeClient``: the Checks list, the four subtabs, the one
``note_need`` call per unbuilt subtab (record type only), a broken or refused note, the Enter
that opens a referenced record, and the words the tab must never use.
"""

from __future__ import annotations

import re
from typing import Any

from fakes import SCOPE, FakeClient
from helpers import run_pilot, static_of
from rich.text import Text
from textual.app import App, ComposeResult
from textual.message import Message
from textual.pilot import Pilot
from textual.widgets import Static
from tl_core.insights.types import CheckFinding
from tl_core.readiness.types import RecordRef
from tl_core.services.errors import ServiceError
from tl_tui.display import DisplayMode, Labels, find_technical
from tl_tui.messages import OpenRecord, StatusMessage
from tl_tui.widgets.insights_tab import InsightsTab
from tl_tui.widgets.record_view import RecordView

VALVE = "FV-1001"
WORDS_NOT_ALLOWED = re.compile(
    r"\b(AI|models?|providers?|OpenAI|Anthropic|Claude|LLM|GPT)\b", re.IGNORECASE
)


class Host(App[None]):
    def __init__(self, client: FakeClient, record: dict[str, Any], *, technical: bool = False):
        super().__init__()
        self.client = client
        self.record = record
        self.display_mode = DisplayMode()
        self.display_mode.technical = technical
        self.seen: list[Message] = []

    def compose(self) -> ComposeResult:
        yield InsightsTab(self.client, SCOPE, id="insights")

    def on_mount(self) -> None:
        tab = self.query_one(InsightsTab)
        tab.show_record(self.record)
        tab.focus()

    def on_status_message(self, message: StatusMessage) -> None:
        self.seen.append(message)

    def on_open_record(self, message: OpenRecord) -> None:
        self.seen.append(message)


def setup() -> tuple[FakeClient, dict[str, Any]]:
    client = FakeClient.with_valve_example()
    record = client.get_record(SCOPE, VALVE)
    assert record is not None
    return client, record


def finding(
    *,
    source: str = "readiness",
    state: str = "blocked",
    text: str = "Dry run not passed",
    severity: str = "blocking",
    refs: list[RecordRef] | None = None,
) -> CheckFinding:
    return CheckFinding(
        source=source,
        subject_id="01HAAAAAAAAAAAAAAAAAAAAAAA",
        state=state,
        text=text,
        since="2026-11-07",
        severity=severity,  # pyright: ignore[reportArgumentType]
        resolve_via=refs or [],
    )


async def settle(app: App[Any], pilot: Pilot[Any]) -> None:
    """Wait for the background read of the Checks subtab, then let the screen draw."""
    await app.workers.wait_for_complete()
    await pilot.pause()


def subtab_text(app: App[Any]) -> str:
    return static_of(app, "#insights-subtabs")


def body_text(app: App[Any]) -> str:
    return static_of(app, "#insights-body")


def test_checks_lists_the_findings_under_their_source_heading() -> None:
    client, record = setup()
    client.findings[record["id"]] = [finding(refs=[])]
    app = Host(client, record)

    async def scenario(pilot: Pilot[Any]) -> None:
        await settle(app, pilot)
        body = body_text(app)
        assert body.splitlines()[0] == "Readiness"
        assert "! blocked  Dry run not passed  (since 2026-11-07)" in body
        assert "Nothing needs attention." not in body

    run_pilot(app, scenario)


def test_checks_without_findings_says_nothing_needs_attention() -> None:
    client, record = setup()
    app = Host(client, record)

    async def scenario(pilot: Pilot[Any]) -> None:
        await settle(app, pilot)
        assert body_text(app) == "Nothing needs attention."

    run_pilot(app, scenario)


def test_left_and_right_cycle_the_four_subtabs() -> None:
    client, record = setup()
    app = Host(client, record)

    async def scenario(pilot: Pilot[Any]) -> None:
        await settle(app, pilot)
        assert subtab_text(app).startswith("[Checks]")
        await pilot.press("right")
        await pilot.pause()
        assert subtab_text(app) == "Checks  [Suggestions]  Analysis  Ask"
        assert body_text(app) == "Suggestions are not available yet."
        for _ in range(3):
            await pilot.press("right")
        await pilot.pause()
        assert subtab_text(app).startswith("[Checks]")
        await pilot.press("left")
        await pilot.pause()
        assert subtab_text(app).endswith("[Ask]")
        assert body_text(app) == "Ask is not available yet."

    run_pilot(app, scenario)


def test_opening_each_unbuilt_subtab_notes_one_need_with_no_record_id() -> None:
    client, record = setup()
    app = Host(client, record)

    async def scenario(pilot: Pilot[Any]) -> None:
        await settle(app, pilot)
        await pilot.press("right")
        await pilot.press("right")
        await pilot.press("right")
        await pilot.pause()
        rtype = record["type"]
        assert client.needs == [
            ("suggestion", "screen:insights.suggestions", rtype, None),
            ("analysis", "screen:insights.analysis", rtype, None),
            ("ask", "screen:insights.ask", rtype, None),
        ]

    run_pilot(app, scenario)


def test_checks_writes_no_need_and_reopening_a_subtab_makes_no_second_call() -> None:
    client, record = setup()
    app = Host(client, record)

    async def scenario(pilot: Pilot[Any]) -> None:
        await settle(app, pilot)
        await pilot.press("left")  # Ask: one note
        await pilot.press("right")  # Checks: none
        await pilot.press("right")  # Suggestions: one note
        await pilot.press("left")
        await pilot.press("right")  # Suggestions again: no note
        await pilot.pause()
        tab = app.query_one(InsightsTab)
        tab.show_record(record)  # the same record shown again: still no second call
        await settle(app, pilot)
        await pilot.press("left")
        await pilot.press("left")  # Ask again: still no second call
        await pilot.pause()
        assert [kind for kind, *_ in client.needs] == ["ask", "suggestion"]

    run_pilot(app, scenario)


def test_a_raising_note_need_does_not_break_the_screen() -> None:
    client, record = setup()

    def boom(**_kwargs: object) -> None:
        raise RuntimeError("telemetry is down")

    client.note_need = boom  # type: ignore[method-assign]
    app = Host(client, record)

    async def scenario(pilot: Pilot[Any]) -> None:
        await settle(app, pilot)
        await pilot.press("right")
        await pilot.pause()
        assert body_text(app) == "Suggestions are not available yet."
        await pilot.press("right")
        await pilot.pause()
        assert body_text(app) == "Analyses are not available yet."
        assert app.is_running

    run_pilot(app, scenario)


def test_a_refused_note_need_changes_nothing_on_screen() -> None:
    client, record = setup()
    client.note_need = lambda **_kwargs: None  # type: ignore[method-assign,assignment]
    app = Host(client, record)

    async def scenario(pilot: Pilot[Any]) -> None:
        await settle(app, pilot)
        await pilot.press("right")
        await pilot.pause()
        assert subtab_text(app).startswith("Checks  [Suggestions]")
        assert body_text(app) == "Suggestions are not available yet."

    run_pilot(app, scenario)


def test_a_finding_without_resolve_via_shows_no_reference_line() -> None:
    client, record = setup()
    client.findings[record["id"]] = [finding(refs=[])]
    app = Host(client, record)

    async def scenario(pilot: Pilot[Any]) -> None:
        await settle(app, pilot)
        assert all(not line.startswith("    ") for line in body_text(app).splitlines())

    run_pilot(app, scenario)


def test_enter_opens_the_first_record_a_finding_points_to() -> None:
    client, record = setup()
    ref = RecordRef(
        record_id="01HDDDDDDDDDDDDDDDDDDDDDDD", record_type="core.Record", key="FV-1002"
    )
    client.findings[record["id"]] = [finding(refs=[ref])]
    app = Host(client, record)

    async def scenario(pilot: Pilot[Any]) -> None:
        await settle(app, pilot)
        assert "    Record FV-1002" in body_text(app)
        await pilot.press("enter")
        await pilot.pause()
        opened = [m for m in app.seen if isinstance(m, OpenRecord)]
        assert [(m.key, m.follow) for m in opened] == [("FV-1002", True)]

    run_pilot(app, scenario)


def test_a_failed_read_keeps_the_display_and_posts_a_status_line() -> None:
    client, record = setup()

    def refused(record_id: str) -> list[CheckFinding]:
        raise ServiceError("checks are refused")

    client.checks = refused  # type: ignore[method-assign]
    app = Host(client, record)

    async def scenario(pilot: Pilot[Any]) -> None:
        await settle(app, pilot)
        assert body_text(app) == ""
        assert [m.text for m in app.seen if isinstance(m, StatusMessage)] == ["checks are refused"]

    run_pilot(app, scenario)


def test_no_subtab_or_finding_uses_a_model_or_provider_word() -> None:
    client, record = setup()
    client.findings[record["id"]] = [finding(refs=[]), finding(source="clocks", state="overdue")]
    app = Host(client, record)

    async def scenario(pilot: Pilot[Any]) -> None:
        await settle(app, pilot)
        labels = Labels()
        seen: list[str] = []
        for _ in range(4):
            seen += [subtab_text(app), body_text(app)]
            await pilot.press("right")
            await pilot.pause()
        for text in seen:
            assert WORDS_NOT_ALLOWED.search(text) is None, text
            assert find_technical(text, labels) == []

    run_pilot(app, scenario)


def test_plain_mode_shows_no_technical_token_in_the_checks() -> None:
    client, record = setup()
    client.findings[record["id"]] = [finding(refs=[])]
    app = Host(client, record)

    async def scenario(pilot: Pilot[Any]) -> None:
        await settle(app, pilot)
        body = body_text(app)
        assert "01HAAAAAAAAAAAAAAAAAAAAAAA" not in body
        assert find_technical(body, Labels()) == []

    run_pilot(app, scenario)


def test_technical_mode_adds_the_source_and_the_subject_id() -> None:
    client, record = setup()
    client.findings[record["id"]] = [finding(refs=[])]
    app = Host(client, record, technical=True)

    async def scenario(pilot: Pilot[Any]) -> None:
        await settle(app, pilot)
        assert "[readiness 01HAAAAAAAAAAAAAAAAAAAAAAA]" in body_text(app)

    run_pilot(app, scenario)


def open_suggestions(client: FakeClient, record: dict[str, Any]) -> None:
    """One app session: open the Suggestions subtab once and leave the app."""
    app = Host(client, record)

    async def scenario(pilot: Pilot[Any]) -> None:
        await settle(app, pilot)
        await pilot.press("right")
        await pilot.pause()

    run_pilot(app, scenario)


def test_up_and_down_move_the_cursor_and_enter_opens_the_highlighted_finding() -> None:
    client, record = setup()
    first = RecordRef(
        record_id="01HDDDDDDDDDDDDDDDDDDDDDDD", record_type="core.Record", key="FV-1002"
    )
    second = RecordRef(
        record_id="01HEEEEEEEEEEEEEEEEEEEEEEE", record_type="core.Record", key="FV-1003"
    )
    client.findings[record["id"]] = [
        finding(text="Dry run not passed", refs=[first]),
        finding(text="Pressure test not logged", refs=[second]),
    ]
    app = Host(client, record)

    async def scenario(pilot: Pilot[Any]) -> None:
        await settle(app, pilot)
        await pilot.press("enter")  # the cursor starts on the first finding
        await pilot.press("down")
        await pilot.press("enter")  # the second finding
        await pilot.press("down")  # stays on the last finding
        await pilot.press("enter")
        await pilot.press("up")
        await pilot.press("up")  # stays on the first finding
        await pilot.press("enter")
        opened = [m.key for m in app.seen if isinstance(m, OpenRecord)]
        assert opened == ["FV-1002", "FV-1003", "FV-1003", "FV-1002"]

    run_pilot(app, scenario)


def test_enter_on_a_finding_with_nothing_to_open_does_nothing() -> None:
    client, record = setup()
    ref = RecordRef(
        record_id="01HDDDDDDDDDDDDDDDDDDDDDDD", record_type="core.Record", key="FV-1002"
    )
    client.findings[record["id"]] = [
        finding(text="No link yet", refs=[]),
        finding(text="Dry run not passed", refs=[ref]),
    ]
    app = Host(client, record)

    async def scenario(pilot: Pilot[Any]) -> None:
        await settle(app, pilot)
        await pilot.press("enter")  # the highlighted finding points to nothing
        await pilot.pause()
        assert [m for m in app.seen if isinstance(m, OpenRecord)] == []
        await pilot.press("down")
        await pilot.press("enter")
        await pilot.pause()
        assert [m.key for m in app.seen if isinstance(m, OpenRecord)] == ["FV-1002"]

    run_pilot(app, scenario)


def test_the_highlighted_finding_is_drawn_reversed_and_follows_the_cursor() -> None:
    client, record = setup()
    ref = RecordRef(
        record_id="01HDDDDDDDDDDDDDDDDDDDDDDD", record_type="core.Record", key="FV-1002"
    )
    client.findings[record["id"]] = [
        finding(text="Dry run not passed", refs=[ref]),
        finding(text="Pressure test not logged", refs=[]),
    ]
    app = Host(client, record)

    def reversed_lines(app: App[Any]) -> list[str]:
        content = app.query_one("#insights-body", Static).content
        assert isinstance(content, Text)
        return [
            content.plain[span.start : span.end]
            for span in content.spans
            if span.style == "reverse"
        ]

    async def scenario(pilot: Pilot[Any]) -> None:
        await settle(app, pilot)
        assert reversed_lines(app) == ["! blocked  Dry run not passed  (since 2026-11-07)"]
        await pilot.press("down")
        await pilot.pause()
        assert reversed_lines(app) == ["! blocked  Pressure test not logged  (since 2026-11-07)"]

    run_pilot(app, scenario)


def test_a_rebuilt_tab_in_the_same_app_does_not_note_the_same_pair_twice() -> None:
    client, record = setup()
    app = Host(client, record)

    async def scenario(pilot: Pilot[Any]) -> None:
        await settle(app, pilot)
        await pilot.press("right")  # Suggestions: one note
        await pilot.pause()
        again = InsightsTab(client, SCOPE, id="insights-again")
        await app.mount(again)
        again.show_record(record)
        await settle(app, pilot)
        again.action_subtab(1)  # Suggestions again, in the rebuilt tab: no note
        again.action_subtab(1)  # Analysis: one more note
        await pilot.pause()
        assert [kind for kind, *_ in client.needs] == ["suggestion", "analysis"]

    run_pilot(app, scenario)


def test_each_app_session_notes_its_own_first_visit() -> None:
    client, record = setup()
    open_suggestions(client, record)
    open_suggestions(client, record)
    assert [kind for kind, *_ in client.needs] == ["suggestion", "suggestion"]


class RecordHost(App[None]):
    """The record view with its Insights pane (``9``), as the app shows it."""

    def __init__(self, client: FakeClient) -> None:
        super().__init__()
        self.client = client
        self.display_mode = DisplayMode()

    def compose(self) -> ComposeResult:
        yield RecordView(self.client, SCOPE, VALVE, id="record")


def test_9_opens_the_insights_tab_and_focuses_it() -> None:
    client, _ = setup()
    app = RecordHost(client)

    async def scenario(pilot: Pilot[Any]) -> None:
        await pilot.pause()
        await pilot.press("9")
        await settle(app, pilot)
        assert app.focused is app.query_one(InsightsTab)
        await pilot.press("right")  # the tab's own key now: Left and Right switch subtabs
        await pilot.pause()
        assert subtab_text(app).startswith("Checks  [Suggestions]")

    run_pilot(app, scenario, size=(120, 40))
