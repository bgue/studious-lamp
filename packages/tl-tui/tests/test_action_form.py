"""The action form: what an action asks before it runs (P1-UX2-S2). It sends nothing."""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Sequence
from typing import Any

from helpers import run_pilot, screen_text
from textual.app import App
from textual.pilot import Pilot
from textual.widgets import Input, Static, TextArea
from tl_tui.widgets.action_form import ActionFormScreen, ChoiceField, FormField

PENDING = object()


class FormApp(App[None]):
    def __init__(self, form: ActionFormScreen) -> None:
        super().__init__()
        self.form = form
        self.result: object = PENDING

    def on_mount(self) -> None:
        self.push_screen(self.form, self.got)

    def got(self, result: dict[str, str] | None) -> None:
        self.result = result


def drive(
    form: ActionFormScreen,
    steps: Callable[[Pilot[Any], FormApp, ActionFormScreen], Awaitable[None]],
    size: tuple[int, int] = (100, 30),
) -> None:
    app = FormApp(form)

    async def go(pilot: Pilot[Any]) -> None:
        await pilot.pause()
        assert pilot.app.screen is form
        await steps(pilot, app, form)

    run_pilot(app, go, size=size)


def reason(form: ActionFormScreen) -> str:
    return str(form.query_one("#form-reason", Static).render())


ANSWER: Sequence[FormField] = (
    FormField("answer", "Answer", kind="text"),
    FormField("note", "Note", required=False),
)


def test_a_required_field_blocks_enter_and_ctrl_s_with_a_one_line_reason() -> None:
    form = ActionFormScreen("Close the RFI", (FormField("reason", "Reason"),))

    async def steps(pilot: Pilot[Any], app: FormApp, screen: ActionFormScreen) -> None:
        await pilot.press("enter")
        await pilot.pause()
        assert app.result is PENDING and reason(screen) == "Reason is required."
        await pilot.press("space", "ctrl+s")  # blanks do not count
        await pilot.pause()
        assert app.result is PENDING and "\n" not in reason(screen)
        await pilot.press(*"done")
        assert reason(screen) == ""  # typing clears the reason
        await pilot.press("enter")
        await pilot.pause()
        assert app.result == {"reason": "done"}

    drive(form, steps)


def test_a_blocked_form_puts_the_cursor_on_the_first_missing_field() -> None:
    form = ActionFormScreen(
        "Escalate",
        (FormField("who", "Who"), FormField("why", "Why"), FormField("also", "Also")),
    )

    async def steps(pilot: Pilot[Any], app: FormApp, screen: ActionFormScreen) -> None:
        await pilot.press(*"kim", "tab")  # Enter is send, so Tab moves on
        await pilot.press("ctrl+s")
        await pilot.pause()
        assert reason(screen) == "Why is required."
        assert screen.focused is screen.query_one("#field-why", Input)
        await pilot.press(*"scope", "tab", *"yes", "ctrl+s")
        await pilot.pause()
        assert app.result == {"who": "kim", "why": "scope", "also": "yes"}

    drive(form, steps)


def test_escape_returns_none() -> None:
    form = ActionFormScreen("Close", (FormField("reason", "Reason"),))

    async def steps(pilot: Pilot[Any], app: FormApp, screen: ActionFormScreen) -> None:
        await pilot.press(*"half", "escape")
        await pilot.pause()
        assert app.result is None

    drive(form, steps)


def test_an_optional_field_may_stay_empty() -> None:
    form = ActionFormScreen("Void", (FormField("reason", "Reason", required=False, default=""),))

    async def steps(pilot: Pilot[Any], app: FormApp, screen: ActionFormScreen) -> None:
        await pilot.press("enter")
        await pilot.pause()
        assert app.result == {"reason": ""}

    drive(form, steps)


def test_choice_cycles_with_left_and_right_and_wraps() -> None:
    form = ActionFormScreen(
        "Close", (FormField("outcome", "Outcome", kind="choice", choices=("Done", "Void", "Dup")),)
    )

    async def steps(pilot: Pilot[Any], app: FormApp, screen: ActionFormScreen) -> None:
        choice = screen.query_one("#field-outcome", ChoiceField)
        assert screen.focused is choice and choice.value == "Done"
        assert "Done" in screen_text(app)
        await pilot.press("right")
        assert choice.value == "Void"
        await pilot.press("right", "right")
        assert choice.value == "Done"  # wrapped
        await pilot.press("left")
        assert choice.value == "Dup"
        await pilot.press("enter")
        await pilot.pause()
        assert app.result == {"outcome": "Dup"}

    drive(form, steps)


def test_a_choice_starts_on_its_default() -> None:
    form = ActionFormScreen(
        "Close",
        (FormField("outcome", "Outcome", kind="choice", choices=("A", "B"), default="B"),),
    )

    async def steps(pilot: Pilot[Any], app: FormApp, screen: ActionFormScreen) -> None:
        assert screen.query_one("#field-outcome", ChoiceField).value == "B"

    drive(form, steps)


def test_confirm_only_asks_yes_or_no() -> None:
    async def yes_by_enter(pilot: Pilot[Any], app: FormApp, screen: ActionFormScreen) -> None:
        assert "Void this RFI?" in screen_text(app)
        await pilot.press("enter")
        await pilot.pause()
        assert app.result == {}

    async def yes_by_y(pilot: Pilot[Any], app: FormApp, screen: ActionFormScreen) -> None:
        await pilot.press("y")
        await pilot.pause()
        assert app.result == {}

    async def no_by_n(pilot: Pilot[Any], app: FormApp, screen: ActionFormScreen) -> None:
        await pilot.press("n")
        await pilot.pause()
        assert app.result is None

    async def no_by_escape(pilot: Pilot[Any], app: FormApp, screen: ActionFormScreen) -> None:
        await pilot.press("escape")
        await pilot.pause()
        assert app.result is None

    for steps in (yes_by_enter, yes_by_y, no_by_n, no_by_escape):
        drive(ActionFormScreen("Void", confirm="Void this RFI?"), steps)


def test_y_and_n_are_letters_when_there_are_fields() -> None:
    form = ActionFormScreen("Reason", (FormField("reason", "Reason"),))

    async def steps(pilot: Pilot[Any], app: FormApp, screen: ActionFormScreen) -> None:
        await pilot.press("y", "n", "y")
        await pilot.pause()
        assert app.result is PENDING
        assert screen.value_of(form.fields[0]) == "yny"

    drive(form, steps)


def test_a_confirm_text_above_fields_is_shown() -> None:
    form = ActionFormScreen(
        "Close", (FormField("reason", "Reason"),), confirm="This cannot be undone."
    )

    async def steps(pilot: Pilot[Any], app: FormApp, screen: ActionFormScreen) -> None:
        assert "This cannot be undone." in screen_text(app)

    drive(form, steps)


def test_multi_line_text_wraps_scrolls_and_enter_adds_a_line() -> None:
    form = ActionFormScreen("Answer", ANSWER)
    long = "word " * 60

    async def steps(pilot: Pilot[Any], app: FormApp, screen: ActionFormScreen) -> None:
        area = screen.query_one("#field-answer", TextArea)
        assert screen.focused is area and area.soft_wrap
        area.insert(long.strip())
        await pilot.pause()
        assert area.wrapped_document.height > 1  # one long line wraps to several rows
        await pilot.press("enter", *"end")
        await pilot.pause()
        assert app.result is PENDING  # Enter added a line; it did not send
        assert area.text.endswith("\nend")
        for _ in range(8):
            await pilot.press("enter", "x")
        await pilot.pause()
        assert area.scroll_offset.y > 0  # more lines than the box shows: it scrolls
        await pilot.press("ctrl+s")
        await pilot.pause()
        assert isinstance(app.result, dict)
        assert app.result["answer"].startswith("word word") and app.result["note"] == ""

    drive(form, steps)


def test_a_required_text_field_left_blank_blocks() -> None:
    form = ActionFormScreen("Answer", ANSWER)

    async def steps(pilot: Pilot[Any], app: FormApp, screen: ActionFormScreen) -> None:
        await pilot.press("enter", "enter", "ctrl+s")
        await pilot.pause()
        assert app.result is PENDING and reason(screen) == "Answer is required."

    drive(form, steps)
