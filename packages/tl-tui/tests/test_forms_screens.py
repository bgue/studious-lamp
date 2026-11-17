"""The forms log, a submission's screen and the fill runner on `FakeClient` (V3-F1b), by pilot."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from fakes import SCOPE, FakeClient
from fakes_forms import seed_forms
from helpers import run_pilot, screen_text, settle, static_of
from textual.pilot import Pilot
from textual.widgets import DataTable, Input
from tl_mod_forms.commands import SubmitForm
from tl_tui.app import TlApp
from tl_tui.commands import APP_COMMANDS
from tl_tui.display import find_technical
from tl_tui.widgets.forms_log import FormRunnerScreen, FormsLogScreen, FormSubmissionScreen

SIZES = [(80, 40), (170, 44)]
Step = Callable[[Pilot[Any], TlApp], Awaitable[None]]


def make_app(*, actor: str = "user:uma") -> tuple[TlApp, FakeClient]:
    client = FakeClient()
    seed_forms(client)
    return TlApp(client, scope=SCOPE, actor=actor), client


def run(app: TlApp, steps: Step, size: tuple[int, int] = (170, 44)) -> None:
    async def go(pilot: Pilot[Any]) -> None:
        await settle(pilot)
        await steps(pilot, app)

    run_pilot(app, go, size=size)


async def type_line(pilot: Pilot[Any], typed: str) -> None:
    """Type a line into the focused input and press Enter."""
    for ch in typed:
        await pilot.press("space" if ch == " " else ch)
    await pilot.press("enter")
    await settle(pilot)


def numbers(screen: FormsLogScreen) -> list[str]:
    return [screen.row_cells(r)[0] for r in screen.shown]


def test_the_palette_lists_forms_and_its_action_exists() -> None:
    rows = {c.id: c for c in APP_COMMANDS}
    assert rows["forms"].action == "forms" and rows["forms"].keys == ""
    assert callable(getattr(TlApp, "action_forms", None))


def shown_at(size: tuple[int, int], keys: tuple[str, ...]) -> tuple[Any, str]:
    """The screen after ``app.action_forms()`` and ``keys``, and its text, at ``size``."""
    seen: dict[str, Any] = {}

    async def steps(pilot: Pilot[Any], app: TlApp) -> None:
        app.action_forms()
        await settle(pilot)
        for key in keys:
            await pilot.press(key)
            await settle(pilot)
        seen["screen"] = app.screen
        seen["text"] = screen_text(app)

    app, _ = make_app()
    run(app, steps, size=size)
    return seen["screen"], seen["text"]


def test_the_log_mounts_at_80_and_170_columns_without_overflow() -> None:
    for size in SIZES:
        screen, text = shown_at(size, ())
        seen = {"screen": screen, "text": text}
        assert isinstance(seen["screen"], FormsLogScreen)
        lines = seen["text"].splitlines()
        assert all(len(line) <= size[0] for line in lines), f"overflow at {size}"
        header = next(line for line in lines if "Number" in line)
        assert header.index("Form") < header.index("State"), f"Form right of State at {size}"


def test_the_submissions_view_lists_the_rows_the_client_gave() -> None:
    seen: dict[str, Any] = {}

    async def steps(pilot: Pilot[Any], app: TlApp) -> None:
        app.action_forms()
        await settle(pilot)
        screen = app.screen
        assert isinstance(screen, FormsLogScreen)
        seen["numbers"] = numbers(screen)
        seen["summary"] = static_of(screen, "#log-status")

    app, _ = make_app()
    run(app, steps)
    assert sorted(seen["numbers"]) == ["(draft)", "P123-FRM-0001", "P123-FRM-0002"]
    assert "3 form submissions" in seen["summary"]


def test_tab_shows_the_published_templates_only_and_back() -> None:
    seen: dict[str, Any] = {}

    async def steps(pilot: Pilot[Any], app: TlApp) -> None:
        app.action_forms()
        await settle(pilot)
        screen = app.screen
        assert isinstance(screen, FormsLogScreen)
        await pilot.press("2")
        await settle(pilot)
        seen["templates"] = numbers(screen)
        seen["name"] = screen.LOG_NAME
        await pilot.press("tab")
        await settle(pilot)
        seen["back"] = screen.LOG_NAME

    app, _ = make_app()
    run(app, steps)
    assert seen["templates"] == ["TPL-0001", "TPL-0002"]  # the Retired one is not offered
    assert seen["name"] == "Form templates" and seen["back"] == "Form submissions"


def test_enter_on_a_submission_opens_its_screen_with_the_questions_in_words() -> None:
    seen: dict[str, Any] = {}

    async def steps(pilot: Pilot[Any], app: TlApp) -> None:
        app.action_forms()
        await settle(pilot)
        log = app.screen
        assert isinstance(log, FormsLogScreen)
        row = next(r for r in log.shown if r.key == "P123-FRM-0002")
        log.open_row(row)
        await settle(pilot)
        seen["screen"] = app.screen
        seen["text"] = static_of(app.screen, "#fs-page")
        await pilot.press("escape")
        await settle(pilot)
        seen["back"] = app.screen is log

    app, _ = make_app()
    run(app, steps)
    assert isinstance(seen["screen"], FormSubmissionScreen)
    text = seen["text"]
    assert "P123-FRM-0002 · Pre-use check" in text
    assert "Question tool" in text and "Drill" in text and "yes (serviced)" in text
    assert "Checked and filed." in text and seen["back"]


def test_a_key_that_is_not_there_is_one_not_found() -> None:
    seen: dict[str, str] = {}

    async def steps(pilot: Pilot[Any], app: TlApp) -> None:
        for key in ("P123-FRM-9999", "01J000000000000000000000"):
            app.push_screen(FormSubmissionScreen(app.client, "P123", key))
            await settle(pilot)
            seen[key] = (
                static_of(app.screen, "#fs-status") + "|" + static_of(app.screen, "#fs-page")
            )
            await pilot.press("escape")
            await settle(pilot)

    app, _ = make_app()
    run(app, steps)
    assert set(seen.values()) == {"! no such submission|This form could not be read."}


def test_the_runner_walks_one_question_at_a_time_skips_hidden_and_submits() -> None:
    seen: dict[str, Any] = {}

    async def steps(pilot: Pilot[Any], app: TlApp) -> None:
        app.action_forms()
        await settle(pilot)
        log = app.screen
        assert isinstance(log, FormsLogScreen)
        await pilot.press("2")
        await settle(pilot)
        await pilot.press("f")  # fill the highlighted template (TPL-0001)
        await settle(pilot)
        runner_screen = app.screen
        assert isinstance(runner_screen, FormRunnerScreen)
        seen["first"] = static_of(runner_screen, "#fr-head")
        await type_line(pilot, "Ladders")
        seen["second"] = static_of(runner_screen, "#fr-head")
        await type_line(pilot, "many")  # not a number: refused, stays on the question
        seen["refused"] = static_of(runner_screen, "#fr-status")
        seen["still"] = static_of(runner_screen, "#fr-head")
        await pilot.press("up")  # back to the first question; its answer is in the line
        await settle(pilot)
        seen["back_value"] = runner_screen.query_one("#fr-input", Input).value
        await type_line(pilot, "Ladders")
        await type_line(pilot, "12")
        await type_line(pilot, "yes")
        seen["optional"] = static_of(runner_screen, "#fr-head")
        await type_line(pilot, "1,3")  # hazards by number
        seen["last"] = static_of(runner_screen, "#fr-head")
        seen["review"] = static_of(runner_screen, "#fr-page")
        seen["review_head"] = static_of(runner_screen, "#fr-head")
        await pilot.press("enter")  # send
        await settle(pilot)
        seen["after"] = app.screen is log
        seen["numbers"] = numbers(log)
        seen["status"] = static_of(log, "#log-status")

    app, client = make_app()
    run(app, steps)
    assert seen["first"] == "Toolbox talk · Question 1 of 4 · Talk"
    assert seen["second"] == "Toolbox talk · Question 2 of 4"
    assert seen["refused"].startswith("! count: must be a number")
    assert seen["still"] == seen["second"]
    assert seen["back_value"] == "Ladders"
    assert seen["optional"].endswith("Question 4 of 4")
    assert seen["last"].endswith("Review")
    assert "Falls, Electrical" in seen["review"] and "Question detail" not in seen["review"]
    assert seen["review_head"].endswith("Review")
    assert seen["after"]
    assert "P123-FRM-0003" in seen["numbers"]  # the next number after 0002 (the draft has none)
    assert seen["status"].startswith("Submitted P123-FRM-")
    (cmd,) = client.form_commands
    assert isinstance(cmd, SubmitForm)
    assert cmd.actor == "user:uma" and cmd.scope == "project:P123" and cmd.template_id == "TPL-ID-1"
    assert {a["q"]: a["value"] for a in cmd.answers} == {
        "topic": "Ladders",
        "count": 12,
        "ppe": "yes",
        "hazards": ["Falls", "Electrical"],
    }


def test_a_required_question_cannot_be_skipped_and_an_optional_one_can() -> None:
    seen: dict[str, str] = {}

    async def steps(pilot: Pilot[Any], app: TlApp) -> None:
        app.action_forms()
        await settle(pilot)
        await pilot.press("2")
        await settle(pilot)
        await pilot.press("f")
        await settle(pilot)
        screen = app.screen
        await pilot.press("enter")  # an empty line on a required question
        await settle(pilot)
        seen["refused"] = static_of(screen, "#fr-status")
        for line in ("Ladders", "5", "no"):
            await type_line(pilot, line)
        seen["hidden_shown"] = static_of(screen, "#fr-head")  # hazards, optional
        await pilot.press("enter")  # empty line: skipped
        await settle(pilot)
        seen["next"] = static_of(screen, "#fr-head")  # "detail" is visible when ppe is no

    app, _ = make_app()
    run(app, steps)
    assert seen["refused"] == "! topic: answer required"
    assert seen["hidden_shown"].endswith("Question 4 of 5")
    assert seen["next"].endswith("Question 5 of 5")


def test_a_refusal_of_the_send_is_the_status_line_and_the_review_stays() -> None:
    seen: dict[str, Any] = {}

    async def steps(pilot: Pilot[Any], app: TlApp) -> None:
        app.action_forms()
        await settle(pilot)
        await pilot.press("2")
        await settle(pilot)
        await pilot.press("down")  # TPL-0002, Pre-use check
        await settle(pilot)
        await pilot.press("f")
        await settle(pilot)
        screen = app.screen
        assert isinstance(screen, FormRunnerScreen)
        await type_line(pilot, "Drill")
        await type_line(pilot, "yes")
        # the server (the fake) now refuses: the template changed under the person
        app.client.load_form_templates([])  # type: ignore[attr-defined]
        await pilot.press("enter")
        await settle(pilot)
        seen["status"] = static_of(screen, "#fr-status")
        seen["still"] = app.screen is screen

    app, client = make_app()
    run(app, steps)
    assert seen["status"] == "! no such template" and seen["still"]
    assert client.form_commands == []


def test_escape_cancels_the_runner_and_sends_nothing() -> None:
    async def steps(pilot: Pilot[Any], app: TlApp) -> None:
        app.action_forms()
        await settle(pilot)
        log = app.screen
        await pilot.press("2")
        await settle(pilot)
        await pilot.press("f")
        await settle(pilot)
        await type_line(pilot, "Ladders")
        await pilot.press("escape")
        await settle(pilot)
        assert app.screen is log

    app, client = make_app()
    run(app, steps)
    assert client.form_commands == []


def test_the_runner_screens_fit_80_and_170_columns() -> None:
    for size in SIZES:
        _screen, text = shown_at(size, ("2", "f"))
        assert all(len(line) <= size[0] for line in text.splitlines())
        assert "Question topic" in text


def test_a_published_template_offers_fill_and_a_submission_offers_nothing() -> None:
    seen: dict[str, Any] = {}

    async def steps(pilot: Pilot[Any], app: TlApp) -> None:
        app.action_forms()
        await settle(pilot)
        screen = app.screen
        assert isinstance(screen, FormsLogScreen)
        seen["sub"] = [a.key for a in screen.actions_for(screen.shown[0])]
        await pilot.press("2")
        await settle(pilot)
        seen["tpl"] = [a.key for a in screen.actions_for(screen.shown[0])]
        seen["table"] = screen.query_one("#log-table", DataTable).row_count
        seen["bar"] = static_of(screen, "#log-actions")

    app, _ = make_app()
    run(app, steps)
    assert seen["sub"] == [] and seen["tpl"] == ["f"] and seen["table"] == 2
    assert "Fill this form" in seen["bar"]


def test_no_screen_shows_an_id_a_hash_or_a_key_in_plain_mode() -> None:
    seen: list[str] = []

    async def steps(pilot: Pilot[Any], app: TlApp) -> None:
        app.action_forms()
        await settle(pilot)
        log = app.screen
        assert isinstance(log, FormsLogScreen)
        seen.append(screen_text(app))
        row = next(r for r in log.shown if r.key == "P123-FRM-0002")
        log.open_row(row)
        await settle(pilot)
        seen.append(screen_text(app))
        await pilot.press("escape")
        await settle(pilot)
        await pilot.press("2")
        await settle(pilot)
        seen.append(screen_text(app))
        await pilot.press("f")
        await settle(pilot)
        seen.append(screen_text(app))

    app, _ = make_app()
    run(app, steps)
    assert len(seen) == 4
    for text in seen:
        assert find_technical(text) == []
        assert "TPL-ID" not in text and "SUB-" not in text  # the ids of the rows
