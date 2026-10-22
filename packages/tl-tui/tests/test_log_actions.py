"""What a log offers on a record comes from the server and runs through a form (P1-UX2-S3).

The fake client's ``set_actions`` is the server: the RFI log shows exactly the offers returned for
the highlighted row, keyed by ``ACTION_UI``; an offer with no UI entry is not shown; a refusal from
the command lands in the status line.
"""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from typing import Any

import pytest
from fakes import SCOPE, FakeClient
from fakes_correspondence import seed_domains
from helpers import run_pilot, settle
from textual.pilot import Pilot
from textual.screen import Screen
from textual.widgets import Static
from tl_core.actions import ActionOffer, RecordActions
from tl_core.services.errors import RecordNotFoundError
from tl_mod_correspondence.handlers.commercial import ReviewCommercial
from tl_mod_correspondence.handlers.technical_flow import AnswerTechnical, CloseTechnical
from tl_mod_engineering.handlers.tags import RenameTag
from tl_tui import log_actions
from tl_tui.app import TlApp
from tl_tui.log_actions import ACTION_UI, ENVELOPE, ActionUi
from tl_tui.log_actions import log_actions as present
from tl_tui.widgets.domain_screen import DomainScreen
from tl_tui.widgets.tag_register import TagRegisterScreen

RFI1, RFI2 = "ID-P123-RFI-0001", "ID-P123-RFI-0002"
ANSWERER = (
    ("AnswerTechnical", "Answer"),
    ("CloseTechnical", "Close"),
    ("EscalateTechnical", "Escalate"),
)


def world(*, controller: bool = True) -> FakeClient:
    client = FakeClient()
    seed_domains(client)
    client.is_corr_controller = controller
    return client


def scenario(
    client: FakeClient,
    steps: Callable[[Pilot[None], TlApp, DomainScreen], Awaitable[None]],
) -> None:
    app = TlApp(client, scope=SCOPE, actor="user:kim")

    async def go(pilot: Pilot[None]) -> None:
        await pilot.press("ctrl+g")
        await settle(pilot)
        assert isinstance(app.screen, DomainScreen)
        await steps(pilot, app, app.screen)

    run_pilot(app, go)


def bar(screen: Screen[Any]) -> str:
    return str(screen.query_one("#log-actions", Static).render())


def status(screen: Screen[Any]) -> str:
    return str(screen.query_one("#log-status", Static).render())


def offers(*pairs: tuple[str, str]) -> RecordActions:
    return RecordActions(
        record_id="R",
        state=None,
        actions=[ActionOffer(command=c, label=label) for c, label in pairs],
    )


# --- the mapping, without a screen --------------------------------------------------------


def test_offers_map_to_the_keys_of_the_table_in_the_order_the_server_gave() -> None:
    ran: list[str] = []
    shown = present(
        offers(*ANSWERER), ACTION_UI, lambda label, ui, prepare: ran.append(label), version=3
    )
    assert [(a.key, a.label) for a in shown] == [("a", "Answer"), ("c", "Close"), ("e", "Escalate")]
    shown[1].run()
    assert ran == ["Close"]


def test_an_offer_without_a_ui_entry_is_not_shown_and_is_logged_once(
    caplog: pytest.LogCaptureFixture,
) -> None:
    log_actions._unknown_logged.clear()  # pyright: ignore[reportPrivateUsage]
    given = offers(("CloseTechnical", "Close"), ("MadeUpCommand", "Do magic"))
    with caplog.at_level(logging.INFO, logger="tl_tui.log_actions"):
        first = present(given, ACTION_UI, lambda *_: None)
        second = present(given, ACTION_UI, lambda *_: None)
    assert [a.label for a in first] == ["Close"] == [a.label for a in second]
    assert [r.getMessage() for r in caplog.records if "MadeUpCommand" in r.getMessage()] == [
        "no screen action for the offered command MadeUpCommand"
    ]


def test_the_table_builds_the_command_with_the_typed_values_and_the_row_version() -> None:
    answer = ACTION_UI["AnswerTechnical"].build(
        {"answer": "Use 600 mm", "cost_impact": "yes", "schedule_impact": "no"}, RFI1, 4
    )
    assert isinstance(answer, AnswerTechnical)
    assert (answer.stream_id, answer.expected_version, answer.answer) == (RFI1, 4, "Use 600 mm")
    assert (answer.cost_impact, answer.schedule_impact) == ("yes", "no")
    close = ACTION_UI["CloseTechnical"].build({"reason": " "}, RFI1, 2)
    assert isinstance(close, CloseTechnical) and close.reason is None
    assert ENVELOPE["source"] == "tui"
    assert isinstance(ACTION_UI["CloseTechnical"], ActionUi)


# --- on the RFI log ----------------------------------------------------------------------


def test_the_bar_of_an_rfi_differs_between_an_answerer_and_a_reader() -> None:
    answerer = world()
    answerer.set_actions(RFI1, *ANSWERER)
    reader = world(controller=False)  # offers nothing: a reader may only look

    async def answerer_steps(pilot: Pilot[None], app: TlApp, screen: DomainScreen) -> None:
        assert bar(screen) == "[a] Answer  [c] Close  [e] Escalate  [Enter] Open record"

    async def reader_steps(pilot: Pilot[None], app: TlApp, screen: DomainScreen) -> None:
        assert bar(screen) == "[Enter] Open record"

    scenario(answerer, answerer_steps)
    scenario(reader, reader_steps)


def test_the_bar_follows_the_highlighted_row_and_shows_nothing_the_server_did_not_offer() -> None:
    client = world()
    client.set_actions(RFI1, ("AnswerTechnical", "Answer"), ("MadeUpCommand", "Do magic"))
    client.set_actions(RFI2, ("CloseTechnical", "Close"))

    async def steps(pilot: Pilot[None], app: TlApp, screen: DomainScreen) -> None:
        assert bar(screen) == "[a] Answer  [Enter] Open record"
        await pilot.press("down")
        await settle(pilot)
        assert bar(screen) == "[c] Close  [Enter] Open record"
        await pilot.press("a")  # not offered on this row
        await settle(pilot)
        assert client.correspondence_commands == []

    scenario(client, steps)


def test_a_failed_read_of_the_actions_leaves_no_actions_of_the_previous_row() -> None:
    client = world()
    client.set_actions(RFI1, *ANSWERER)
    real = client.allowed_actions

    def flaky(record_id: str) -> RecordActions:
        if record_id == RFI2:
            raise RecordNotFoundError(f"no record {record_id!r}")
        return real(record_id)

    client.allowed_actions = flaky  # type: ignore[method-assign]

    async def steps(pilot: Pilot[None], app: TlApp, screen: DomainScreen) -> None:
        assert "[a] Answer" in bar(screen)
        await pilot.press("down")
        await settle(pilot)
        assert bar(screen) == ""
        assert status(screen).startswith("! ")
        await pilot.press("a")  # the previous row's Answer must not run on this row
        await settle(pilot)
        assert client.correspondence_commands == []

    scenario(client, steps)


def test_answer_opens_the_form_and_sends_answer_technical_with_the_typed_text() -> None:
    client = world()
    client.set_actions(RFI1, *ANSWERER)

    async def steps(pilot: Pilot[None], app: TlApp, screen: DomainScreen) -> None:
        await pilot.press("a")
        await settle(pilot)
        assert not isinstance(app.screen, DomainScreen)  # the form is up
        await pilot.press(*"Use 600 mm")
        await pilot.press("ctrl+s")
        await settle(pilot)
        assert isinstance(app.screen, DomainScreen)
        [(name, cmd)] = client.correspondence_commands
        assert name == "AnswerTechnical" and isinstance(cmd, AnswerTechnical)
        assert cmd.answer == "Use 600 mm" and cmd.stream_id == RFI1
        assert (cmd.actor, cmd.source, cmd.scope) == ("user:kim", "tui", "project:P123")
        assert not status(screen).startswith("! ")

    scenario(client, steps)


def test_esc_on_the_form_sends_nothing() -> None:
    client = world()
    client.set_actions(RFI1, *ANSWERER)

    async def steps(pilot: Pilot[None], app: TlApp, screen: DomainScreen) -> None:
        await pilot.press("a", "x", "escape")
        await settle(pilot)
        assert isinstance(app.screen, DomainScreen) and client.correspondence_commands == []

    scenario(client, steps)


def test_a_refusal_from_the_command_lands_in_the_status_line() -> None:
    client = world(controller=False)  # Escalate is a controller command: the client refuses it
    client.set_actions(RFI1, ("EscalateTechnical", "Escalate"))

    async def steps(pilot: Pilot[None], app: TlApp, screen: DomainScreen) -> None:
        assert "[e] Escalate" in bar(screen)  # the fake offered it; the command decides
        await pilot.press("e")
        await settle(pilot)
        await pilot.press("enter")  # yes, escalate
        await settle(pilot)
        assert isinstance(app.screen, DomainScreen)
        assert status(screen).startswith("! ") and "document_controller" in status(screen)

    scenario(client, steps)


# --- on the tag register and the Commercial register ----------------------------------------


def tag_world() -> FakeClient:
    client = FakeClient()
    client.add_tag("P123", "47-FV-1001", class_code="ControlValve", title="Feed gas control")
    client.add_tag("P123", "47-FV-1002", class_code="ControlValve", title="Vent valve")
    return client


def test_the_tag_bar_is_server_fed_and_a_tag_command_runs_on_the_engineering_table() -> None:
    client = tag_world()
    tag = client.get_tag("P123", "47-FV-1001")
    client.set_actions(tag.id, ("ReclassifyTag", "Reclassify"), ("RenameTag", "Rename"))
    app = TlApp(client, scope=SCOPE, actor="user:kim")

    async def go(pilot: Pilot[None]) -> None:
        await pilot.press("f8")
        await settle(pilot)
        screen = app.screen
        assert isinstance(screen, TagRegisterScreen)
        assert bar(screen) == "[l] Reclassify  [n] Rename  [Enter] Open record"
        await pilot.press("n")
        await settle(pilot)
        assert not isinstance(app.screen, TagRegisterScreen)  # the form is up
        await pilot.press(*"47-FV-2001")
        await pilot.press("tab")
        await pilot.press(*"typo")
        await pilot.press("ctrl+s")
        await settle(pilot)
        assert isinstance(app.screen, TagRegisterScreen)
        [(module, name, cmd)] = client.module_commands
        assert (module, name) == ("engineering", "RenameTag") and isinstance(cmd, RenameTag)
        assert (cmd.stream_id, cmd.new_number, cmd.reason) == (tag.id, "47-FV-2001", "typo")
        assert (cmd.actor, cmd.source, cmd.scope) == ("user:kim", "tui", "project:P123")
        assert client.correspondence_commands == []
        assert not status(screen).startswith("! ")

    run_pilot(app, go)


def test_a_tag_that_is_offered_nothing_has_only_the_open_key() -> None:
    client = tag_world()  # no offers set: the server offers nothing

    async def go(pilot: Pilot[None]) -> None:
        await pilot.press("f8")
        await settle(pilot)
        assert bar(app.screen) == "[Enter] Open record"
        await pilot.press("l")
        await settle(pilot)
        assert client.module_commands == []

    app = TlApp(client, scope=SCOPE, actor="user:kim")
    run_pilot(app, go)


def test_the_commercial_bar_is_server_fed_and_runs_on_the_correspondence_table() -> None:
    client = world()
    for number in ("ID-P123-EW-0001", "ID-P123-CN-0001"):
        client.set_actions(number, ("ReviewCommercial", "Review"))

    async def steps(pilot: Pilot[None], app: TlApp, screen: DomainScreen) -> None:
        await pilot.press("2")
        await settle(pilot)
        assert bar(screen) == "[w] Review  [Enter] Open record"
        await pilot.press("w")
        await settle(pilot)
        await pilot.press("enter")  # yes, approve
        await settle(pilot)
        [(name, cmd)] = client.correspondence_commands
        assert name == "ReviewCommercial" and isinstance(cmd, ReviewCommercial)
        assert cmd.stream_id in ("ID-P123-EW-0001", "ID-P123-CN-0001")
        assert (cmd.actor, cmd.source, cmd.scope) == ("user:kim", "tui", "project:P123")
        assert client.module_commands == []

    scenario(client, steps)
