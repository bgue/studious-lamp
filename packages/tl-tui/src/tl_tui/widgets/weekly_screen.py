"""The weekly cycle, steps 1 to 3 (P2-I5-T06a; spec §8, skill ``tui-layout``).

Three full-size log screens share a steps line, ``1 Look-ahead  2 Constraints  3 Release  4
Commitments  5 Progress``; the keys ``1`` to ``3`` switch between them, ``4`` and ``5`` say "Not
available yet" until T06b. ``LookAheadScreen`` lists the activities of the next weeks with their
IWPs; ``ConstraintReviewScreen`` lists the open blocking constraints and waives a check-raised one
(``x``); ``ReleaseScreen`` lists the Ready IWPs and signs them off (``s``) or issues them (``i``).

The screens read through ``ClientInterface`` and send commands through ``client.awp_command`` and
``client.constraint_command``; the handlers decide what is allowed. Every command is stamped with
the signed-in actor and the scope, and sent inside ``LogScreen.attempt`` so a refusal reaches the
status line. The text is ``tl_tui.weekly_text``; no screen holds a business rule.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import TYPE_CHECKING, ClassVar

from textual.binding import Binding, BindingType
from textual.widget import Widget
from textual.widgets import Input, Static
from tl_core.constraints.commands import ClearConstraint
from tl_mod_awp.commands import IssueIwp, SignOffIwp

from tl_tui.action_ui import ENVELOPE, FormField, stamp
from tl_tui.client import ClientInterface
from tl_tui.errors import CLIENT_ERRORS, describe_error
from tl_tui.weekly_text import (
    CONSTRAINT_REVIEW_COLUMNS,
    LOOK_AHEAD_COLUMNS,
    NO_SCHEDULE,
    OPEN_STATES,
    RELEASE_COLUMNS,
    LookAheadLine,
    constraint_cells,
    constraint_panel,
    line_key,
    look_ahead_cells,
    look_ahead_lines,
    look_ahead_panel,
    look_ahead_summary,
    merge_constraints,
    release_cells,
    release_panel,
    release_summary,
    review_summary,
    waivable,
)
from tl_tui.widgets.action_form import ActionFormScreen
from tl_tui.widgets.log_screen import LogAction, LogScreen

if TYPE_CHECKING:
    from tl_api.routes.constraints import ConstraintRow
    from tl_mod_awp.iwp_counts import IwpCountRow
    from tl_mod_awp.iwp_views import IwpRow
    from tl_mod_awp.look_ahead_view import LookAheadView

#: The steps line: key and words of each step, in order.
STEPS: tuple[tuple[str, str], ...] = (
    ("1", "Look-ahead"),
    ("2", "Constraints"),
    ("3", "Release"),
    ("4", "Commitments"),
    ("5", "Progress"),
)
#: The steps that arrive in T06b; their key says so and changes nothing.
LATER_STEPS = frozenset({"4", "5"})
NOT_AVAILABLE = "Not available yet"
LOG_NAME = "Weekly cycle"
LOOK_AHEAD_WEEKS = 4
REASON = "reason"


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
        """``1`` to ``3`` show that step (the same screen again does nothing); ``4`` and ``5``
        say that they are not available yet."""
        if isinstance(self.focused, Input):
            return  # the key is text
        if key in LATER_STEPS:
            self.say(NOT_AVAILABLE)
            return
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
    HELP_KEYS: ClassVar[tuple[tuple[str, str], ...]] = (
        ("1 to 5", "Show that step (4 and 5 are not available yet)"),
    )

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
        ("1 to 5", "Show that step (4 and 5 are not available yet)"),
    )

    def columns(self) -> Sequence[str]:
        return CONSTRAINT_REVIEW_COLUMNS

    def drop_order(self) -> Sequence[str]:
        return ("Source", "Phase", "Owner")

    def load_rows(self) -> Sequence[ConstraintRow]:
        opened = self.client.list_constraints(self.project, blocking=True, state="Open")
        assigned = self.client.list_constraints(self.project, blocking=True, state="Assigned")
        cleared = self.client.list_constraints(self.project, blocking=True, state="Cleared")
        return merge_constraints(opened.rows, assigned.rows, cleared.rows)

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
        ("1 to 5", "Show that step (4 and 5 are not available yet)"),
    )

    def __init__(self, client: ClientInterface, project: str) -> None:
        super().__init__(client, project)
        self.counts: dict[str, IwpCountRow] = {}  # by IWP number, as the last read gave them

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
        try:
            detail = self.client.get_iwp(self.project, row.number)
        except CLIENT_ERRORS as exc:
            self.say(describe_error(exc), error=True)
            return release_panel(row, None)
        return release_panel(row, len(detail.signoffs))

    def actions_for(self, row: IwpRow) -> Sequence[LogAction]:
        return [
            LogAction("s", "Sign off", lambda: self._sign_off(row)),
            LogAction("i", "Issue", lambda: self._issue(row)),
        ]

    def summary_text(self) -> str:
        return release_summary(len(self.shown))

    def _sign_off(self, row: IwpRow) -> None:
        digest = self.client.get_iwp_hash(self.project, row.number)
        cmd = stamp(
            SignOffIwp(iwp=row.id, record_hash=digest.record_hash, **ENVELOPE),
            actor=self._actor(),
            scope=self._scope(),
        )
        self.client.awp_command("SignOffIwp", cmd)

    def _issue(self, row: IwpRow) -> None:
        digest = self.client.get_iwp_hash(self.project, row.number)
        cmd = stamp(
            IssueIwp(iwp=row.id, foreman=row.foreman, record_hash=digest.record_hash, **ENVELOPE),
            actor=self._actor(),
            scope=self._scope(),
        )
        self.client.awp_command("IssueIwp", cmd)


STEP_SCREENS: dict[str, type[WeeklyScreen]] = {
    "1": LookAheadScreen,
    "2": ConstraintReviewScreen,
    "3": ReleaseScreen,
}
