"""The thread tab: messages, participants, result cards, paging and the compose key
(P1-I7 WS-B, T11a).

Provided; do not edit.
"""

from __future__ import annotations

from typing import Any

from fakes import SCOPE, FakeClient
from helpers import run_pilot, screen_text
from textual.app import App, ComposeResult
from textual.message import Message
from textual.pilot import Pilot
from tl_core.services.errors import RecordNotFoundError
from tl_core.threads.contract import DispatchOutcome, DispatchResult
from tl_tui.messages import RecordChanged, StatusMessage
from tl_tui.widgets.thread_composer import ThreadComposer
from tl_tui.widgets.thread_tab import ThreadTab


class Host(App[None]):
    def __init__(self, client: FakeClient, record: dict[str, Any]) -> None:
        super().__init__()
        self.client = client
        self.record = record
        self.seen: list[Message] = []

    def compose(self) -> ComposeResult:
        yield ThreadTab(self.client, SCOPE, actor="user:me", id="tab")

    def on_mount(self) -> None:
        tab = self.query_one(ThreadTab)
        tab.show_record(self.record)
        tab.focus()

    def on_status_message(self, message: StatusMessage) -> None:
        self.seen.append(message)

    def on_record_changed(self, message: RecordChanged) -> None:
        self.seen.append(message)


def setup() -> tuple[FakeClient, dict[str, Any]]:
    client = FakeClient.with_valve_example()
    record = client.get_record(SCOPE, "FV-1001")
    assert record is not None
    return client, record


def test_the_header_and_the_messages_are_drawn_oldest_first() -> None:
    client, record = setup()
    client.seed_message(record["id"], "Crew P-07 starting tie-ins\nFlanges short")
    client.seed_message(record["id"], "On it", author="agent:planner")
    app = Host(client, record)

    async def scenario(pilot: Pilot[Any]) -> None:
        await pilot.pause()
        text = screen_text(app)
        assert "FV-1001 · Thread · 2 participants · dispatch on" in text
        assert text.index("Crew P-07 starting tie-ins") < text.index("planner ⚙  On it")
        assert "agent:planner" not in text  # plain mode; the raw actor id is technical only
        assert "      Flanges short" in text
        assert "c compose" in text

    run_pilot(app, scenario)


def test_a_dispatch_message_shows_its_result_card() -> None:
    client, record = setup()
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
        text = screen_text(app)
        assert "▤ raise: Create record: Clash" in text and "Create record NEW-1" in text
        assert "v1" not in text  # plain mode: no version on the card

    run_pilot(app, scenario)


def test_an_empty_thread_and_a_type_without_threads_say_so() -> None:
    client, record = setup()
    app = Host(client, record)

    async def empty(pilot: Pilot[Any]) -> None:
        await pilot.pause()
        assert "No messages yet." in screen_text(app)

    run_pilot(app, empty)
    client.threads_enabled = False
    off = Host(client, record)

    async def disabled(pilot: Pilot[Any]) -> None:
        await pilot.pause()
        text = screen_text(off)
        assert "Threads are not switched on for this type." in text
        assert "c compose" not in text
        await pilot.press("c")
        await pilot.pause()
        assert not isinstance(off.screen, ThreadComposer)
        assert any(isinstance(m, StatusMessage) and "not switched on" in m.text for m in off.seen)

    run_pilot(off, disabled)


def test_o_loads_the_older_page_above_the_newest() -> None:
    client, record = setup()
    for n in range(60):
        client.seed_message(record["id"], f"message {n:02d}")
    app = Host(client, record)

    async def scenario(pilot: Pilot[Any]) -> None:
        await pilot.pause()
        text = screen_text(app)
        assert "o older" in text and "message 59" in text
        tab = app.query_one(ThreadTab)
        assert "message 05" not in "\n".join(str(w.render()) for w in tab.query("#thread-body"))
        await pilot.press("o")
        await pilot.pause()
        body = str(tab.query_one("#thread-body").render())
        assert body.index("message 00") < body.index("message 10") < body.index("message 59")
        assert "o older" not in screen_text(app)

    run_pilot(app, scenario, size=(120, 100))


def test_c_opens_the_composer_and_a_sent_message_reloads_the_tab() -> None:
    client, record = setup()
    app = Host(client, record)

    async def scenario(pilot: Pilot[Any]) -> None:
        await pilot.pause()
        await pilot.press("c")
        await pilot.pause()
        assert isinstance(app.screen, ThreadComposer)
        app.screen.query_one("#tc-input").value = "hello thread"  # type: ignore[attr-defined]
        await pilot.press("enter")
        await pilot.pause()
        await pilot.pause()
        assert not isinstance(app.screen, ThreadComposer)
        assert "hello thread" in screen_text(app)
        assert any(isinstance(m, RecordChanged) for m in app.seen)

    run_pilot(app, scenario)


def test_a_client_error_is_a_status_line_and_keeps_the_display() -> None:
    client, record = setup()
    client.seed_message(record["id"], "kept")
    app = Host(client, record)

    async def scenario(pilot: Pilot[Any]) -> None:
        await pilot.pause()

        def missing(*_args: Any, **_kwargs: Any) -> Any:
            raise RecordNotFoundError("no record")

        client.thread_page = missing  # type: ignore[method-assign]
        app.query_one(ThreadTab).reload()
        await pilot.pause()
        assert any(isinstance(m, StatusMessage) and m.severity == "error" for m in app.seen)
        assert "kept" in screen_text(app)

    run_pilot(app, scenario)


def test_a_client_with_no_threads_leaves_the_tab_empty() -> None:
    client, record = setup()

    def unsupported(*_args: Any, **_kwargs: Any) -> Any:
        raise NotImplementedError

    client.thread_page = unsupported  # type: ignore[method-assign]
    app = Host(client, record)

    async def scenario(pilot: Pilot[Any]) -> None:
        await pilot.pause()
        tab = app.query_one(ThreadTab)
        assert tab.page is None and not app.seen
        tab.action_older()  # nothing to page: no crash
        await pilot.pause()

    run_pilot(app, scenario)
