"""The IWP log and the IWP screen (P2-I2 T07b; spec §8, ``tui-layout``).

``IwpRegisterScreen`` is a full-size ``LogScreen``: the project's IWPs by number, with subject,
state, discipline, foreman, planned start, scope count and hours. The panel describes the
highlighted IWP (``iwp_page``, panel form). ``s`` shows the next state, ``d`` the next discipline
(each: all, then each one present in the list), ``m`` shows only the IWPs whose foreman is the
signed-in actor, ``r`` shows only the Ready IWPs. The filters work on the rows already read; the
list is not read again. Enter opens ``IwpScreen`` for the IWP: one IWP in full, text only.

``IwpScreen`` has no actions (``actions_for`` is empty); Esc closes it, F5 reads it again.
"""

from __future__ import annotations

import asyncio
from collections.abc import Iterable, Sequence
from typing import TYPE_CHECKING, Any, ClassVar

from textual.app import ComposeResult
from textual.binding import Binding, BindingType
from textual.containers import Vertical, VerticalScroll
from textual.screen import ModalScreen
from textual.widgets import Input, Static
from tl_mod_awp.iwp_views import IwpRow

from tl_tui.awp_text import DISCIPLINE_LIST
from tl_tui.client import ClientInterface
from tl_tui.display import Labels, humanize, mode_of
from tl_tui.errors import CLIENT_ERRORS, describe_error
from tl_tui.iwp_text import IWP_COLUMNS, IWP_DROP, iwp_cells, iwp_page, iwp_summary
from tl_tui.labels_load import load_labels
from tl_tui.layout import Page, Panel, render
from tl_tui.widgets.log_screen import LogAction, LogScreen

if TYPE_CHECKING:
    from tl_tui.layout import Adaptive

READY = "Ready"  # the state the ``r`` key shows alone


def _next_value(current: str | None, values: Iterable[str]) -> str | None:
    """The next filter value: all (``None``), then each value in order, then all again."""
    options: list[str | None] = [None, *sorted(set(values))]
    index = options.index(current) if current in options else 0
    return options[(index + 1) % len(options)]


class IwpRegisterScreen(LogScreen[IwpRow]):
    """The IWPs of ``project`` (the id, not the scope)."""

    LOG_NAME: ClassVar[str] = "IWPs"
    # every key the log has, in one text (the walking tests read it); the keys row shows KEY_CELLS
    # and F1 lists the rest (HELP_KEYS)
    KEY_HINTS: ClassVar[str] = (
        "/ filter  s state  d discipline  m mine  r ready  F5 reload  Esc back"
    )
    KEY_CELLS: ClassVar[tuple[str, ...]] = (
        "/ filter",
        "s state",
        "d discipline",
        "m mine",
        "r ready",
    )
    HELP_KEYS: ClassVar[tuple[tuple[str, str], ...]] = (
        ("s", "Show the next state: all, then each state in the list"),
        ("d", "Show the next discipline: all, then each discipline in the list"),
        ("m", "Show only the IWPs whose foreman is you (again: all)"),
        ("r", "Show only the Ready IWPs (again: all)"),
    )

    BINDINGS: ClassVar[list[BindingType]] = [
        Binding("s", "state", "State", show=False),
        Binding("d", "discipline", "Discipline", show=False),
        Binding("m", "mine", "Mine", show=False),
        Binding("r", "ready", "Ready", show=False),
    ]

    def __init__(self, client: ClientInterface, project: str) -> None:
        super().__init__()
        self.client = client
        self.project = project
        self.state_filter: str | None = None
        self.discipline_filter: str | None = None
        self.mine = False  # True: only the IWPs whose foreman is the signed-in actor
        self.views: list[IwpRow] = []  # as listed, before the screen's own filters
        self.labels = Labels()  # the discipline labels, loaded with the first rows
        self._labelled = False

    # --- the log's hooks -----------------------------------------------------------------

    def log_project(self) -> str:
        return self.project

    def columns(self) -> Sequence[str]:
        return IWP_COLUMNS

    def drop_order(self) -> Sequence[str]:
        return IWP_DROP

    def load_rows(self) -> Sequence[IwpRow]:
        if not self._labelled:
            self.labels = load_labels(self.client, f"project:{self.project}", ("awp.IWP",))
            self._labelled = True
        self.views = self.client.list_iwps(self.project)
        return self._filtered()

    def row_key(self, row: IwpRow) -> str:
        return row.number

    def row_cells(self, row: IwpRow) -> Sequence[str]:
        return iwp_cells(row, self.labels)

    def row_record(self, row: IwpRow) -> tuple[str, str]:
        return (row.number, row.title)

    def panel_text(self, row: IwpRow | None) -> Panel:
        """The highlighted IWP in full: one ``get_iwp`` and one scope read for it."""
        if row is None:
            return "No IWP matches."
        try:
            full = self.client.get_iwp(self.project, row.number)
            scope = self.client.list_iwp_scope(self.project, row.number)
        except CLIENT_ERRORS as exc:
            self.say(describe_error(exc), error=True)
            return "This IWP could not be read."
        technical = mode_of(self.app).technical
        return render(iwp_page(full, scope, self.labels, technical=technical, panel=True))

    def actions_for(self, row: IwpRow) -> Sequence[LogAction]:
        """No action on an IWP here: the writes come with the later screens."""
        return []

    def summary_text(self) -> str:
        foreman = self._actor() if self.mine else None
        head = iwp_summary(
            len(self.views), len(self.shown), state=self.state_filter, foreman=foreman
        )
        named: list[str] = []
        if self.discipline_filter is not None:
            named.append(f"discipline {self._discipline_label(self.discipline_filter)}")
        if self.filter_text.strip():
            named.append(f"filter {self.filter_text.strip()!r}")
        return " · ".join([head, *named])

    def open_row(self, row: IwpRow) -> None:
        """Enter on a row opens the IWP screen for it."""
        self.app.push_screen(IwpScreen(self.client, self.project, row.number))

    # --- the log's own keys --------------------------------------------------------------

    def action_state(self) -> None:
        """Show the next state: all, then each state that an IWP in the list has."""
        if isinstance(self.focused, Input):
            return  # the key is text
        self.state_filter = _next_value(self.state_filter, (v.state for v in self.views))
        self._apply()

    def action_discipline(self) -> None:
        """Show the next discipline: all, then each discipline that an IWP in the list has."""
        if isinstance(self.focused, Input):
            return  # the key is text
        self.discipline_filter = _next_value(
            self.discipline_filter,
            (v.discipline for v in self.views if v.discipline is not None),
        )
        self._apply()

    def action_mine(self) -> None:
        """Show only the IWPs whose foreman is the signed-in actor, or all of them again."""
        if isinstance(self.focused, Input):
            return  # the key is text
        self.mine = not self.mine
        self._apply()

    def action_ready(self) -> None:
        """Show only the Ready IWPs, or all of them again."""
        if isinstance(self.focused, Input):
            return  # the key is text
        self.state_filter = None if self.state_filter == READY else READY
        self._apply()

    # --- helpers -------------------------------------------------------------------------

    def _actor(self) -> str:
        return str(getattr(self.app, "actor", "user:dev"))

    def _filtered(self) -> list[IwpRow]:
        """The listed IWPs the screen's filters keep, in number order."""
        actor = self._actor()
        return [
            v
            for v in self.views
            if (self.state_filter is None or v.state == self.state_filter)
            and (self.discipline_filter is None or v.discipline == self.discipline_filter)
            and (not self.mine or v.foreman == actor)
        ]

    def _apply(self) -> None:
        """A filter key changed: filter the rows already held (no read), keep the cursor."""
        self.rows = self._filtered()
        self._fill(self._key())

    def _discipline_label(self, code: str) -> str:
        return self.labels.code_labels.get(DISCIPLINE_LIST, {}).get(code) or humanize(code)


class IwpScreen(ModalScreen[None]):
    """One IWP in full: identity, state, summary, Scope, Sign-offs, Drawings, Constraints. Text
    only; Esc closes it, F5 reads it again."""

    KEY_HINTS: ClassVar[str] = "r Readiness  c Constraints  Esc back  F5 reload"

    BINDINGS: ClassVar[list[BindingType]] = [
        Binding("escape", "close", "Close", show=False),
        Binding("f5", "reload", "Reload", show=False),
        Binding("r", "readiness", "Readiness", show=False),
        Binding("c", "constraints", "Constraints", show=False),
    ]

    DEFAULT_CSS = """
    IwpScreen { background: $surface; }
    IwpScreen #iwp-body { height: 1fr; padding: 0 1; }
    IwpScreen #iwp-keys { height: 1; color: $text-muted; }
    IwpScreen #iwp-status { height: 1; }
    """

    def __init__(self, client: ClientInterface, project: str, number: str) -> None:
        super().__init__()
        self.client = client
        self.project = project
        self.number = number
        self.labels = Labels()
        self._gen = 0

    # --- layout --------------------------------------------------------------------------

    def compose(self) -> ComposeResult:
        with Vertical():
            with VerticalScroll(id="iwp-body"):
                yield Static("", markup=False, id="iwp-page")
            yield Static(self.KEY_HINTS, markup=False, id="iwp-keys")
            yield Static("", markup=False, id="iwp-status")

    def on_mount(self) -> None:
        self.reload()

    # --- reads ---------------------------------------------------------------------------

    def reload(self) -> None:
        """Read the IWP again (off the UI thread)."""
        self._gen += 1
        self.run_worker(
            self._load(self._gen, mode_of(self.app).technical), group="iwp", exclusive=True
        )

    async def _load(self, gen: int, technical: bool) -> None:
        try:
            page = await asyncio.to_thread(self._read, technical)
        except CLIENT_ERRORS as exc:
            if gen == self._gen and self.is_attached:
                self._show(None, describe_error(exc))
            return
        if gen == self._gen and self.is_attached:
            self._show(page, "")

    def _read(self, technical: bool) -> Page:
        self.labels = load_labels(self.client, f"project:{self.project}", ("awp.IWP",))
        detail = self.client.get_iwp(self.project, self.number)
        scope = self.client.list_iwp_scope(self.project, self.number)
        return iwp_page(detail, scope, self.labels, technical=technical)

    def _show(self, page: Page | None, error: str) -> None:
        body: Adaptive | str = render(page) if page is not None else "This IWP could not be read."
        self.query_one("#iwp-page", Static).update(body)
        status = self.query_one("#iwp-status", Static)
        status.update(("! " + error) if error else "")

    # --- the screen's keys ---------------------------------------------------------------

    def actions_for(self, *_: Any) -> Sequence[LogAction]:
        """Text only: this screen offers no action."""
        return []

    def action_reload(self) -> None:
        self.reload()

    def action_readiness(self) -> None:
        """The readiness checks of this IWP."""
        from tl_tui.widgets.readiness_screen import ReadinessScreen  # noqa: PLC0415

        self.app.push_screen(ReadinessScreen(self.client, self.project, self.number))

    def action_constraints(self) -> None:
        """The constraint log, filtered to this IWP."""
        from tl_tui.widgets.constraint_screen import ConstraintScreen  # noqa: PLC0415

        self.app.push_screen(ConstraintScreen(self.client, self.project, subject_key=self.number))

    def action_close(self) -> None:
        self.dismiss(None)
