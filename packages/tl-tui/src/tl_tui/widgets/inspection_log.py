"""The inspection log of a project and one inspection's screen (P2-INSP-T10; spec §8,
``tui-layout``).

``InspectionLogScreen`` is a full-size ``LogScreen``: the project's inspections by key, with title,
state, point, result, scheduled date, inspector and area. The panel describes the highlighted
inspection. ``s`` shows the next state, ``p`` the next point, ``m`` the inspections whose inspector
is the signed-in actor; each filter is read again from the client (the list filters). Enter opens
``InspectionScreen`` for the inspection.

``InspectionScreen`` shows one inspection in full. ``v`` verifies it (asks "are you sure"), ``r``
reinspects it (asks an optional date), ``x`` cancels it (asks a reason). A key is shown and taken
only in the states ``tl_mod_quality.actions.RULES`` offers the command in. The command goes through
the client's ``quality_command`` with the signed-in actor, the project's scope and the record's
version; a refusal is the status line, then the inspection is read again. Scheduling and recording
answers stay on the CLI until the runner screen (T11).
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable, Iterable, Sequence
from typing import Any, ClassVar

from textual.app import ComposeResult
from textual.binding import Binding, BindingType
from textual.containers import Vertical, VerticalScroll
from textual.screen import ModalScreen
from textual.widgets import Input, Static
from tl_mod_quality.actions import states_for
from tl_mod_quality.commands import CancelInspection, ReinspectInspection, VerifyInspection
from tl_mod_quality.insp_views import InspectionDetail, InspectionRow
from tl_mod_quality.names import INSPECTION, POINTS

from tl_tui.action_ui import FormField
from tl_tui.client import ClientInterface
from tl_tui.display import humanize, mode_of
from tl_tui.errors import CLIENT_ERRORS, describe_error
from tl_tui.inspection_text import (
    INSPECTION_COLUMNS,
    INSPECTION_DROP,
    STATES,
    inspection_cells,
    inspection_count,
    inspection_page,
    inspection_summary,
)
from tl_tui.layout import Adaptive, Page, Panel, render
from tl_tui.widgets.action_form import ActionFormScreen
from tl_tui.widgets.log_screen import LogAction, LogScreen

VERIFY = "VerifyInspection"
REINSPECT = "ReinspectInspection"
CANCEL = "CancelInspection"


def _next_value(current: str | None, values: Iterable[str]) -> str | None:
    """The next filter value: all (``None``), then each value in order, then all again."""
    options: list[str | None] = [None, *values]
    index = options.index(current) if current in options else 0
    return options[(index + 1) % len(options)]


class InspectionLogScreen(LogScreen[InspectionRow]):
    """The inspections of ``project`` (the id, not the scope)."""

    LOG_NAME: ClassVar[str] = "Inspections"
    # every key the log has, in one text (the walking tests read it); the keys row shows KEY_CELLS
    KEY_HINTS: ClassVar[str] = "/ filter  s state  p point  m mine  F5 reload  Esc back"
    KEY_CELLS: ClassVar[tuple[str, ...]] = ("/ filter", "s state", "p point", "m mine")
    HELP_KEYS: ClassVar[tuple[tuple[str, str], ...]] = (
        ("s", "Show the next state: all, then each state"),
        ("p", "Show the next point: all, then hold, witness, review and surveillance"),
        ("m", "Show only the inspections of your own inspector name (again: all)"),
    )

    BINDINGS: ClassVar[list[BindingType]] = [
        Binding("s", "state", "State", show=False),
        Binding("p", "point", "Point", show=False),
        Binding("m", "mine", "Mine", show=False),
    ]

    def __init__(self, client: ClientInterface, project: str) -> None:
        super().__init__()
        self.client = client
        self.project = project
        self.state_filter: str | None = None
        self.point_filter: str | None = None
        self.mine = False  # True: only the inspections whose inspector is the signed-in actor
        self.total = 0  # the page total, as last read

    # --- the log's hooks -----------------------------------------------------------------

    def log_project(self) -> str:
        return self.project

    def columns(self) -> Sequence[str]:
        return INSPECTION_COLUMNS

    def drop_order(self) -> Sequence[str]:
        return INSPECTION_DROP

    def load_rows(self) -> Sequence[InspectionRow]:
        """The filters go to the list (state, point, inspector); the summary counts the rows."""
        page = self.client.list_inspections(
            self.project,
            state=self.state_filter,
            point=self.point_filter,
            inspector=self._actor() if self.mine else None,
        )
        self.total = page.total
        return page.rows

    def row_key(self, row: InspectionRow) -> str:
        return row.key

    def row_cells(self, row: InspectionRow) -> Sequence[str]:
        return inspection_cells(row)

    def row_record(self, row: InspectionRow) -> tuple[str, str]:
        return (row.key, row.title)

    def panel_text(self, row: InspectionRow | None) -> Panel:
        """The highlighted inspection in full: one ``get_inspection`` read for it."""
        if row is None:
            return "No inspection matches."
        try:
            detail = self.client.get_inspection(self.project, row.key)
        except CLIENT_ERRORS as exc:
            self.say(describe_error(exc), error=True)
            return "This inspection could not be read."
        technical = mode_of(self.app).technical
        return render(inspection_page(detail, technical=technical, panel=True))

    def actions_for(self, row: InspectionRow) -> Sequence[LogAction]:
        """No action on the log's rows: the commands are on the inspection's screen."""
        return []

    def summary_text(self) -> str:
        if not self.mine:
            return inspection_summary(
                self.rows,
                self.total,
                len(self.shown),
                state=self.state_filter,
                point=self.point_filter,
            )
        named: list[str] = []
        if self.state_filter is not None:
            named.append(f"state {humanize(self.state_filter)}")
        if self.point_filter is not None:
            named.append(f"point {self.point_filter}")
        named.append("mine")
        return ", ".join([f"{len(self.shown)} of {inspection_count(self.total)}", *named])

    def open_row(self, row: InspectionRow) -> None:
        """Enter on a row opens the inspection's screen."""
        self.app.push_screen(InspectionScreen(self.client, self.project, row.key))

    # --- the log's own keys --------------------------------------------------------------

    def action_state(self) -> None:
        """Show the next state: all, then Planned, Scheduled, Done, Verified and Cancelled."""
        if isinstance(self.focused, Input):
            return  # the key is text
        self.state_filter = _next_value(self.state_filter, STATES)
        self.reload()

    def action_point(self) -> None:
        """Show the next point: all, then hold, witness, review and surveillance."""
        if isinstance(self.focused, Input):
            return  # the key is text
        self.point_filter = _next_value(self.point_filter, POINTS)
        self.reload()

    def action_mine(self) -> None:
        """Show only the inspections whose inspector is the signed-in actor (again: all)."""
        if isinstance(self.focused, Input):
            return  # the key is text
        self.mine = not self.mine
        self.reload()

    # --- helpers -------------------------------------------------------------------------

    def _actor(self) -> str:
        return str(getattr(self.app, "actor", "user:dev"))


class InspectionScreen(ModalScreen[None]):
    """One inspection in full. Esc closes it, F5 reads it again; ``v``, ``r`` and ``x`` are
    offered only in the states that take them."""

    KEY_HINTS: ClassVar[str] = (
        "v Verify  r Reinspect  x Cancel  Esc back  F5 reload  "
        "schedule and record answers: on the CLI"
    )

    BINDINGS: ClassVar[list[BindingType]] = [
        Binding("escape", "close", "Close", show=False),
        Binding("f5", "reload", "Reload", show=False),
        Binding("v", "verify", "Verify", show=False),
        Binding("r", "reinspect", "Reinspect", show=False),
        Binding("x", "cancel", "Cancel", show=False),
    ]

    DEFAULT_CSS = """
    InspectionScreen { background: $surface; }
    InspectionScreen #inspection-body { height: 1fr; padding: 0 1; }
    InspectionScreen #inspection-keys { height: 1; color: $text-muted; }
    InspectionScreen #inspection-status { height: 1; }
    """

    def __init__(self, client: ClientInterface, project: str, key: str) -> None:
        super().__init__()
        self.client = client
        self.project = project
        self.key = key
        self.detail: InspectionDetail | None = None  # as last read
        self.flash = ""  # the refusal of the last command, shown until the next command
        self._gen = 0

    # --- layout --------------------------------------------------------------------------

    def compose(self) -> ComposeResult:
        with Vertical():
            with VerticalScroll(id="inspection-body"):
                yield Static("", markup=False, id="inspection-page")
            yield Static(self.KEY_HINTS, markup=False, id="inspection-keys")
            yield Static("", markup=False, id="inspection-status")

    def on_mount(self) -> None:
        self.reload()

    # --- reads ---------------------------------------------------------------------------

    def reload(self) -> None:
        """Read the inspection again (off the UI thread)."""
        self._gen += 1
        self.run_worker(
            self._load(self._gen, mode_of(self.app).technical), group="inspection", exclusive=True
        )

    async def _load(self, gen: int, technical: bool) -> None:
        try:
            detail = await asyncio.to_thread(self.client.get_inspection, self.project, self.key)
        except CLIENT_ERRORS as exc:
            if gen == self._gen and self.is_attached:
                self.detail = None
                self._show(None, describe_error(exc))
            return
        if gen == self._gen and self.is_attached:
            self.detail = detail
            self._show(inspection_page(detail, technical=technical), self.flash)

    def _show(self, page: Page | None, error: str) -> None:
        body: Adaptive | str = (
            render(page) if page is not None else "This inspection could not be read."
        )
        self.query_one("#inspection-page", Static).update(body)
        self.query_one("#inspection-keys", Static).update(self._keys_text())
        status = self.query_one("#inspection-status", Static)
        status.update(("! " + error) if error else "")

    # --- the screen's keys ---------------------------------------------------------------

    def _offers(self, command: str) -> bool:
        """The command is offered (and taken) for the inspection's state now."""
        return self.detail is not None and self.detail.row.state in states_for(command, INSPECTION)

    def _keys_text(self) -> str:
        offered = [
            cell
            for cell, command in (
                ("v Verify", VERIFY),
                ("r Reinspect", REINSPECT),
                ("x Cancel", CANCEL),
            )
            if self._offers(command)
        ]
        return "  ".join([*offered, "Esc back", "F5 reload", "schedule and record: CLI"])

    def action_reload(self) -> None:
        self.reload()

    def action_close(self) -> None:
        self.dismiss(None)

    def action_verify(self) -> None:
        """Ask "are you sure", then verify the inspection (Done only)."""
        if not self._offers(VERIFY):
            return

        def answered(answers: dict[str, str] | None) -> None:
            if answers is not None:
                self._send(
                    VERIFY,
                    lambda: VerifyInspection(**self._envelope(), **self._target()),
                )

        self.app.push_screen(
            ActionFormScreen(
                "Verify inspection", confirm="Are you sure this inspection is verified?"
            ),
            answered,
        )

    def action_reinspect(self) -> None:
        """Ask an optional date for the new inspection, then plan it (Done or Verified only)."""
        if not self._offers(REINSPECT):
            return

        def answered(answers: dict[str, str] | None) -> None:
            if answers is not None:
                planned = answers["planned_on"].strip() or None
                self._send(
                    REINSPECT,
                    lambda: ReinspectInspection(
                        **self._envelope(), **self._target(), planned_on=planned
                    ),
                )

        self.app.push_screen(
            ActionFormScreen(
                "Reinspect",
                (FormField("planned_on", "Date YYYY-MM-DD (optional)", required=False),),
            ),
            answered,
        )

    def action_cancel(self) -> None:
        """Ask for the reason, then cancel the inspection (Planned or Scheduled only)."""
        if not self._offers(CANCEL):
            return

        def answered(answers: dict[str, str] | None) -> None:
            if answers is not None:
                self._send(
                    CANCEL,
                    lambda: CancelInspection(
                        **self._envelope(), **self._target(), reason=answers["reason"]
                    ),
                )

        self.app.push_screen(
            ActionFormScreen("Cancel inspection", (FormField("reason", "Reason"),)), answered
        )

    # --- helpers -------------------------------------------------------------------------

    def _target(self) -> dict[str, Any]:
        """The inspection (its id, carried and never shown) and the version the screen read."""
        assert self.detail is not None  # the keys are offered only when an inspection is read
        return {"inspection": self.detail.row.id, "expected_version": self.detail.version}

    def _envelope(self) -> dict[str, Any]:
        return {
            "actor": str(getattr(self.app, "actor", "user:dev")),
            "source": "tui",
            "scope": f"project:{self.project}",
        }

    def _send(self, name: str, make: Callable[[], Any]) -> None:
        """Send the command as the person. A refusal is the status line; the inspection is read
        again either way."""
        try:
            self.client.quality_command(name, make())
        except CLIENT_ERRORS as exc:
            self.flash = describe_error(exc)
        else:
            self.flash = ""
        self.reload()
