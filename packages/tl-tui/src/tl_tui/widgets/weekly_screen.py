"""The weekly cycle, steps 1 to 5 (P2-I5-T06a and T06b; spec §8, skill ``tui-layout``).

Five full-size log screens share a steps line, ``1 Look-ahead  2 Constraints  3 Release  4
Commitments  5 Progress``; the keys ``1`` to ``5`` switch between them. ``LookAheadScreen`` lists
the activities of the next weeks with their IWPs; ``ConstraintReviewScreen`` lists the open
blocking constraints and waives a check-raised one (``x``); ``ReleaseScreen`` lists the Ready IWPs
and signs them off (``s``) or issues them (``i``); ``CommitmentsScreen`` lists the open week and
its commitments (``c`` commit, ``d``/``m`` done or missed, ``z`` close, ``o`` open); and
``ProgressScreen`` lists the IWPs in field work with their KPI line and starts (``w``) or completes
(``f``) field work.

The screens read through ``ClientInterface`` and send commands through ``client.awp_command`` and
``client.constraint_command``; the handlers decide what is allowed. Every command is stamped with
the signed-in actor and the scope, and sent inside ``LogScreen.attempt`` so a refusal reaches the
status line. The text is ``tl_tui.weekly_text``; no screen holds a business rule.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import date
from typing import TYPE_CHECKING, ClassVar, Literal

from textual.binding import Binding, BindingType
from textual.widget import Widget
from textual.widgets import Input, Static
from tl_core.constraints.commands import ClearConstraint
from tl_core.services.errors import RecordNotFoundError
from tl_mod_awp.commands import (
    CloseWeek,
    CommitIwpToWeek,
    CompleteIwpField,
    IssueIwp,
    OpenWeeklyPlan,
    RecordWeekOutcome,
    SignOffIwp,
    StartIwpWork,
)
from tl_mod_awp.names import IWP_IN_PROGRESS, IWP_ISSUED

from tl_tui.action_ui import ENVELOPE, FormField, stamp
from tl_tui.client import ClientInterface
from tl_tui.errors import CLIENT_ERRORS, describe_error
from tl_tui.weekly_text import (
    CLOSED_WEEK,
    COMMITMENT_COLUMNS,
    CONSTRAINT_REVIEW_COLUMNS,
    LOOK_AHEAD_COLUMNS,
    NO_OPEN_WEEK,
    NO_SCHEDULE,
    OPEN_STATES,
    PROGRESS_COLUMNS,
    PROGRESS_STATES,
    RELEASE_COLUMNS,
    LookAheadLine,
    PlanLine,
    commitment_panel,
    commitment_summary,
    constraint_cells,
    constraint_panel,
    line_key,
    look_ahead_cells,
    look_ahead_lines,
    look_ahead_panel,
    look_ahead_summary,
    merge_constraints,
    plan_line_cells,
    plan_line_key,
    plan_lines,
    plan_panel,
    progress_cells,
    progress_panel,
    progress_summary,
    reason_labels,
    release_cells,
    release_panel,
    release_summary,
    review_summary,
    waivable,
)
from tl_tui.widgets.action_form import ActionFormScreen
from tl_tui.widgets.log_screen import LogAction, LogScreen

if TYPE_CHECKING:
    from tl_api.routes.awp_progress import IwpProgress
    from tl_api.routes.constraints import ConstraintRow
    from tl_mod_awp.iwp_counts import IwpCountRow
    from tl_mod_awp.iwp_views import IwpRow
    from tl_mod_awp.kpis import KpiTile
    from tl_mod_awp.look_ahead_view import LookAheadView
    from tl_mod_awp.week_views import CommitmentRow, WeekDetail

#: The steps line: key and words of each step, in order.
STEPS: tuple[tuple[str, str], ...] = (
    ("1", "Look-ahead"),
    ("2", "Constraints"),
    ("3", "Release"),
    ("4", "Commitments"),
    ("5", "Progress"),
)
LOG_NAME = "Weekly cycle"
LOOK_AHEAD_WEEKS = 4
REASON = "reason"
HOURS = "hours"
FOREMAN = "foreman"
IWP_NUMBER = "iwp"


def steps_line() -> str:
    """``1 Look-ahead  2 Constraints  3 Release  4 Commitments  5 Progress``."""
    return "  ".join(f"{key} {label}" for key, label in STEPS)


class WeeklyScreen[Row](LogScreen[Row]):
    """The shared frame of the three steps: the steps line, the keys 1 to 5, the actor."""

    LOG_NAME: ClassVar[str] = LOG_NAME
    BINDINGS: ClassVar[list[BindingType]] = [
        Binding("1", "step('1')", show=False),
        Binding("2", "step('2')", show=False),
        Binding("3", "step('3')", show=False),
        Binding("4", "step('4')", show=False),
        Binding("5", "step('5')", show=False),
    ]

    def __init__(self, client: ClientInterface, project: str) -> None:
        super().__init__()
        self.client = client
        self.project = project

    def log_project(self) -> str:
        return self.project

    def on_mount(self) -> None:
        """The steps line goes above the breadcrumb (the log's layout is not changed)."""
        crumb = self.query_one("#log-crumb", Static)
        holder = crumb.parent
        if isinstance(holder, Widget):
            holder.mount(Static(steps_line(), markup=False, id="weekly-steps"), before=crumb)

    def open_row(self, row: Row) -> None:
        """Enter opens nothing on these steps: the actions are the keys."""

    def action_step(self, key: str) -> None:
        """``1`` to ``5`` show that step (the same screen again does nothing)."""
        if isinstance(self.focused, Input):
            return  # the key is text
        target = STEP_SCREENS[key]
        if isinstance(self, target):
            return
        self.app.switch_screen(target(self.client, self.project))

    def _actor(self) -> str:
        return str(getattr(self.app, "actor", "user:dev"))

    def _scope(self) -> str:
        return str(getattr(self.app, "scope", ""))


class LookAheadScreen(WeeklyScreen[LookAheadLine]):
    """Step 1: the activities of the next weeks, each with its IWPs and their readiness."""

    KEY_HINTS: ClassVar[str] = "/ filter  1 to 5 steps  F5 reload  Esc back"
    KEY_CELLS: ClassVar[tuple[str, ...]] = ("/ filter", "2 constraints", "3 release")
    HELP_KEYS: ClassVar[tuple[tuple[str, str], ...]] = (("1 to 5", "Show that step"),)

    def __init__(self, client: ClientInterface, project: str) -> None:
        super().__init__(client, project)
        self.view: LookAheadView | None = None  # None: no schedule has a published snapshot

    def columns(self) -> Sequence[str]:
        return LOOK_AHEAD_COLUMNS

    def drop_order(self) -> Sequence[str]:
        return ("Phase", "Start")

    def load_rows(self) -> Sequence[LookAheadLine]:
        schedule = next(
            (
                s
                for s in self.client.list_schedules(self.project)
                if s.current_snapshot_number is not None
            ),
            None,
        )
        if schedule is None:
            self.view = None
            return []
        self.view = self.client.get_awp_look_ahead(
            self.project, schedule.code, weeks=LOOK_AHEAD_WEEKS
        )
        return look_ahead_lines(self.view)

    def row_key(self, row: LookAheadLine) -> str:
        return line_key(row)

    def row_cells(self, row: LookAheadLine) -> Sequence[str]:
        return look_ahead_cells(row)

    def row_record(self, row: LookAheadLine) -> tuple[str, str]:
        return (line_key(row), row.item.row.name)

    def panel_text(self, row: LookAheadLine | None) -> str:
        if row is None:
            return "No activity matches."
        return look_ahead_panel(row)

    def actions_for(self, row: LookAheadLine) -> Sequence[LogAction]:
        """Nothing is written on the look-ahead."""
        return []

    def summary_text(self) -> str:
        if self.view is None:
            return NO_SCHEDULE
        return look_ahead_summary(self.view)


class ConstraintReviewScreen(WeeklyScreen["ConstraintRow"]):
    """Step 2: the open blocking constraints (Open, Assigned) and the waived ones (Cleared, so a
    waived row shows ``waived``); ``x`` waives a check-raised open one."""

    KEY_CELLS: ClassVar[tuple[str, ...]] = ("/ filter", "x waive", "1 look-ahead", "3 release")
    HELP_KEYS: ClassVar[tuple[tuple[str, str], ...]] = (
        ("x", "Waive the highlighted check-raised constraint: asks for a reason"),
        ("1 to 5", "Show that step"),
    )

    def columns(self) -> Sequence[str]:
        return CONSTRAINT_REVIEW_COLUMNS

    def drop_order(self) -> Sequence[str]:
        return ("Source", "Phase", "Owner")

    def load_rows(self) -> Sequence[ConstraintRow]:
        opened = self.client.list_constraints(self.project, blocking=True, state="Open")
        assigned = self.client.list_constraints(self.project, blocking=True, state="Assigned")
        cleared = self.client.list_constraints(self.project, blocking=True, state="Cleared")
        waived = [row for row in cleared.rows if row.waived]  # ordinary cleared ones do not linger
        return merge_constraints(opened.rows, assigned.rows, waived)

    def row_key(self, row: ConstraintRow) -> str:
        return row.key

    def row_cells(self, row: ConstraintRow) -> Sequence[str]:
        return constraint_cells(row)

    def row_record(self, row: ConstraintRow) -> tuple[str, str]:
        return (row.key, row.description or row.subject_key)

    def panel_text(self, row: ConstraintRow | None) -> str:
        if row is None:
            return "No constraint matches."
        return constraint_panel(row)

    def actions_for(self, row: ConstraintRow) -> Sequence[LogAction]:
        if not waivable(row):
            return []
        return [LogAction("x", "Waive", lambda: self._waive(row))]

    def summary_text(self) -> str:
        return review_summary(sum(1 for row in self.shown if row.state in OPEN_STATES))

    def _waive(self, row: ConstraintRow) -> None:
        """Ask for the reason (one required line), then send the clear; an empty reason is not
        sent (the form keeps asking)."""
        fields = (FormField(REASON, "Reason", kind="line", required=True),)

        def answered(values: dict[str, str] | None) -> None:
            if values is None:
                return
            reason = values[REASON]
            self.attempt(lambda: self._clear(row, reason))

        self.app.push_screen(ActionFormScreen(f"Waive {row.key}", fields), answered)

    def _clear(self, row: ConstraintRow, reason: str) -> None:
        cmd = stamp(
            ClearConstraint(constraint=row.id, reason=reason, **ENVELOPE),
            actor=self._actor(),
            scope=self._scope(),
        )
        self.client.constraint_command("ClearConstraint", cmd)


class ReleaseScreen(WeeklyScreen["IwpRow"]):
    """Step 3: the Ready IWPs; ``s`` signs one off, ``i`` issues it to its foreman."""

    KEY_CELLS: ClassVar[tuple[str, ...]] = ("/ filter", "s sign off", "i issue", "2 constraints")
    HELP_KEYS: ClassVar[tuple[tuple[str, str], ...]] = (
        ("s", "Sign off the highlighted Ready IWP"),
        ("i", "Issue the highlighted IWP to its foreman"),
        ("1 to 5", "Show that step"),
    )

    def __init__(self, client: ClientInterface, project: str) -> None:
        super().__init__(client, project)
        self.counts: dict[str, IwpCountRow] = {}  # by IWP number, as the last read gave them
        self.hashes: dict[str, str] = {}  # record hash of each IWP as its panel was shown

    def columns(self) -> Sequence[str]:
        return RELEASE_COLUMNS

    def drop_order(self) -> Sequence[str]:
        return ("Foreman",)

    def load_rows(self) -> Sequence[IwpRow]:
        self.counts = {row.number: row for row in self.client.list_iwp_counts(self.project)}
        return self.client.list_iwps(self.project, state="Ready")

    def row_key(self, row: IwpRow) -> str:
        return row.number

    def row_cells(self, row: IwpRow) -> Sequence[str]:
        return release_cells(row, self.counts.get(row.number))

    def row_record(self, row: IwpRow) -> tuple[str, str]:
        return (row.number, row.title)

    def panel_text(self, row: IwpRow | None) -> str:
        """The highlighted IWP in full; one ``get_iwp`` for it gives the sign-off count."""
        if row is None:
            return "No Ready IWP."
        self.hashes.pop(row.number, None)
        try:
            detail = self.client.get_iwp(self.project, row.number)
        except CLIENT_ERRORS as exc:
            self.say(describe_error(exc), error=True)
            return release_panel(row, None)
        try:
            # what the person reads is what a key signs: a later edit makes the command stale
            self.hashes[row.number] = self.client.get_iwp_hash(self.project, row.number).record_hash
        except CLIENT_ERRORS:
            pass  # the key reads it and reports the error
        return release_panel(row, len(detail.signoffs))

    def _shown_hash(self, row: IwpRow) -> str:
        """The hash fetched when the panel showed ``row``; read now only if no panel showed it."""
        held = self.hashes.get(row.number)
        if held is not None:
            return held
        return self.client.get_iwp_hash(self.project, row.number).record_hash

    def actions_for(self, row: IwpRow) -> Sequence[LogAction]:
        return [
            LogAction("s", "Sign off", lambda: self._sign_off(row)),
            LogAction("i", "Issue", lambda: self._issue(row)),
        ]

    def summary_text(self) -> str:
        return release_summary(len(self.shown))

    def _sign_off(self, row: IwpRow) -> None:
        cmd = stamp(
            SignOffIwp(iwp=row.id, record_hash=self._shown_hash(row), **ENVELOPE),
            actor=self._actor(),
            scope=self._scope(),
        )
        self.client.awp_command("SignOffIwp", cmd)

    def _issue(self, row: IwpRow) -> None:
        cmd = stamp(
            IssueIwp(
                iwp=row.id, foreman=row.foreman, record_hash=self._shown_hash(row), **ENVELOPE
            ),
            actor=self._actor(),
            scope=self._scope(),
        )
        self.client.awp_command("IssueIwp", cmd)


class CommitmentsScreen(WeeklyScreen["PlanLine"]):
    """Step 4: the open week (the latest week, read-only, when none is open) and its commitments.

    ``c`` commits an Issued or In progress IWP to the week; ``d`` and ``m`` record a commitment done
    or missed (``m`` asks the reason); ``z`` closes the week after a confirm; ``o`` opens this week
    when no week is open. A closed week offers no action; its PPC is in the summary."""

    BINDINGS: ClassVar[list[BindingType]] = [
        Binding("o", "open_week", "Open this week", show=False),
    ]
    KEY_CELLS: ClassVar[tuple[str, ...]] = ("/ filter", "c commit", "d done", "m missed", "z close")
    HELP_KEYS: ClassVar[tuple[tuple[str, str], ...]] = (
        ("c", "Commit an Issued or In progress IWP to this week (IWP, hours, foreman)"),
        ("d", "Record the highlighted commitment done"),
        ("m", "Record the highlighted commitment missed: asks the reason"),
        ("z", "Close this week after a confirm: its PPC is written"),
        ("o", "Open this week, when no week is open"),
        ("1 to 5", "Show that step"),
    )

    def __init__(self, client: ClientInterface, project: str) -> None:
        super().__init__(client, project)
        self.plan: WeekDetail | None = None  # the open week, else the latest; None: no week

    def columns(self) -> Sequence[str]:
        return COMMITMENT_COLUMNS

    def drop_order(self) -> Sequence[str]:
        return ("Reason", "Foreman")

    def load_rows(self) -> Sequence[PlanLine]:
        weeks = self.client.list_weekly_plans(self.project)  # the latest week first
        pick = next((w for w in weeks if w.state != CLOSED_WEEK), weeks[0] if weeks else None)
        self.plan = None if pick is None else self.client.get_weekly_plan(self.project, pick.week)
        return [] if self.plan is None else plan_lines(self.plan)

    def row_key(self, row: PlanLine) -> str:
        return plan_line_key(row)

    def row_cells(self, row: PlanLine) -> Sequence[str]:
        return plan_line_cells(row)

    def row_record(self, row: PlanLine) -> tuple[str, str]:
        if row.commitment is None:
            return (row.plan.week, f"Week {row.plan.week}")
        return (row.commitment.iwp_key, row.commitment.iwp_state)

    def panel_text(self, row: PlanLine | None) -> str:
        if row is None or self.plan is None:
            return NO_OPEN_WEEK
        if row.commitment is not None:
            return commitment_panel(row.commitment)
        if self._is_open():
            return plan_panel(row.plan)
        return f"{plan_panel(row.plan)}\n{NO_OPEN_WEEK}"

    def actions_for(self, row: PlanLine) -> Sequence[LogAction]:
        if not self._is_open():
            return []
        actions = [
            LogAction("c", "Commit", self._commit),
            LogAction("z", "Close the week", self._close),
        ]
        commitment = row.commitment
        if commitment is not None:
            actions += [
                LogAction("d", "Done", lambda: self._record(commitment, "done")),
                LogAction("m", "Missed", lambda: self._missed(commitment)),
            ]
        return actions

    def summary_text(self) -> str:
        if self.plan is None:
            return NO_OPEN_WEEK
        return commitment_summary(self.plan)

    def action_open_week(self) -> None:
        """``o``: open the week of today (the handler normalises it to its Monday)."""
        if isinstance(self.focused, Input) or self._is_open():
            return  # the key is text, or a week is open already
        self.attempt(self._open_week)

    def _is_open(self) -> bool:
        return self.plan is not None and self.plan.state != CLOSED_WEEK

    def _open_week(self) -> None:
        cmd = stamp(
            OpenWeeklyPlan(week_start=date.today(), **ENVELOPE),
            actor=self._actor(),
            scope=self._scope(),
        )
        self.client.awp_command("OpenWeeklyPlan", cmd)

    def _commit(self) -> None:
        """Ask the IWP (an Issued or In progress one), the hours and the foreman, then commit."""
        plan = self.plan
        if plan is None:
            return
        iwps = [
            *self.client.list_iwps(self.project, state=IWP_ISSUED),
            *self.client.list_iwps(self.project, state=IWP_IN_PROGRESS),
        ]
        if not iwps:
            self.say("No Issued or In progress IWP to commit.")
            return
        ids = {row.number: row.id for row in iwps}
        fields = (
            FormField(IWP_NUMBER, "IWP", kind="choice", choices=tuple(ids)),
            FormField(HOURS, "Hours"),
            FormField(FOREMAN, "Foreman", required=False),
        )

        def answered(values: dict[str, str] | None) -> None:
            if values is None:
                return
            self.attempt(lambda: self._send_commit(plan, ids[values[IWP_NUMBER]], values))

        self.app.push_screen(ActionFormScreen(f"Commit to {plan.week}", fields), answered)

    def _send_commit(self, plan: WeekDetail, iwp_id: str, values: dict[str, str]) -> None:
        cmd = stamp(
            CommitIwpToWeek(
                plan_id=plan.id,
                iwp_id=iwp_id,
                committed_hours=values[HOURS],
                foreman=values[FOREMAN] or None,
                expected_version=plan.version,
                **ENVELOPE,
            ),
            actor=self._actor(),
            scope=self._scope(),
        )
        self.client.awp_command("CommitIwpToWeek", cmd)

    def _record(
        self, row: CommitmentRow, outcome: Literal["done", "missed"], reason: str | None = None
    ) -> None:
        """``RecordWeekOutcome``: done, or missed with the reason key."""
        plan = self.plan
        if plan is None:
            return
        cmd = stamp(
            RecordWeekOutcome(
                plan_id=plan.id,
                iwp_id=row.iwp_id,
                outcome=outcome,
                miss_reason=reason,
                expected_version=plan.version,
                **ENVELOPE,
            ),
            actor=self._actor(),
            scope=self._scope(),
        )
        self.client.awp_command("RecordWeekOutcome", cmd)

    def _missed(self, row: CommitmentRow) -> None:
        """Ask the miss reason (the humanized code list), then record the commitment missed."""
        labels = reason_labels(self.client.list_miss_reasons(self.project))
        if not labels:
            self.say("The miss-reason code list is empty.")
            return
        fields = (FormField(REASON, "Reason", kind="choice", choices=tuple(labels)),)

        def answered(values: dict[str, str] | None) -> None:
            if values is None:
                return
            key = labels[values[REASON]]
            self.attempt(lambda: self._record(row, "missed", key))

        self.app.push_screen(ActionFormScreen(f"Missed: {row.iwp_key}", fields), answered)

    def _close(self) -> None:
        """Confirm, then ``CloseWeek`` (it writes the PPC)."""
        plan = self.plan
        if plan is None:
            return

        def answered(values: dict[str, str] | None) -> None:
            if values is None:
                return
            self.attempt(lambda: self._send_close(plan))

        confirm = f"Close {plan.week}? Its PPC is written and the week is final."
        self.app.push_screen(ActionFormScreen(f"Close {plan.week}", (), confirm=confirm), answered)

    def _send_close(self, plan: WeekDetail) -> None:
        cmd = stamp(
            CloseWeek(plan_id=plan.id, expected_version=plan.version, **ENVELOPE),
            actor=self._actor(),
            scope=self._scope(),
        )
        self.client.awp_command("CloseWeek", cmd)


class ProgressScreen(WeeklyScreen["IwpRow"]):
    """Step 5: the IWPs in field work (Issued, In progress, Field complete), with their readiness
    and blocking counts; the KPI line of both tiles is the summary; the highlighted IWP's panel
    shows its earned progress (one read, for that row). ``w`` starts work on an Issued IWP and
    ``f`` completes field work on an In progress one."""

    KEY_CELLS: ClassVar[tuple[str, ...]] = ("/ filter", "w start work", "f complete", "3 release")
    HELP_KEYS: ClassVar[tuple[tuple[str, str], ...]] = (
        ("w", "Start work on the highlighted Issued IWP"),
        ("f", "Complete field work on the highlighted In progress IWP"),
        ("1 to 5", "Show that step"),
    )

    def __init__(self, client: ClientInterface, project: str) -> None:
        super().__init__(client, project)
        self.counts: dict[str, IwpCountRow] = {}  # by IWP number, as the last read gave them
        self.tiles: list[KpiTile] = []

    def columns(self) -> Sequence[str]:
        return PROGRESS_COLUMNS

    def drop_order(self) -> Sequence[str]:
        return ("Blocking", "Ready")

    def load_rows(self) -> Sequence[IwpRow]:
        self.counts = {row.number: row for row in self.client.list_iwp_counts(self.project)}
        self.tiles = self.client.list_kpis(self.project)
        rows = [
            row
            for state in PROGRESS_STATES
            for row in self.client.list_iwps(self.project, state=state)
        ]
        return sorted(rows, key=lambda row: row.number)

    def row_key(self, row: IwpRow) -> str:
        return row.number

    def row_cells(self, row: IwpRow) -> Sequence[str]:
        return progress_cells(row, self.counts.get(row.number))

    def row_record(self, row: IwpRow) -> tuple[str, str]:
        return (row.number, row.title)

    def panel_text(self, row: IwpRow | None) -> str:
        """The highlighted IWP in full, with its earned progress (one ``get_iwp_progress``)."""
        if row is None:
            return "No IWP in field work."
        try:
            progress: IwpProgress | None = self.client.get_iwp_progress(self.project, row.number)
        except CLIENT_ERRORS as exc:
            self.say(describe_error(exc), error=True)
            progress = None
        return progress_panel(row, progress)

    def actions_for(self, row: IwpRow) -> Sequence[LogAction]:
        if row.state == IWP_ISSUED:
            return [LogAction("w", "Start work", lambda: self._start(row))]
        if row.state == IWP_IN_PROGRESS:
            return [LogAction("f", "Complete field work", lambda: self._complete(row))]
        return []

    def summary_text(self) -> str:
        return progress_summary(self.tiles)

    def _version(self, number: str) -> int:
        """The current version of the IWP (``IwpRow`` has none): the record's, as the terminal
        reads it."""
        record = self.client.get_record(f"project:{self.project}", number)
        if record is None:
            raise RecordNotFoundError(f"no IWP {number!r}")
        return int(record["version"])

    def _start(self, row: IwpRow) -> None:
        cmd = stamp(
            StartIwpWork(iwp_id=row.id, expected_version=self._version(row.number), **ENVELOPE),
            actor=self._actor(),
            scope=self._scope(),
        )
        self.client.awp_command("StartIwpWork", cmd)

    def _complete(self, row: IwpRow) -> None:
        cmd = stamp(
            CompleteIwpField(iwp_id=row.id, expected_version=self._version(row.number), **ENVELOPE),
            actor=self._actor(),
            scope=self._scope(),
        )
        self.client.awp_command("CompleteIwpField", cmd)


STEP_SCREENS: dict[str, type[WeeklyScreen]] = {
    "1": LookAheadScreen,
    "2": ConstraintReviewScreen,
    "3": ReleaseScreen,
    "4": CommitmentsScreen,
    "5": ProgressScreen,
}
