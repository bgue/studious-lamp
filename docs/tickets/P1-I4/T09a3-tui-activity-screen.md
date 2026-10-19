# P1-I4-T09a3 — TUI: the activities of a snapshot and one activity

Status: ready
Tier: haiku
Labels: tui
Depends on: S9 and the TUI text helpers on `p1/i4` (in the tree); T09a1 opens this screen with `a` but the provided test pushes it directly
Branch: `p1/i4-t09a3-tui-activity-screen`

## Goal
A planner pages through the activities of a snapshot, keeps the critical ones or searches by id or name, and sees the highlighted activity with its dates, float, the relationships that name it and how its float moved through the published snapshots. `packages/tl-tui/src/tl_tui/widgets/activity_screen.py` has the layout, the bindings, the event handlers and the paging and filter actions written; `reload`, `_fill` and `_describe` raise `NotImplementedError`. You implement them. One provided test file must pass.

## Brief references (pasted)
> **Brief 10 TUI.** Screens are built on the client interface (`ClientInterface`); they never import the services. A screen shows what the services return and decides nothing.
>
> **ADR-0015 (M11).** A schedule is the series of snapshots of one P6 project, each upload an immutable snapshot, one of them the current schedule. Records link to an activity by its stable id. What moved between two snapshots, which float eroded and which links went stale are the module's findings; the screens show them as they come (`tl_tui/schedule_text.py`).

### Specification
- `reload` reads one page (`PAGE` rows from `self.first`) with the screen's filters; `_fill` fills the table and the status line from `self.page`; `_describe` writes the panel for the highlighted activity.
- `critical=True` asks for the critical activities; `critical=False` would ask for the non-critical ones, so the screen passes `None` when it shows all.
- An activity can be in one snapshot only: the float trend then has one line; a failure of the trend read is shown in the panel under the activity, not instead of it.

### Learnings that apply
> **Convention (AGENTS.md of tl-tui).** Screens call `ClientInterface` only; they never import a service handler, write SQL or touch the ledger.
>
> **L-P1-I4-9.** `just check` takes over two minutes in a fresh worktree; give it a long timeout or run it in the background and wait for it.
>
> **L-P0-I1-6.** ruff's `E501` applies to comments and docstrings at 100 columns, and pyright strict flags `@contextmanager` functions annotated `Iterator[X]`. Wrap prose.
>
> **L-P1-I3-3.** A stub fails pyright on unused imports and unused private helpers, so its header carries `# ruff: noqa: F401, F841` and a `# pyright: reportUnusedImport=false, ...` line. You remove both with the STEPS comments when the bodies are written, and then remove every import that is unused.
>
> **L-P0-I6C-8 / L-P1-I0B-3.** Write files with the Write tool, not a long `cat > file <<'EOF'` inside a `&&` chain, and never `pkill -f`: kill only a PID you started.

## Interfaces (verbatim from the repo at the branch point)
`packages/tl-tui/src/tl_tui/widgets/activity_screen.py` (the stub you complete; the whole file):
```python
# ruff: noqa: F401, F841
# pyright: reportUnusedImport=false, reportUnusedFunction=false, reportUnusedVariable=false
"""The activities of a schedule snapshot, one activity with its neighbours and float trend (P1-I4).

A full-size modal opened from the schedule screen with ``a``. The table lists the activities of
the snapshot in file order, a page at a time; the panel under it describes the highlighted one:
its dates, float, the relationships that name it and how its float moved through the published
snapshots. ``c`` keeps only the critical activities, ``/`` filters by id or name, ``n`` and ``b``
page forward and back. Everything is read through the client; the screen shows what the module
found and decides nothing.


STUB (P1-I4-T09a3): `reload`, `_fill` and `_describe` are `NotImplementedError`; the layout, the
bindings, the event handlers, the actions and the text helpers (`tl_tui/schedule_text.py`) are
written. The ticket fills the three bodies by their STEPS comments.
"""

from __future__ import annotations

from typing import ClassVar

from rich.text import Text
from textual.app import ComposeResult
from textual.binding import Binding, BindingType
from textual.containers import Vertical
from textual.screen import ModalScreen
from textual.widgets import DataTable, Input, Static
from tl_mod_schedule.registry import ActivityRow
from tl_mod_schedule.views import ActivityPage

from tl_tui.client import ClientInterface
from tl_tui.errors import CLIENT_ERRORS, describe_error
from tl_tui.schedule_text import (
    ACTIVITY_COLUMNS,
    activity_cells,
    activity_detail_lines,
    page_line,
    trend_lines,
)

PAGE = 200


class ActivityScreen(ModalScreen[None]):
    """The activities of snapshot ``number`` of schedule ``code`` (``None``: the current one)."""

    KEY_HINTS: ClassVar[str] = (
        "c critical only  n next page  b previous page  / filter  F5 reload  Esc close"
    )

    BINDINGS: ClassVar[list[BindingType]] = [
        Binding("c", "critical", "Critical", show=False),
        Binding("n", "next_page", "Next page", show=False),
        Binding("b", "previous_page", "Previous page", show=False),
        Binding("slash", "filter", "Filter", show=False),
        Binding("f5", "reload", "Reload", show=False),
        Binding("escape", "close", "Close", show=False),
    ]

    DEFAULT_CSS = """
    ActivityScreen { background: $surface; }
    ActivityScreen > Vertical { padding: 0 1; }
    ActivityScreen #ac-title { text-style: bold; height: 1; }
    ActivityScreen #ac-filter { height: 3; }
    ActivityScreen #ac-table { height: 1fr; min-height: 6; }
    ActivityScreen #ac-detail { height: 18; border-top: solid $accent; padding: 0 1; }
    ActivityScreen #ac-status { height: 1; }
    ActivityScreen #ac-hints { height: 1; color: $text-muted; }
    """

    def __init__(
        self, client: ClientInterface, project: str, code: str, number: int | None = None
    ) -> None:
        super().__init__()
        self.client = client
        self.project = project
        self.code = code
        self.number = number
        self.text = ""
        self.critical_only = False
        self.first = 0
        self.page: ActivityPage | None = None
        self.shown: list[ActivityRow] = []

    # --- layout --------------------------------------------------------------------------

    def compose(self) -> ComposeResult:
        with Vertical():
            yield Static(f"Activities of {self.code}", markup=False, id="ac-title")
            yield Input(placeholder="Filter by activity id or name", id="ac-filter")
            yield DataTable[str](id="ac-table", cursor_type="row", zebra_stripes=True)
            yield Static("", markup=False, id="ac-detail")
            yield Static("", markup=False, id="ac-status")
            yield Static(self.KEY_HINTS, markup=False, id="ac-hints")

    def on_mount(self) -> None:
        self.query_one("#ac-table", DataTable).add_columns(*ACTIVITY_COLUMNS)
        self.reload()
        self.query_one("#ac-table", DataTable).focus()

    # --- data ----------------------------------------------------------------------------

    def reload(self) -> None:
        """Read the page again and keep the highlighted activity where it is."""
        # STEPS
        # 1. `keep = self._current_id()`: the highlighted activity, to put the cursor
        #    back.
        # 2. Read `self.page = self.client.list_activities(self.project, self.code,
        #    snapshot=self.number, critical=True if self.critical_only else None,
        #    q=self.text.strip() or None, limit=PAGE, offset=self.first)`
        #    (`critical=False` would ask for the non-critical ones).
        # 3. On `CLIENT_ERRORS`: set `self.page = None` and `self.shown = []`, clear
        #    `#ac-table`, write `describe_error(exc)` to `#ac-detail` and (as an error)
        #    to the status line, and return.
        # 4. Otherwise call `self._fill(keep)`.
        raise NotImplementedError

    def _fill(self, keep: str | None = None) -> None:
        """Fill the table from ``self.page`` and describe the highlighted activity."""
        # STEPS
        # 1. `self.shown = list(self.page.rows)`. Clear `#ac-table` and add one row per
        #    activity with `Text(cell)` for each cell of `activity_cells(a)` (a cell is
        #    read as markup, a `Text` is not) and `key=a.activity_id`.
        # 2. Put the cursor on the row of `keep` when it is still shown, else on row 0,
        #    when there are rows.
        # 3. Write `Activities of <page.snapshot_key>` to `#ac-title`,
        #    `page_line(self.page, critical=self.critical_only, text=self.text)` to the
        #    status line, and call `self._describe()`.
        raise NotImplementedError

    def _current_id(self) -> str | None:
        row = self.current()
        return row.activity_id if row is not None else None

    def current(self) -> ActivityRow | None:
        table = self.query_one("#ac-table", DataTable)
        if not self.shown or not 0 <= table.cursor_row < len(self.shown):
            return None
        return self.shown[table.cursor_row]

    def _describe(self) -> None:
        """The highlighted activity with its relationships and its float trend."""
        # STEPS
        # 1. `panel` is `#ac-detail`. The highlighted activity is `self.current()`; with
        #    none write `No activity matches.` and return.
        # 2. Read `self.client.get_schedule_activity(self.project, self.code,
        #    row.activity_id, snapshot=self.number)` and make `lines =
        #    activity_detail_lines(detail)`. On `CLIENT_ERRORS` write
        #    `describe_error(exc)` to the panel and (as an error) to the status line,
        #    and return.
        # 3. In a second `try`: append an empty line and
        #    `trend_lines(self.client.get_activity_trend(self.project, self.code,
        #    row.activity_id))`. On `CLIENT_ERRORS` append an empty line and
        #    `describe_error(exc)` instead: an activity can have no published snapshot.
        # 4. Write the lines joined by newlines to the panel.
        raise NotImplementedError

    def _say(self, text: str, *, error: bool = False) -> None:
        self.query_one("#ac-status", Static).update(("! " if error else "") + text)

    # --- events --------------------------------------------------------------------------

    def on_data_table_row_highlighted(self, event: DataTable.RowHighlighted) -> None:
        event.stop()
        self._describe()

    def on_input_changed(self, event: Input.Changed) -> None:
        event.stop()
        self.text = event.value
        self.first = 0
        self.reload()

    def on_input_submitted(self, event: Input.Submitted) -> None:
        event.stop()
        self.query_one("#ac-table", DataTable).focus()

    # --- actions -------------------------------------------------------------------------

    def action_critical(self) -> None:
        """Show only the critical activities, or all of them again."""
        if isinstance(self.focused, Input):
            return  # the key is text
        self.critical_only = not self.critical_only
        self.first = 0
        self.reload()

    def action_next_page(self) -> None:
        """The next page, when there is one."""
        if isinstance(self.focused, Input):
            return  # the key is text
        if self.page is None or self.first + PAGE >= self.page.total:
            self._say("This is the last page.")
            return
        self.first += PAGE
        self.reload()

    def action_previous_page(self) -> None:
        """The previous page, when there is one."""
        if isinstance(self.focused, Input):
            return  # the key is text
        if self.first == 0:
            self._say("This is the first page.")
            return
        self.first = max(0, self.first - PAGE)
        self.reload()

    def action_filter(self) -> None:
        self.query_one("#ac-filter", Input).focus()

    def action_reload(self) -> None:
        self.reload()

    def action_close(self) -> None:
        if isinstance(self.focused, Input) and self.text:
            self.query_one("#ac-filter", Input).value = ""
            self.query_one("#ac-table", DataTable).focus()
            return
        self.dismiss(None)
```

`packages/tl-tui/src/tl_tui/schedule_text.py (excerpt; final, read only)` (read-only for you):
```python
ACTIVITY_COLUMNS                                        # the table header
def activity_cells(a: ActivityRow) -> tuple[str, ...]: ...
def page_line(page: ActivityPage, *, critical: bool, text: str) -> str: ...
def activity_detail_lines(detail: ActivityDetail) -> list[str]: ...
def trend_lines(points: Sequence[TrendPoint]) -> list[str]: ...
```

`packages/tl-tui/src/tl_tui/client.py (ClientInterface, schedule part; read only)` (read-only for you):
```python
def list_activities(self, project: str, code: str, *, snapshot: int | None = None,
                    critical: bool | None = None, status: str | None = None, q: str | None = None,
                    limit: int = 200, offset: int = 0) -> ActivityPage: ...
def get_schedule_activity(self, project: str, code: str, activity_id: str, *,
                          snapshot: int | None = None) -> ActivityDetail: ...
def get_activity_trend(self, project: str, code: str, activity_id: str) -> list[TrendPoint]: ...
```

## Context (read these, nothing else)
- `packages/tl-tui/src/tl_tui/widgets/activity_screen.py (the file you edit)`
- `packages/tl-tui/src/tl_tui/schedule_text.py`
- `packages/tl-tui/src/tl_tui/widgets/derived_documents.py (the same pattern, complete)`
- `packages/tl-tui/tests/fakes_schedule.py (the fake the test uses)`
- `docs/tickets/P1-I4/provided/t09a3-test_activity_screen.py.txt (the test)`
may explore: (none)

## Allowed paths
- `packages/tl-tui/src/tl_tui/widgets/activity_screen.py (edit)`
- `packages/tl-tui/tests/test_activity_screen.py (create; byte-identical copy of the provided test)`
- `docs/reports/P1-I4/P1-I4-T09a3.md (create; commit it)`

Notes:
- pytest runs in importlib mode: a test cannot import a sibling test file; `tests/fakes.py`, `fakes_schedule.py` and `helpers.py` are in the tree and read only (L-P0-I2-B1). The tests use `FakeClient.seed_schedule("P123")`.
- A table cell is a `rich.text.Text`, not a string: a title such as `[a, b]` is not markup (L-P0-I2-T13).
- The screens decide nothing: what a row says comes from `tl_tui/schedule_text.py` and the client; do not rebuild text in the widget, and do not edit `schedule_text.py`.
- A client failure (`CLIENT_ERRORS`) is shown on the status line with `describe_error`; it never crashes the screen.
- The keys do nothing while the filter input has focus (the letters are text).
- Do not name an attribute after a DOM property or a Textual private (`offset`, `_id`, `visible`, `query`): the stub already uses `first` and `_current_id`.
- The test file has no database fixture and runs in a few seconds.

## Lines you must not change
Everything in `activity_screen.py` outside the three functions that have a STEPS comment: the module docstring (apart from the STUB paragraph and the two header lines you remove), `PAGE`, the layout, `BINDINGS`, `KEY_HINTS`, the event handlers and the actions. The signatures and docstrings of the three functions. The attribute names `first` and `_current_id` (Textual owns `offset` and `_id`). The provided test.

## Steps
1. `uv sync --all-packages` (a new worktree has an empty `.venv`).
2. Copy `docs/tickets/P1-I4/provided/t09a3-test_activity_screen.py.txt` to `packages/tl-tui/tests/test_activity_screen.py`. Do not edit it.
3. Implement the three functions marked STEPS in `activity_screen.py`. Remove the `STUB` paragraph of the module docstring, the STEPS comments and the two header lines (`# ruff: noqa: F401, F841` and `# pyright: ...`); remove the imports that are then unused.
4. Run the acceptance commands. Write the report and commit it with the code.

## Acceptance
```
just check
uv run pytest packages/tl-tui/tests/test_activity_screen.py -q
```
Expected: `just check` clean; 15 pass in the provided file.

## Tests to add
None beyond the provided file.

## Report requirements
Standard report (`docs/templates/haiku-report.md`) plus: the decisive lines of each acceptance command, and one line for every STEPS line you did differently from what it says, with the reason (or "none").

## Escalation triggers
- Stop and report *Blocked* if a STEPS line and the provided test disagree, or if a test needs a change in `schedule_text.py`, the fake or any file outside *Allowed paths*.

## Blocked
(implementer writes here)

## Decision
(supervisor or orchestrator writes here)
