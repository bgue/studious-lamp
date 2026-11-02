"""The CWP register: a project's construction work packages (P2-I1-T05d; spec §8, ``tui-layout``).

A full-size ``LogScreen``. The list shows the project's CWPs by number with their subject, state,
discipline, CWA, planned start, budget hours and whether they are allocated to the WBS. The panel
describes the highlighted CWP (``cwp_page``: identity, state, summary, then the sections). The
columns, cells, summary and page all come from ``tl_tui.awp_text``; this screen only reads the rows
and keeps its filters. ``d`` shows the next discipline, ``s`` the next state (each: all, then each
one present in the list), ``c`` groups the rows by CWA. No action is offered in I1 (writes come
with P2-I2). Enter on a row opens the full record screen; Esc returns to the same row.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import TYPE_CHECKING, ClassVar

from textual.binding import Binding, BindingType
from textual.widgets import Input
from tl_mod_awp.views import CwpRow

from tl_tui.awp_text import (
    CWP_COLUMNS,
    CWP_DROP,
    DISCIPLINE_LIST,
    cwp_cells,
    cwp_page,
    group_by_cwa,
)
from tl_tui.client import ClientInterface
from tl_tui.display import Labels, humanize, mode_of
from tl_tui.errors import CLIENT_ERRORS, describe_error
from tl_tui.labels_load import load_labels
from tl_tui.layout import Panel, render
from tl_tui.widgets.log_screen import LogAction, LogScreen
from tl_tui.widgets.record_screen import open_record

if TYPE_CHECKING:
    from collections.abc import Iterable


def _next_value(current: str | None, values: Iterable[str]) -> str | None:
    """The next filter value: all (``None``), then each value in order, then all again."""
    options: list[str | None] = [None, *sorted(set(values))]
    index = options.index(current) if current in options else 0
    return options[(index + 1) % len(options)]


def _count(n: int) -> str:
    return "1 CWP" if n == 1 else f"{n} CWPs"


class CwpRegisterScreen(LogScreen[CwpRow]):
    """The CWPs of ``project`` (the id, not the scope)."""

    LOG_NAME: ClassVar[str] = "CWPs"
    # every key the log has, in one text (the walking tests read it); the keys row shows KEY_CELLS
    # and F1 lists the rest (HELP_KEYS)
    KEY_HINTS: ClassVar[str] = "/ filter  d discipline  s state  c by CWA  F5 reload  Esc back"
    KEY_CELLS: ClassVar[tuple[str, ...]] = ("/ filter", "d discipline", "s state", "c by CWA")
    HELP_KEYS: ClassVar[tuple[tuple[str, str], ...]] = (
        ("d", "Show the next discipline: all, then each discipline in the list"),
        ("s", "Show the next state: all, then each state in the list"),
        ("c", "Group the rows by construction work area (CWA), in code order"),
    )

    BINDINGS: ClassVar[list[BindingType]] = [
        Binding("d", "discipline", "Discipline", show=False),
        Binding("s", "state", "State", show=False),
        Binding("c", "by_cwa", "By CWA", show=False),
    ]

    def __init__(self, client: ClientInterface, project: str) -> None:
        super().__init__()
        self.client = client
        self.project = project
        self.discipline_filter: str | None = None
        self.state_filter: str | None = None
        self.grouped = False  # True: the rows are ordered by CWA, then number
        self.views: list[CwpRow] = []  # as listed, before the screen's own filters
        self.labels = Labels()  # the discipline labels, loaded with the first rows
        self._labelled = False

    # --- the log's hooks -----------------------------------------------------------------

    def log_project(self) -> str:
        return self.project

    def columns(self) -> Sequence[str]:
        return CWP_COLUMNS

    def drop_order(self) -> Sequence[str]:
        return CWP_DROP

    def load_rows(self) -> Sequence[CwpRow]:
        if not self._labelled:
            self.labels = load_labels(self.client, f"project:{self.project}", ("awp.CWP",))
            self._labelled = True
        self.views = self.client.list_cwps(self.project)
        return self._filtered()

    def row_key(self, row: CwpRow) -> str:
        return row.number

    def row_cells(self, row: CwpRow) -> Sequence[str]:
        return cwp_cells(row, self.labels)

    def row_record(self, row: CwpRow) -> tuple[str, str]:
        return (row.number, row.title)

    def panel_text(self, row: CwpRow | None) -> Panel:
        """The highlighted CWP in full (one ``get_cwp`` call per CWP)."""
        if row is None:
            return "No CWP matches."
        try:
            full = self.client.get_cwp(self.project, row.number)
        except CLIENT_ERRORS as exc:
            self.say(describe_error(exc), error=True)
            return "This CWP could not be read."
        technical = mode_of(self.app).technical
        return render(cwp_page(full, self.labels, technical=technical, panel=True))

    def actions_for(self, row: CwpRow) -> Sequence[LogAction]:
        """I1 offers no action on a CWP: the writes come with P2-I2."""
        return []

    def summary_text(self) -> str:
        total = len(self.views)
        shown = len(self.shown)
        named: list[str] = []
        if self.discipline_filter is not None:
            named.append(f"discipline {self._discipline_label(self.discipline_filter)}")
        if self.state_filter is not None:
            named.append(f"state {humanize(self.state_filter)}")
        narrowed = bool(named) or bool(self.filter_text.strip())
        if self.filter_text.strip():
            named.append(f"filter {self.filter_text.strip()!r}")
        if self.grouped:
            named.append("by CWA")
        head = f"{shown} of {_count(total)}" if narrowed else _count(shown)
        return " · ".join([head, *named])

    def open_row(self, row: CwpRow) -> None:
        """Enter on a row opens its full record; Esc on that screen returns to this row."""
        actor = str(getattr(self.app, "actor", "user:dev"))
        open_record(self, self.client, f"project:{self.project}", self.project, actor, row.id)

    # --- the log's own keys --------------------------------------------------------------

    def action_discipline(self) -> None:
        """Show the next discipline: all, then each discipline that a CWP in the list has."""
        if isinstance(self.focused, Input):
            return  # the key is text
        self.discipline_filter = _next_value(
            self.discipline_filter,
            (v.discipline for v in self.views if v.discipline is not None),
        )
        self._apply()

    def action_state(self) -> None:
        """Show the next state: all, then each state that a CWP in the list has."""
        if isinstance(self.focused, Input):
            return  # the key is text
        self.state_filter = _next_value(self.state_filter, (v.state for v in self.views))
        self._apply()

    def action_by_cwa(self) -> None:
        """Group the rows by CWA, or list them by number again."""
        if isinstance(self.focused, Input):
            return  # the key is text
        self.grouped = not self.grouped
        self._apply()

    # --- helpers -------------------------------------------------------------------------

    def _filtered(self) -> list[CwpRow]:
        """The listed CWPs the screen's filters keep, in the order the screen shows them."""
        rows = [
            v
            for v in self.views
            if (self.discipline_filter is None or v.discipline == self.discipline_filter)
            and (self.state_filter is None or v.state == self.state_filter)
        ]
        if self.grouped:
            return [row for _, group in group_by_cwa(rows) for row in group]
        return rows

    def _apply(self) -> None:
        """A filter key changed: filter the rows already held (no read), keep the cursor."""
        self.rows = self._filtered()
        self._fill(self._key())

    def _discipline_label(self, code: str) -> str:
        return self.labels.code_labels.get(DISCIPLINE_LIST, {}).get(code) or humanize(code)
