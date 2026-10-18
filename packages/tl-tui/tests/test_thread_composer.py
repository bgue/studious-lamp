"""The thread composer: verb completion, posting, previewing and confirming a slash command
(P1-I7 WS-B, T11b).

Provided; do not edit.
"""

from __future__ import annotations

from typing import Any

from fakes import SCOPE, FakeClient
from helpers import run_pilot, screen_text
from textual.app import App
from textual.pilot import Pilot
from textual.widgets import Input, OptionList, Static
from tl_core.integration.contract import PlannedCommand, Problem, RecordRef
from tl_core.threads.contract import DispatchPreview, ParseProblem
from tl_core.threads.dispatch import DispatchFromThread
from tl_core.threads.messages import PostThreadMessage
from tl_core.threads.parser import CommandLineParser
from tl_tui.widgets.thread_composer import ThreadComposer, verb_token


class Host(App[None]):
    def __init__(self, client: FakeClient, record: dict[str, Any], **kw: Any) -> None:
        super().__init__()
        self.client = client
        self.record = record
        self.kw = kw
        self.result: list[str | None] = []

    def on_mount(self) -> None:
        screen = ThreadComposer(self.client, self.record, actor="user:me", **self.kw)
        self.push_screen(screen, self.result.append)


def setup() -> tuple[FakeClient, dict[str, Any]]:
    client = FakeClient.with_valve_example()
    record = client.get_record(SCOPE, "FV-1001")
    assert record is not None
    return client, record


def field(app: App[Any]) -> Input:
    return app.screen.query_one("#tc-input", Input)


def popup(app: App[Any]) -> OptionList:
    return app.screen.query_one("#tc-popup", OptionList)


def error_text(app: App[Any]) -> str:
    return str(app.screen.query_one("#tc-error", Static).render())


def type_(app: App[Any], value: str) -> None:
    field(app).value = value
    field(app).cursor_position = len(value)


def link_preview(
    client: FakeClient, record: dict[str, Any], line: str, **kw: Any
) -> DispatchPreview:
    parsed = CommandLineParser().parse(line)
    assert parsed is not None and not isinstance(parsed, ParseProblem)
    return DispatchPreview(
        record=RecordRef(id=record["id"], key=record["key"], record_type="core.Record"),
        parsed=parsed,
        planned=[
            PlannedCommand(
                command_type="AddLink",
                access="user",
                permitted=True,
                summary="Link FV-1001 to FV-1002",
            )
        ],
        side_effecting=True,
        can_dispatch=kw.pop("can", True),
        token="b" * 64,
        expires_at="2026-10-17T09:00:00+00:00",
        **kw,
    )


def sent(client: FakeClient) -> list[PostThreadMessage]:
    return [c for c in client.thread_commands if isinstance(c, PostThreadMessage)]


# --- the pure function ------------------------------------------------------------------------


def test_verb_token() -> None:
    assert verb_token("/li", 3) == ("li", 1)
    assert verb_token("/", 1) == ("", 1)
    assert verb_token("  /rem", 6) == ("rem", 3)
    assert verb_token("/link A", 7) is None
    assert verb_token("/link A", 3) == ("li", 1)
    assert verb_token("hello /li", 9) is None
    assert verb_token("", 0) is None
    assert verb_token("/link", 0) is None


# --- completion -------------------------------------------------------------------------------


def test_a_slash_offers_the_verbs_and_tab_puts_the_chosen_one_in() -> None:
    client, record = setup()
    app = Host(client, record)

    async def scenario(pilot: Pilot[Any]) -> None:
        await pilot.pause()
        type_(app, "/")
        await pilot.pause()
        assert popup(app).display and popup(app).option_count == 11
        type_(app, "/re")
        await pilot.pause()
        assert popup(app).option_count == 2
        assert "release" in screen_text(app) and "remind" in screen_text(app)
        await pilot.press("down")
        await pilot.press("tab")
        assert field(app).value == "/remind "
        assert not popup(app).display

    run_pilot(app, scenario)


def test_hash_and_at_still_complete_records_and_people() -> None:
    client, record = setup()
    app = Host(client, record)

    async def scenario(pilot: Pilot[Any]) -> None:
        await pilot.pause()
        type_(app, "/link #FV-100")
        await pilot.pause()
        assert popup(app).display and popup(app).option_count == 3
        await pilot.press("tab")
        assert field(app).value == "/link #FV-1001 "

    run_pilot(app, scenario)


def test_escape_closes_the_list_then_cancels() -> None:
    client, record = setup()
    app = Host(client, record)

    async def scenario(pilot: Pilot[Any]) -> None:
        await pilot.pause()
        type_(app, "/l")
        await pilot.pause()
        await pilot.press("escape")
        assert isinstance(app.screen, ThreadComposer) and not popup(app).display
        await pilot.press("escape")
        await pilot.pause()
        assert app.result == [None]

    run_pilot(app, scenario)


# --- a plain message --------------------------------------------------------------------------


def test_a_plain_message_is_posted_and_the_screen_closes_with_its_id() -> None:
    client, record = setup()
    app = Host(client, record)

    async def scenario(pilot: Pilot[Any]) -> None:
        await pilot.pause()
        type_(app, "Flanges short for W019 @lchen")
        await pilot.press("enter")
        await pilot.pause()
        (cmd,) = sent(client)
        assert (cmd.actor, cmd.source, cmd.scope, cmd.record_id) == (
            "user:me",
            "tui",
            record["scope"],
            record["id"],
        )
        assert cmd.body == "Flanges short for W019 @lchen"
        assert len(app.result) == 1 and app.result[0] is not None
        assert "thread_preview" not in client.calls

    run_pilot(app, scenario)


def test_a_blank_message_is_not_sent_and_a_client_error_keeps_the_text() -> None:
    client, record = setup()
    app = Host(client, record)

    async def scenario(pilot: Pilot[Any]) -> None:
        await pilot.pause()
        type_(app, "   ")
        await pilot.press("enter")
        assert error_text(app) == "Write something first" and not client.thread_commands
        client.threads_enabled = False
        type_(app, "hello")
        await pilot.press("enter")
        await pilot.pause()
        assert "not switched on" in error_text(app)
        assert field(app).value == "hello" and isinstance(app.screen, ThreadComposer)
        assert app.result == []

    run_pilot(app, scenario)


# --- a slash command ----------------------------------------------------------------------------


def test_a_slash_line_is_previewed_first_and_enter_confirms_exactly_that_plan() -> None:
    client, record = setup()
    line = "/link FV-1002"
    client.script_preview(line, link_preview(client, record, line))
    app = Host(client, record)

    async def scenario(pilot: Pilot[Any]) -> None:
        await pilot.pause()
        type_(app, line)
        await pilot.press("enter")
        await pilot.pause()
        text = screen_text(app)
        assert "1. AddLink · user · ok · Link FV-1001 to FV-1002" in text
        assert "Enter to run, Esc to edit" in text
        assert not client.dispatched and not sent(client)
        await pilot.press("enter")
        await pilot.pause()
        (cmd,) = client.dispatched
        assert isinstance(cmd, DispatchFromThread)
        assert (cmd.text, cmd.token, cmd.actor) == (line, "b" * 64, "user:me")
        assert cmd.expires_at == "2026-10-17T09:00:00+00:00" and cmd.record_id == record["id"]
        assert len(app.result) == 1 and app.result[0] is not None

    run_pilot(app, scenario)


def test_escape_after_a_preview_goes_back_to_editing_and_an_edit_drops_the_preview() -> None:
    client, record = setup()
    line = "/link FV-1002"
    client.script_preview(line, link_preview(client, record, line))
    app = Host(client, record)

    async def scenario(pilot: Pilot[Any]) -> None:
        await pilot.pause()
        type_(app, line)
        await pilot.press("enter")
        await pilot.pause()
        assert "Enter to run" in screen_text(app)
        await pilot.press("escape")
        await pilot.pause()
        assert isinstance(app.screen, ThreadComposer) and field(app).value == line
        assert "Enter to run" not in screen_text(app) and not client.dispatched
        await pilot.press("enter")
        await pilot.pause()
        type_(app, line + " as requires")  # an edit after the preview
        await pilot.pause()
        assert "Enter to run" not in screen_text(app)
        await pilot.press("enter")  # previews the new line; it is not run
        await pilot.pause()
        assert not client.dispatched

    run_pilot(app, scenario)


def test_a_preview_that_cannot_run_is_shown_and_enter_runs_nothing() -> None:
    client, record = setup()
    line = "/status Closed"
    client.script_preview(
        line,
        link_preview(
            client,
            record,
            line,
            can=False,
            problems=[
                Problem(code="unknown_state", message="from Draft the record can go to: Issued")
            ],
        ),
    )
    app = Host(client, record)

    async def scenario(pilot: Pilot[Any]) -> None:
        await pilot.pause()
        type_(app, line)
        await pilot.press("enter")
        await pilot.pause()
        text = screen_text(app)
        assert "! from Draft the record can go to: Issued" in text
        assert "Cannot be dispatched: Esc to edit" in text
        await pilot.press("enter")
        await pilot.pause()
        assert not client.dispatched and isinstance(app.screen, ThreadComposer)

    run_pilot(app, scenario)


def test_a_parse_problem_is_shown_under_the_input() -> None:
    client, record = setup()
    app = Host(client, record)

    async def scenario(pilot: Pilot[Any]) -> None:
        await pilot.pause()
        type_(app, "/link")
        await pilot.press("enter")
        await pilot.pause()
        assert error_text(app).startswith("missing_argument: ")
        assert not client.dispatched and field(app).value == "/link"

    run_pilot(app, scenario)


def test_a_stale_token_goes_back_to_editing_with_a_message() -> None:
    client, record = setup()
    line = "/link FV-1002"
    preview = link_preview(client, record, line)
    client.script_preview(line, preview)
    app = Host(client, record)

    async def scenario(pilot: Pilot[Any]) -> None:
        await pilot.pause()
        type_(app, line)
        await pilot.press("enter")
        await pilot.pause()
        client.script_preview(
            line, preview.model_copy(update={"token": "c" * 64})
        )  # the server moved
        await pilot.press("enter")
        await pilot.pause()
        assert "The plan changed since the preview: preview it again" in error_text(app)
        assert isinstance(app.screen, ThreadComposer) and "Enter to run" not in screen_text(app)
        assert app.result == []

    run_pilot(app, scenario)


def test_dispatch_off_refuses_a_slash_line_but_not_a_message() -> None:
    client, record = setup()
    app = Host(client, record, dispatch=False)

    async def scenario(pilot: Pilot[Any]) -> None:
        await pilot.pause()
        type_(app, "/link FV-1002")
        await pilot.press("enter")
        await pilot.pause()
        assert error_text(app) == "Dispatch is switched off for this record"
        assert "thread_preview" not in client.calls
        type_(app, "plain words")
        await pilot.press("enter")
        await pilot.pause()
        assert len(sent(client)) == 1

    run_pilot(app, scenario)
