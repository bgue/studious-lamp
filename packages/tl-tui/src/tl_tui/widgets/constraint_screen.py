"""The constraint review and a record's constraint log (P2-I2 T04b; spec §8, ``tui-layout``).

A full-size ``LogScreen``. With no subject it lists the project's visible constraints (one log);
with ``subject_key`` it lists that record's constraints only and names the key in its summary
line (``Constraints on <key>``). The list shows key, subject, type, state, owner, need by, age and
source; ``o``, ``t`` and ``a`` group the rows by owner, type or age (the same key again ungroups),
``s`` shows the next state, ``b`` the blocking rows only. The columns, cells, summary and page
come from ``tl_tui.constraint_text``; this screen only reads the rows and keeps its filters. No
action is offered (the writes are not in this increment: ``actions_for`` returns ``[]``).

Enter reads the constraint once (``get_constraint``) and shows its page in the panel; below 120
columns the page opens as a text box instead. A constraint that cannot be read is named in the
status line.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import TYPE_CHECKING, ClassVar

from textual.binding import Binding, BindingType
from textual.containers import Vertical, VerticalScroll
from textual.screen import ModalScreen
from textual.widgets import Input, Static
from tl_api.routes.constraints import ConstraintRow
from tl_core.constraints.queries import MAX_LIMIT

from tl_tui.client import ClientInterface
from tl_tui.constraint_text import (
    CONSTRAINT_COLUMNS,
    CONSTRAINT_DROP,
    constraint_cells,
    constraint_page,
    constraint_summary,
    order_by_group,
)
from tl_tui.display import mode_of
from tl_tui.errors import CLIENT_ERRORS, describe_error
from tl_tui.layout import Page, Panel, plain_lines, render
from tl_tui.widgets.log_screen import LogAction, LogScreen

if TYPE_CHECKING:
    from collections.abc import Iterable

    from textual.app import ComposeResult
WIDE_MIN = 120  # from this width the page of an opened constraint stays in the panel
BLOCKING = "blocking"


def _next_value(current: str | None, values: Iterable[str]) -> str | None:
    """The next state filter: all (``None``), then each value in order, then all again."""
    options: list[str | None] = [None, *sorted(set(values))]
    index = options.index(current) if current in options else 0
    return options[(index + 1) % len(options)]


class ConstraintPageScreen(ModalScreen[None]):
    """A constraint's page as text, for a terminal narrower than ``WIDE_MIN``. Esc closes it."""

    KEY_HINTS: ClassVar[str] = "Esc close"

    BINDINGS: ClassVar[list[BindingType]] = [Binding("escape", "close", "Close", show=False)]

    DEFAULT_CSS = """
    ConstraintPageScreen { align: center middle; }
    ConstraintPageScreen > Vertical {
        width: 95%;
        height: 90%;
        border: round $accent;
        background: $surface;
        padding: 0 1;
    }
    ConstraintPageScreen #constraint-page-scroll { height: 1fr; }
    """

    def __init__(self, page: Page) -> None:
        super().__init__()
        self.page = page

    def compose(self) -> ComposeResult:
        with Vertical():
            with VerticalScroll(id="constraint-page-scroll"):
                yield Static(
                    "\n".join(plain_lines(self.page)), id="constraint-page-text", markup=False
                )

    def action_close(self) -> None:
        self.dismiss(None)


class ConstraintScreen(LogScreen[ConstraintRow]):
    """The constraints of ``project``, or those of the record ``subject_key`` (its key)."""

    LOG_NAME: ClassVar[str] = "Constraints"
    # every key the log has, in one text (the walking tests read it); the keys row shows KEY_CELLS
    # and F1 lists the rest (HELP_KEYS)
    KEY_HINTS: ClassVar[str] = (
        "/ filter  o owner  t type  a age  s state  b blocking  F5 reload  Esc back"
    )
    KEY_CELLS: ClassVar[tuple[str, ...]] = (
        "/ filter",
        "o owner",
        "t type",
        "a age",
        "s state",
        "b blocking",
    )
    HELP_KEYS: ClassVar[tuple[tuple[str, str], ...]] = (
        ("o", "Group the rows by owner; again to list them in key order"),
        ("t", "Group the rows by type (category); again to ungroup"),
        ("a", "Group the rows by age band; again to ungroup"),
        ("s", "Show the next state: all, then each state in the list"),
        ("b", "Show the blocking constraints only; again for all"),
    )

    BINDINGS: ClassVar[list[BindingType]] = [
        Binding("o", "by_owner", "Owner", show=False),
        Binding("t", "by_type", "Type", show=False),
        Binding("a", "by_age", "Age", show=False),
        Binding("s", "state", "State", show=False),
        Binding("b", "blocking", "Blocking", show=False),
    ]

    def __init__(
        self, client: ClientInterface, project: str, subject_key: str | None = None
    ) -> None:
        super().__init__()
        self.client = client
        self.project = project
        self.subject_key = subject_key
        self.state_filter: str | None = None
        self.blocking_only = False
        self.by: str | None = None  # the group: owner, category or age; None: key order
        self.views: list[ConstraintRow] = []  # as listed, before the screen's own filters
        self.total = 0  # how many constraints the same filters find in all

    # --- the log's hooks -----------------------------------------------------------------

    def log_project(self) -> str:
        return self.project

    def columns(self) -> Sequence[str]:
        return CONSTRAINT_COLUMNS

    def drop_order(self) -> Sequence[str]:
        return CONSTRAINT_DROP

    def load_rows(self) -> Sequence[ConstraintRow]:
        found = self.client.list_constraints(
            self.project, subject=self.subject_key, limit=MAX_LIMIT
        )
        self.views = list(found.rows)
        self.total = found.total
        return self._filtered()

    def row_key(self, row: ConstraintRow) -> str:
        return row.key

    def row_cells(self, row: ConstraintRow) -> Sequence[str]:
        return constraint_cells(row)

    def row_record(self, row: ConstraintRow) -> tuple[str, str]:
        return (row.key, row.description or row.subject_key)

    def panel_text(self, row: ConstraintRow | None) -> Panel:
        """The highlighted constraint's page, from the row the list holds (no read)."""
        if row is None:
            return "No constraint matches."
        technical = mode_of(self.app).technical
        return render(constraint_page(row, technical=technical, panel=True))

    def actions_for(self, row: ConstraintRow) -> Sequence[LogAction]:
        """No action on a constraint yet: the writes are not in this increment."""
        return []

    def summary_text(self) -> str:
        blocking = sum(1 for row in self.shown if row.severity == BLOCKING)
        aging = sum(1 for row in self.shown if row.aging)
        text = constraint_summary(
            self.total,
            len(self.shown),
            by=self.by,
            blocking=blocking,
            aging=aging,
            truncated=self.by is not None and self.total > len(self.views),
        )
        if self.subject_key is not None:
            return f"Constraints on {self.subject_key} · {text}"
        return text

    def open_row(self, row: ConstraintRow) -> None:
        """Enter: read the constraint once and show its page (the panel, or a text box below
        ``WIDE_MIN`` columns). A constraint that cannot be read is named in the status line."""
        try:
            full = self.client.get_constraint(self.project, row.key)
        except CLIENT_ERRORS as exc:
            self.say(describe_error(exc), error=True)
            return
        technical = mode_of(self.app).technical
        if self.app.size.width < WIDE_MIN:
            self.app.push_screen(ConstraintPageScreen(constraint_page(full, technical=technical)))
            return
        page = constraint_page(full, technical=technical)
        self.query_one("#log-panel-text", Static).update(render(page))

    # --- the log's own keys --------------------------------------------------------------

    def action_by_owner(self) -> None:
        self._group("owner")

    def action_by_type(self) -> None:
        self._group("category")

    def action_by_age(self) -> None:
        self._group("age")

    def action_state(self) -> None:
        """Show the next state: all, then each state that a constraint in the list has."""
        if isinstance(self.focused, Input):
            return  # the key is text
        self.state_filter = _next_value(self.state_filter, (v.state for v in self.views))
        self._apply()

    def action_blocking(self) -> None:
        """Show the blocking constraints only, or all of them again."""
        if isinstance(self.focused, Input):
            return  # the key is text
        self.blocking_only = not self.blocking_only
        self._apply()

    # --- helpers -------------------------------------------------------------------------

    def _group(self, by: str) -> None:
        """Group by ``by``, or ungroup when the list is already grouped by it."""
        if isinstance(self.focused, Input):
            return  # the key is text
        self.by = None if self.by == by else by
        self._apply()

    def _filtered(self) -> list[ConstraintRow]:
        """The listed constraints the screen's filters keep, in the order the screen shows them."""
        rows = [
            v
            for v in self.views
            if (self.state_filter is None or v.state == self.state_filter)
            and (not self.blocking_only or v.severity == BLOCKING)
        ]
        if self.by is not None:
            return order_by_group(rows, self.by)
        return rows

    def _apply(self) -> None:
        """A filter or group key changed: filter the rows held (no read), keep the cursor."""
        self.rows = self._filtered()
        self._fill(self._key())
