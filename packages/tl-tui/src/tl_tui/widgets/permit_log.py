"""The permit register of a project and one permit's screen (P2-PTW-T11; spec §8, ``tui-layout``).

``PermitLogScreen`` is a full-size ``LogScreen``: the project's permits by key, with subject,
state, type, area, holder, valid-until and the record they are for. The panel describes the
highlighted permit. ``s`` shows the next state, ``t`` the next type (the names of the type table),
``a`` the next area of the rows, ``m`` the permits whose holder is the signed-in actor; each filter
is read again from the client (the list filters). Enter opens ``PermitScreen``.

``PermitScreen`` shows one permit in full. ``a`` approves it, ``x`` rejects it, ``s`` suspends it,
``r`` resumes it, ``v`` revalidates it, ``h`` hands it back, ``c`` closes it. A key is shown and
taken only in the states ``permit_text.ACTIONS`` offers the command in. The command goes through
the client's ``permit_command`` with the signed-in actor, the project's scope and the permit's
version; a refusal is the status line, then the permit is read again. Issue, cancel and request
stay on the CLI.
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable, Iterable, Sequence
from typing import Any, ClassVar

from pydantic import ValidationError
from textual.app import ComposeResult
from textual.binding import Binding, BindingType
from textual.containers import Vertical, VerticalScroll
from textual.screen import ModalScreen
from textual.widgets import Input, Static
from tl_mod_permits.commands import (
    ApprovePermit,
    ClosePermit,
    HandBackPermit,
    RejectPermit,
    ResumePermit,
    RevalidatePermit,
    SuspendPermit,
)
from tl_mod_permits.iso_views import GasRow
from tl_mod_permits.types_table import load_types
from tl_mod_permits.views import SHOWN_STATES, PermitDetail, PermitRow

from tl_tui.action_ui import FormField
from tl_tui.client import ClientInterface
from tl_tui.display import humanize, mode_of
from tl_tui.errors import CLIENT_ERRORS, describe_error
from tl_tui.layout import Adaptive, Page, Panel, render
from tl_tui.permit_text import (
    ACTIONS,
    PERMIT_COLUMNS,
    PERMIT_DROP,
    permit_cells,
    permit_count,
    permit_page,
    permit_summary,
)
from tl_tui.widgets.action_form import ActionFormScreen
from tl_tui.widgets.log_screen import LogAction, LogScreen

APPROVE = "ApprovePermit"
REJECT = "RejectPermit"
SUSPEND = "SuspendPermit"
RESUME = "ResumePermit"
REVALIDATE = "RevalidatePermit"
HAND_BACK = "HandBackPermit"
CLOSE = "ClosePermit"


def _next_value(current: str | None, values: Iterable[str]) -> str | None:
    """The next filter value: all (``None``), then each value in order, then all again."""
    options: list[str | None] = [None, *values]
    index = options.index(current) if current in options else 0
    return options[(index + 1) % len(options)]


def permit_types() -> tuple[str, ...]:
    """The permit type names, as the type table reads them (at runtime)."""
    return tuple(load_types())


class PermitLogScreen(LogScreen[PermitRow]):
    """The permits of ``project`` (the id, not the scope)."""

    LOG_NAME: ClassVar[str] = "Permits to work"
    # every key the log has, in one text (the walking tests read it); the keys row shows KEY_CELLS
    KEY_HINTS: ClassVar[str] = "/ filter  s state  t type  a area  m mine  F5 reload  Esc back"
    KEY_CELLS: ClassVar[tuple[str, ...]] = (
        "/ filter",
        "s state",
        "t type",
        "a area",
        "m mine",
    )
    HELP_KEYS: ClassVar[tuple[tuple[str, str], ...]] = (
        ("s", "Show the next state: all, then each state"),
        ("t", "Show the next permit type: all, then each type of the type table"),
        ("a", "Show the next area of the rows: all, then each area"),
        ("m", "Show only the permits whose holder is you (again: all)"),
    )

    BINDINGS: ClassVar[list[BindingType]] = [
        Binding("s", "state", "State", show=False),
        Binding("t", "type", "Type", show=False),
        Binding("a", "area", "Area", show=False),
        Binding("m", "mine", "Mine", show=False),
    ]

    def __init__(self, client: ClientInterface, project: str) -> None:
        super().__init__()
        self.client = client
        self.project = project
        self.state_filter: str | None = None
        self.type_filter: str | None = None
        self.area_filter: str | None = None
        self.mine = False  # True: only the permits whose holder is the signed-in actor
        self.total = 0  # the page total, as last read
        self.areas: list[str] = []  # the areas of the unfiltered rows, as last read

    # --- the log's hooks -----------------------------------------------------------------

    def log_project(self) -> str:
        return self.project

    def columns(self) -> Sequence[str]:
        return PERMIT_COLUMNS

    def drop_order(self) -> Sequence[str]:
        return PERMIT_DROP

    def load_rows(self) -> Sequence[PermitRow]:
        """The filters go to the list (state, type, area, holder); the summary counts the rows.
        The area names come from the unfiltered rows only, so the area key keeps its cycle."""
        page = self.client.list_permits(
            self.project,
            state=self.state_filter,
            permit_type=self.type_filter,
            area=self.area_filter,
            holder=self._actor() if self.mine else None,
        )
        self.total = page.total
        unfiltered = (
            self.state_filter is None
            and self.type_filter is None
            and self.area_filter is None
            and not self.mine
        )
        if unfiltered:
            self.areas = sorted({row.area for row in page.rows if row.area})
        return page.rows

    def row_key(self, row: PermitRow) -> str:
        return row.key

    def row_cells(self, row: PermitRow) -> Sequence[str]:
        return permit_cells(row)

    def row_record(self, row: PermitRow) -> tuple[str, str]:
        return (row.key, row.subject)

    def panel_text(self, row: PermitRow | None) -> Panel:
        """The highlighted permit in full: one ``get_permit`` read and its gas tests."""
        if row is None:
            return "No permit matches."
        try:
            detail = self.client.get_permit(self.project, row.key)
            gas = self.client.list_gas_tests(self.project, row.key)
        except CLIENT_ERRORS as exc:
            self.say(describe_error(exc), error=True)
            return "This permit could not be read."
        technical = mode_of(self.app).technical
        return render(permit_page(detail, gas, technical=technical, panel=True))

    def actions_for(self, row: PermitRow) -> Sequence[LogAction]:
        """No action on the log's rows: the commands are on the permit's screen."""
        return []

    def summary_text(self) -> str:
        if self.area_filter is None and not self.mine:
            return permit_summary(
                self.rows,
                self.total,
                len(self.shown),
                state=self.state_filter,
                permit_type=self.type_filter,
            )
        named: list[str] = []
        if self.state_filter is not None:
            named.append(f"state {humanize(self.state_filter)}")
        if self.type_filter is not None:
            named.append(f"type {humanize(self.type_filter).lower()}")
        if self.area_filter is not None:
            named.append(f"area {self.area_filter}")
        if self.mine:
            named.append("mine")
        return ", ".join([f"{len(self.shown)} of {permit_count(self.total)}", *named])

    def open_row(self, row: PermitRow) -> None:
        """Enter on a row opens the permit's screen."""
        self.app.push_screen(PermitScreen(self.client, self.project, row.key))

    # --- the log's own keys --------------------------------------------------------------

    def action_state(self) -> None:
        """Show the next state: all, then each shown state."""
        if isinstance(self.focused, Input):
            return  # the key is text
        self.state_filter = _next_value(self.state_filter, SHOWN_STATES)
        self.reload()

    def action_type(self) -> None:
        """Show the next permit type: all, then each name of the type table."""
        if isinstance(self.focused, Input):
            return  # the key is text
        self.type_filter = _next_value(self.type_filter, permit_types())
        self.reload()

    def action_area(self) -> None:
        """Show the next area of the rows: all, then each area in name order."""
        if isinstance(self.focused, Input):
            return  # the key is text
        self.area_filter = _next_value(self.area_filter, self.areas)
        self.reload()

    def action_mine(self) -> None:
        """Show only the permits whose holder is the signed-in actor (again: all)."""
        if isinstance(self.focused, Input):
            return  # the key is text
        self.mine = not self.mine
        self.reload()

    # --- helpers -------------------------------------------------------------------------

    def _actor(self) -> str:
        return str(getattr(self.app, "actor", "user:dev"))


class PermitScreen(ModalScreen[None]):
    """One permit in full. Esc closes it, F5 reads it again; each command key is offered only in
    the states ``permit_text.ACTIONS`` gives it."""

    KEY_HINTS: ClassVar[str] = (
        "a Approve  x Reject  s Suspend  r Resume  v Revalidate  h Hand back  c Close  "
        "Esc back  F5 reload  issue, cancel, request: CLI"
    )

    BINDINGS: ClassVar[list[BindingType]] = [
        Binding("escape", "close", "Close", show=False),
        Binding("f5", "reload", "Reload", show=False),
        Binding("a", "approve", "Approve", show=False),
        Binding("x", "reject", "Reject", show=False),
        Binding("s", "suspend", "Suspend", show=False),
        Binding("r", "resume", "Resume", show=False),
        Binding("v", "revalidate", "Revalidate", show=False),
        Binding("h", "hand_back", "Hand back", show=False),
        Binding("c", "close_permit", "Close permit", show=False),
    ]

    DEFAULT_CSS = """
    PermitScreen { background: $surface; }
    PermitScreen #permit-body { height: 1fr; padding: 0 1; }
    PermitScreen #permit-keys { height: 1; color: $text-muted; }
    PermitScreen #permit-status { height: 1; }
    """

    def __init__(self, client: ClientInterface, project: str, key: str) -> None:
        super().__init__()
        self.client = client
        self.project = project
        self.key = key
        self.detail: PermitDetail | None = None  # as last read
        self.flash = ""  # the refusal of the last command, shown until the next command
        self._gen = 0

    # --- layout --------------------------------------------------------------------------

    def compose(self) -> ComposeResult:
        with Vertical():
            with VerticalScroll(id="permit-body"):
                yield Static("", markup=False, id="permit-page")
            yield Static(self.KEY_HINTS, markup=False, id="permit-keys")
            yield Static("", markup=False, id="permit-status")

    def on_mount(self) -> None:
        self.reload()

    # --- reads ---------------------------------------------------------------------------

    def reload(self) -> None:
        """Read the permit again (off the UI thread)."""
        self._gen += 1
        self.run_worker(
            self._load(self._gen, mode_of(self.app).technical), group="permit", exclusive=True
        )

    async def _load(self, gen: int, technical: bool) -> None:
        try:
            detail, gas = await asyncio.to_thread(self._read)
        except CLIENT_ERRORS as exc:
            if gen == self._gen and self.is_attached:
                self.detail = None
                self._show(None, describe_error(exc))
            return
        if gen == self._gen and self.is_attached:
            self.detail = detail
            self._show(permit_page(detail, gas, technical=technical), self.flash)

    def _read(self) -> tuple[PermitDetail, list[GasRow]]:
        detail = self.client.get_permit(self.project, self.key)
        return detail, self.client.list_gas_tests(self.project, self.key)

    def _show(self, page: Page | None, error: str) -> None:
        body: Adaptive | str = (
            render(page) if page is not None else "This permit could not be read."
        )
        self.query_one("#permit-page", Static).update(body)
        self.query_one("#permit-keys", Static).update(self._keys_text())
        status = self.query_one("#permit-status", Static)
        status.update(("! " + error) if error else "")

    # --- the screen's keys ---------------------------------------------------------------

    def _offers(self, command: str) -> bool:
        """The command is offered (and taken) for the permit's state now."""
        return self.detail is not None and self.detail.row.state in ACTIONS[command]

    def _keys_text(self) -> str:
        cells = (
            ("a Approve", APPROVE),
            ("x Reject", REJECT),
            ("s Suspend", SUSPEND),
            ("r Resume", RESUME),
            ("v Revalidate", REVALIDATE),
            ("h Hand back", HAND_BACK),
            ("c Close", CLOSE),
        )
        offered = [cell for cell, command in cells if self._offers(command)]
        return "  ".join([*offered, "Esc back", "F5 reload", "issue, cancel, request: CLI"])

    def action_reload(self) -> None:
        self.reload()

    def action_close(self) -> None:
        self.dismiss(None)

    def action_approve(self) -> None:
        """Ask "are you sure", then approve the permit (Requested only)."""
        if not self._offers(APPROVE):
            return

        def answered(answers: dict[str, str] | None) -> None:
            if answers is not None:
                self._send(APPROVE, lambda: ApprovePermit(**self._envelope(), **self._target()))

        self.app.push_screen(
            ActionFormScreen("Approve permit", confirm="Are you sure this permit is approved?"),
            answered,
        )

    def action_reject(self) -> None:
        """Ask for the reason, then reject the permit (Requested only)."""
        if not self._offers(REJECT):
            return

        def answered(answers: dict[str, str] | None) -> None:
            if answers is not None:
                self._send(
                    REJECT,
                    lambda: RejectPermit(
                        **self._envelope(), **self._target(), reason=answers["reason"]
                    ),
                )

        self.app.push_screen(
            ActionFormScreen("Reject permit", (FormField("reason", "Reason"),)), answered
        )

    def action_suspend(self) -> None:
        """Ask for the reason, then suspend the permit (Active or Lapsed)."""
        if not self._offers(SUSPEND):
            return

        def answered(answers: dict[str, str] | None) -> None:
            if answers is not None:
                self._send(
                    SUSPEND,
                    lambda: SuspendPermit(
                        **self._envelope(), **self._target(), reason=answers["reason"]
                    ),
                )

        self.app.push_screen(
            ActionFormScreen("Suspend permit", (FormField("reason", "Reason"),)), answered
        )

    def action_resume(self) -> None:
        """Ask "are you sure", then resume the permit (Suspended only)."""
        if not self._offers(RESUME):
            return

        def answered(answers: dict[str, str] | None) -> None:
            if answers is not None:
                self._send(RESUME, lambda: ResumePermit(**self._envelope(), **self._target()))

        self.app.push_screen(
            ActionFormScreen("Resume permit", confirm="Are you sure this permit is resumed?"),
            answered,
        )

    def action_revalidate(self) -> None:
        """Ask "are you sure", then revalidate the permit (Active or Lapsed)."""
        if not self._offers(REVALIDATE):
            return

        def answered(answers: dict[str, str] | None) -> None:
            if answers is not None:
                self._send(
                    REVALIDATE, lambda: RevalidatePermit(**self._envelope(), **self._target())
                )

        self.app.push_screen(
            ActionFormScreen(
                "Revalidate permit", confirm="Are you sure this permit is revalidated?"
            ),
            answered,
        )

    def action_hand_back(self) -> None:
        """Ask for the note that the site is safe, then hand the permit back (Active, Lapsed or
        Suspended)."""
        if not self._offers(HAND_BACK):
            return

        def answered(answers: dict[str, str] | None) -> None:
            if answers is not None:
                self._send(
                    HAND_BACK,
                    lambda: HandBackPermit(
                        **self._envelope(), **self._target(), handback_note=answers["note"]
                    ),
                )

        self.app.push_screen(
            ActionFormScreen("Hand back permit", (FormField("note", "Note"),)), answered
        )

    def action_close_permit(self) -> None:
        """Ask "are you sure", then close the permit (Handed back only)."""
        if not self._offers(CLOSE):
            return

        def answered(answers: dict[str, str] | None) -> None:
            if answers is not None:
                self._send(CLOSE, lambda: ClosePermit(**self._envelope(), **self._target()))

        self.app.push_screen(
            ActionFormScreen("Close permit", confirm="Are you sure this permit is closed?"),
            answered,
        )

    # --- helpers -------------------------------------------------------------------------

    def _target(self) -> dict[str, Any]:
        """The permit (its id, carried and never shown) and the version the screen read."""
        assert self.detail is not None  # the keys are offered only when a permit is read
        return {"permit": self.detail.row.id, "expected_version": self.detail.version}

    def _envelope(self) -> dict[str, Any]:
        return {
            "actor": str(getattr(self.app, "actor", "user:dev")),
            "source": "tui",
            "scope": f"project:{self.project}",
        }

    def _send(self, name: str, make: Callable[[], Any]) -> None:
        """Send the command as the person. A refusal is the status line; the permit is read again
        either way."""
        try:
            command = make()
            self.client.permit_command(name, command)
        except ValidationError as exc:
            self.flash = "The text is not valid: " + str(exc.errors()[0]["msg"])
        except CLIENT_ERRORS as exc:
            self.flash = describe_error(exc)
        else:
            self.flash = ""
        self.reload()
