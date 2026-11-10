"""The weekly cycle, steps 1 to 3 (P2-I5-T06a): the palette entry, the three log screens, their
keys and their commands, through the Textual pilot over ``FakeClient``."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import replace
from typing import Any

from fakes import SCOPE, FakeClient
from fakes_iwp import seed_iwp
from fakes_week import PROJECT, seed_week
from helpers import run_pilot, screen_text, settle, static_of
from textual.pilot import Pilot
from textual.widgets import Input
from tl_api.routes.awp_progress import IwpHash
from tl_core.auth.errors import ForbiddenError
from tl_core.constraints.commands import ClearConstraint
from tl_mod_awp.commands import IssueIwp, SignOffIwp
from tl_mod_awp.look_ahead_view import LookAheadItem, LookAheadIwp, LookAheadView
from tl_mod_schedule.lookahead import LookAheadRow
from tl_tui.app import TlApp
from tl_tui.commands import APP_COMMANDS
from tl_tui.errors import describe_error
from tl_tui.weekly_text import review_summary
from tl_tui.widgets.action_form import ActionFormScreen
from tl_tui.widgets.weekly_screen import (
    STEPS,
    CommitmentsScreen,
    ConstraintReviewScreen,
    LookAheadScreen,
    ProgressScreen,
    ReleaseScreen,
    steps_line,
)

SIZE = (170, 44)
HASH = "ab" * 32  # a record hash, 64 hex digits
Step = Callable[[Pilot[Any]], Awaitable[None]]


def make_app() -> tuple[TlApp, FakeClient]:
    client = FakeClient()
    seed_week(client)
    seed_iwp(client)
    client.seed_schedule(PROJECT)
    return TlApp(client, scope=SCOPE, actor="user:kim"), client


def run(app: TlApp, steps: Step) -> None:
    async def go(pilot: Pilot[Any]) -> None:
        await settle(pilot)
        await steps(pilot)

    run_pilot(app, go, size=SIZE)


async def press(pilot: Pilot[Any], *keys: str) -> None:
    for key in keys:
        await pilot.press(key)
        await settle(pilot)


def status_of(app: TlApp) -> str:
    return static_of(app.screen, "#log-status")


def two_of_three_view() -> LookAheadView:
    """One activity with one IWP whose readiness is 2 of 3 checks."""
    activity = LookAheadRow(
        activity_id="A1230",
        name="Pipe rack erection",
        wbs_path="1.2",
        status="Not Started",
        phase="starting",
        early_start="2026-11-09",
        early_finish="2026-11-20",
        total_float_days=3.0,
        critical=True,
        percent_complete=0.0,
    )
    iwp = LookAheadIwp(
        id="rec-iwp-week",
        number=f"{PROJECT}-IWP-PIP-0001",
        state="Ready",
        planned_start="2026-12-01",
        need_by="2026-11-17",
        evaluated=True,
        ready=False,
        checks_ok=2,
        checks_total=3,
        open_blocking=0,
    )
    return LookAheadView(
        snapshot_key="MAIN@1",
        data_date="2026-11-02",
        window_start="2026-11-02",
        window_end="2026-11-30",
        weeks=4,
        lead_weeks=2,
        counts={"starting": 1, "in_progress": 0, "late_start": 0, "total": 1, "critical": 1},
        items=(LookAheadItem(row=activity, iwps=(iwp,)),),
    )


def check_raised(client: FakeClient) -> Any:
    """The first blocking Open constraint, made check-raised; the other rows stay as they are."""
    rows = client.list_constraints(PROJECT).rows
    target = next(r for r in rows if r.severity == "blocking" and r.state == "Open")
    checked = replace(target, source="check")
    client.load_constraints(PROJECT, [checked if r.id == target.id else r for r in rows])
    return checked


# --- the palette and the steps line -------------------------------------------------------------


def test_the_palette_opens_step_one_and_esc_returns() -> None:
    app, _ = make_app()
    seen: dict[str, Any] = {}
    label = next(c.label for c in APP_COMMANDS if c.id == "week")

    async def steps(pilot: Pilot[Any]) -> None:
        base = len(app.screen_stack)
        app.action_palette()
        await settle(pilot)
        app.screen.query_one("#palette-input", Input).value = label
        await settle(pilot)
        await press(pilot, "enter")
        seen["screen"] = app.screen
        seen["steps"] = static_of(app.screen, "#weekly-steps")
        await press(pilot, "escape")
        seen["back"] = len(app.screen_stack) == base

    run(app, steps)
    assert isinstance(seen["screen"], LookAheadScreen)
    assert (
        seen["steps"]
        == steps_line()
        == ("1 Look-ahead  2 Constraints  3 Release  4 Commitments  5 Progress")
    )
    assert [key for key, _ in STEPS] == ["1", "2", "3", "4", "5"]
    assert seen["back"], "Esc did not return from the weekly cycle"


# --- step 1: the look-ahead ----------------------------------------------------------------------


def test_step_one_shows_the_activity_and_its_iwp_with_two_of_three() -> None:
    app, client = make_app()
    client.load_look_ahead(PROJECT, two_of_three_view())
    seen: dict[str, Any] = {}

    async def steps(pilot: Pilot[Any]) -> None:
        app.action_week()
        await settle(pilot)
        seen["screen"] = app.screen
        seen["text"] = screen_text(app)

    run(app, steps)
    assert isinstance(seen["screen"], LookAheadScreen)
    assert "A1230/" + f"{PROJECT}-IWP-PIP-0001" in seen["text"]
    assert "2/3" in seen["text"]
    assert "1 activity, 1 IWP" in seen["text"]


def test_step_one_without_a_published_schedule_says_so() -> None:
    app, client = make_app()
    client.load_look_ahead(PROJECT, two_of_three_view())
    client._schedules.clear()  # no schedule of the project: none has a published snapshot
    seen: dict[str, Any] = {}

    async def steps(pilot: Pilot[Any]) -> None:
        app.action_week()
        await settle(pilot)
        seen["status"] = status_of(app)

    run(app, steps)
    assert seen["status"] == "No published schedule yet."


# --- step 2: the constraint review ---------------------------------------------------------------


def test_step_two_waives_a_check_raised_constraint_with_one_reason() -> None:
    app, client = make_app()
    target = check_raised(client)
    seen: dict[str, Any] = {}

    async def steps(pilot: Pilot[Any]) -> None:
        app.action_week()
        await settle(pilot)
        await press(pilot, "2")
        seen["screen"] = app.screen
        seen["listed"] = target.key in screen_text(app)
        await press(pilot, "x")
        seen["form"] = app.screen
        app.screen.query_one("#field-reason", Input).value = "Checked on site"
        await press(pilot, "ctrl+s")

    run(app, steps)
    assert isinstance(seen["screen"], ConstraintReviewScreen)
    assert seen["listed"], "the blocking check-raised constraint is not listed"
    assert isinstance(seen["form"], ActionFormScreen)
    assert len(client.sent_commands) == 1
    name, cmd = client.sent_commands[0]
    assert name == "ClearConstraint"
    assert isinstance(cmd, ClearConstraint)
    assert cmd.constraint == target.id
    assert cmd.reason == "Checked on site"
    assert cmd.actor == "user:kim"


def test_step_two_does_not_send_an_empty_reason() -> None:
    app, client = make_app()
    check_raised(client)
    seen: dict[str, Any] = {}

    async def steps(pilot: Pilot[Any]) -> None:
        app.action_week()
        await settle(pilot)
        await press(pilot, "2", "x", "ctrl+s")
        seen["still_asking"] = isinstance(app.screen, ActionFormScreen)
        await press(pilot, "escape")

    run(app, steps)
    assert seen["still_asking"]
    assert client.sent_commands == []


def test_a_refusal_of_the_clear_lands_on_the_status_line() -> None:
    app, client = make_app()
    check_raised(client)
    refusal = ForbiddenError("the planner may not clear this constraint")
    client.command_error = refusal
    seen: dict[str, Any] = {}

    async def steps(pilot: Pilot[Any]) -> None:
        app.action_week()
        await settle(pilot)
        await press(pilot, "2", "x")
        app.screen.query_one("#field-reason", Input).value = "Checked on site"
        await press(pilot, "ctrl+s")
        seen["screen"] = app.screen
        seen["status"] = status_of(app)

    run(app, steps)
    assert isinstance(seen["screen"], ConstraintReviewScreen)
    assert seen["status"] == "! " + describe_error(refusal)


# --- step 3: the release -------------------------------------------------------------------------


def test_step_three_lists_the_ready_iwps_and_signs_off_and_issues_with_the_hash() -> None:
    app, client = make_app()
    ready = client.list_iwps(PROJECT, state="Ready")
    assert len(ready) == 1
    client.load_hashes(
        PROJECT, {ready[0].number: IwpHash(number=ready[0].number, record_hash=HASH)}
    )
    seen: dict[str, Any] = {}

    async def steps(pilot: Pilot[Any]) -> None:
        app.action_week()
        await settle(pilot)
        await press(pilot, "3")
        seen["screen"] = app.screen
        seen["text"] = screen_text(app)
        await press(pilot, "s")
        await press(pilot, "i")

    run(app, steps)
    assert isinstance(seen["screen"], ReleaseScreen)
    assert ready[0].number in seen["text"]
    assert "signoffs" in seen["text"] and "of 2" in seen["text"]
    assert [name for name, _ in client.sent_commands] == ["SignOffIwp", "IssueIwp"]
    sign_off = client.sent_commands[0][1]
    issue = client.sent_commands[1][1]
    assert isinstance(sign_off, SignOffIwp) and isinstance(issue, IssueIwp)
    assert sign_off.iwp == ready[0].id and sign_off.record_hash == HASH
    assert issue.iwp == ready[0].id and issue.foreman == ready[0].foreman
    assert issue.record_hash == HASH and sign_off.actor == "user:kim"


def test_step_two_lists_a_waived_constraint_as_waived_and_does_not_count_it() -> None:
    app, client = make_app()
    target = check_raised(client)
    # P2-I5-T06b (review F1): an ordinary cleared blocking constraint (not waived) is not listed
    plain = replace(target, id="con-ordinary", key="CON-ORDINARY", source="manual", state="Cleared")
    client.load_constraints(
        PROJECT,
        [
            replace(r, state="Cleared", waived=True) if r.id == target.id else r
            for r in client.list_constraints(PROJECT).rows
        ]
        + [plain],
    )
    open_now = [
        r
        for r in client.list_constraints(PROJECT, blocking=True).rows
        if r.state in ("Open", "Assigned")
    ]
    seen: dict[str, Any] = {}

    async def steps(pilot: Pilot[Any]) -> None:
        app.action_week()
        await settle(pilot)
        await press(pilot, "2")
        seen["text"] = screen_text(app)

    run(app, steps)
    assert target.key in seen["text"]
    assert "waived" in seen["text"]
    assert plain.key not in seen["text"], "an ordinary cleared constraint lingers as Cleared"
    assert review_summary(len(open_now)) in seen["text"]
    assert client.sent_commands == []


def test_step_three_panel_shows_the_signoff_count_of_the_highlighted_iwp() -> None:
    app, client = make_app()
    ready = client.list_iwps(PROJECT, state="Ready")[0]
    detail = client.get_iwp(PROJECT, ready.number)
    client._iwps[PROJECT] = [
        d.model_copy(update={"signoffs": [{"by": "user:sue"}]}) if d.number == ready.number else d
        for d in client._iwps[PROJECT]
    ]
    assert detail.signoffs == []
    seen: dict[str, Any] = {}

    async def steps(pilot: Pilot[Any]) -> None:
        app.action_week()
        await settle(pilot)
        await press(pilot, "3")
        seen["text"] = screen_text(app)

    run(app, steps)
    assert "signoffs 1 of 2" in seen["text"]
    assert "Sign-offs" not in seen["text"], "the sign-off count is in the panel, not a column"


# --- the keys and the ids -------------------------------------------------------------------------


def test_steps_four_and_five_open_their_screens() -> None:
    """P2-I5-T06b: keys 4 and 5 show the commitments and the progress (were "Not available yet")."""
    app, _ = make_app()
    seen: dict[str, Any] = {}

    async def steps(pilot: Pilot[Any]) -> None:
        app.action_week()
        await settle(pilot)
        await press(pilot, "4")
        seen["four"] = app.screen
        await press(pilot, "5")
        seen["five"] = app.screen

    run(app, steps)
    assert isinstance(seen["four"], CommitmentsScreen)
    assert isinstance(seen["five"], ProgressScreen)


def test_no_screen_text_holds_a_record_id() -> None:
    app, client = make_app()
    client.load_look_ahead(PROJECT, two_of_three_view())
    check_raised(client)
    client.load_hashes(
        PROJECT,
        {f"{PROJECT}-IWP-PIP-0002": IwpHash(number=f"{PROJECT}-IWP-PIP-0002", record_hash=HASH)},
    )
    ids = {r.id for r in client.list_constraints(PROJECT).rows}
    ids |= {r.id for r in client.list_iwps(PROJECT)}
    ids.add("rec-iwp-week")
    texts: dict[str, str] = {}

    async def steps(pilot: Pilot[Any]) -> None:
        app.action_week()
        await settle(pilot)
        texts["1"] = screen_text(app)
        await press(pilot, "2")
        texts["2"] = screen_text(app)
        await press(pilot, "3")
        texts["3"] = screen_text(app)

    run(app, steps)
    for step, text in texts.items():
        for record_id in ids:
            assert record_id not in text, f"step {step} shows the record id {record_id}"
