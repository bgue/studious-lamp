# P1-I4-T09a2 — TUI: the comparison of two snapshots

Status: ready
Tier: haiku
Labels: tui
Depends on: S9 and the TUI text helpers on `p1/i4` (in the tree); T09a1 opens this screen with `c` but the provided test pushes it directly
Branch: `p1/i4-t09a2-tui-compare-screen`

## Goal
A planner sees what changed between a snapshot and the one before it: how far the data date and the project finish moved, then one list at a time (added, removed, date shifts, float, logic, progress, durations, critical), each tab with its full count. `packages/tl-tui/src/tl_tui/widgets/compare_screen.py` has the layout, the bindings and the actions written; `reload` and `_show` raise `NotImplementedError`. You implement them. One provided test file must pass.

## Brief references (pasted)
> **Brief 10 TUI.** Screens are built on the client interface (`ClientInterface`); they never import the services. A screen shows what the services return and decides nothing.
>
> **ADR-0015 (M11).** A schedule is the series of snapshots of one P6 project, each upload an immutable snapshot, one of them the current schedule. Records link to an activity by its stable id. What moved between two snapshots, which float eroded and which links went stale are the module's findings; the screens show them as they come (`tl_tui/schedule_text.py`).

### Specification
- `reload` reads the comparison through `client.compare_snapshots(project, code, new=..., old=...)`; on a failure it clears the header and the tab line and shows the module's message in the body and on the status line (an example: the first snapshot has nothing to compare with).
- `_show` writes the header, the tab line with the section on view in square brackets (meaning does not ride on colour), the section's title and rows, and `section n of 8` on the status line.
- `self.section` is changed by the written actions; `_show` only reads it.

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
`packages/tl-tui/src/tl_tui/widgets/compare_screen.py` (the stub you complete; the whole file):
```python
# ruff: noqa: F401, F841
# pyright: reportUnusedImport=false, reportUnusedFunction=false, reportUnusedVariable=false
"""The comparison of two snapshots of a schedule: what moved, eroded and changed (P1-I4).

A full-size modal opened from the schedule screen with ``c``. The header says which snapshots
are compared and how far the data date and the project finish moved; below it, one section of the
comparison at a time (added, removed, date shifts, float, logic, progress, durations, critical),
with the full count of every section in the tab line. ``Right``/``Left`` (or ``n``/``b``) move to
the next or previous section, ``Esc`` closes. Everything is read through the client; the screen
shows what the module found and decides nothing.


STUB (P1-I4-T09a2): `reload` and `_show` are `NotImplementedError`; the layout, the bindings, the
actions and the text helpers (`tl_tui/schedule_text.py`) are written. The ticket fills the two
bodies by their STEPS comments.
"""

from __future__ import annotations

from typing import ClassVar

from textual.app import ComposeResult
from textual.binding import Binding, BindingType
from textual.containers import Vertical, VerticalScroll
from textual.screen import ModalScreen
from textual.widgets import Static
from tl_mod_schedule.compare import Comparison

from tl_tui.client import ClientInterface
from tl_tui.errors import CLIENT_ERRORS, describe_error
from tl_tui.schedule_text import (
    COMPARE_SECTIONS,
    compare_header_lines,
    compare_section_lines,
    compare_tabs,
)


class CompareScreen(ModalScreen[None]):
    """``new`` against the snapshot before it (``old`` names another one) of schedule ``code``."""

    KEY_HINTS: ClassVar[str] = "Right/n next section  Left/b previous  F5 reload  Esc close"

    BINDINGS: ClassVar[list[BindingType]] = [
        Binding("right,n", "next_section", "Next", show=False),
        Binding("left,b", "previous_section", "Previous", show=False),
        Binding("f5", "reload", "Reload", show=False),
        Binding("escape", "close", "Close", show=False),
    ]

    DEFAULT_CSS = """
    CompareScreen { background: $surface; }
    CompareScreen > Vertical { padding: 0 1; }
    CompareScreen #cp-title { text-style: bold; height: 1; }
    CompareScreen #cp-header { height: 3; }
    CompareScreen #cp-tabs { height: 1; }
    CompareScreen #cp-body { height: 1fr; border-top: solid $accent; padding: 0 1; }
    CompareScreen #cp-status { height: 1; }
    CompareScreen #cp-hints { height: 1; color: $text-muted; }
    """

    def __init__(
        self,
        client: ClientInterface,
        project: str,
        code: str,
        new: int,
        old: int | None = None,
    ) -> None:
        super().__init__()
        self.client = client
        self.project = project
        self.code = code
        self.new = new
        self.old = old
        self.section = 0  # an index into COMPARE_SECTIONS
        self.comparison: Comparison | None = None

    # --- layout --------------------------------------------------------------------------

    def compose(self) -> ComposeResult:
        with Vertical():
            yield Static(f"Comparison of {self.code}#{self.new}", markup=False, id="cp-title")
            yield Static("", markup=False, id="cp-header")
            yield Static("", markup=False, id="cp-tabs")
            with VerticalScroll(id="cp-scroll"):
                yield Static("", markup=False, id="cp-body")
            yield Static("", markup=False, id="cp-status")
            yield Static(self.KEY_HINTS, markup=False, id="cp-hints")

    def on_mount(self) -> None:
        self.reload()

    # --- data ----------------------------------------------------------------------------

    def reload(self) -> None:
        """Read the comparison again and show the section the screen was on."""
        # STEPS
        # 1. Read `self.comparison = self.client.compare_snapshots(self.project,
        #    self.code, new=self.new, old=self.old)`.
        # 2. On `CLIENT_ERRORS`: set `self.comparison = None`, clear `#cp-header` and
        #    `#cp-tabs`, write `describe_error(exc)` to `#cp-body` and (as an error) to
        #    the status line, and return.
        # 3. Otherwise call `self._show()`.
        raise NotImplementedError

    def _show(self) -> None:
        """The header, the tab line (the section on view in brackets) and the section's rows."""
        # STEPS
        # 1. With no `self.comparison` return. Write `compare_header_lines(c)` joined by
        #    newlines to `#cp-header`.
        # 2. The tab line: `compare_tabs(c)` with the label of the section on view
        #    (`self.section`) in square brackets, joined by two spaces, written to
        #    `#cp-tabs`.
        # 3. `name, title = COMPARE_SECTIONS[self.section]`; write `title` and a colon
        #    on a first line, then `compare_section_lines(c, name)`, joined by newlines,
        #    to `#cp-body`.
        # 4. Say `section <n> of <how many>` (n counts from 1), followed by `  (the
        #    lists were cut; the counts are exact)` when `c.cut`.
        raise NotImplementedError

    def _say(self, text: str, *, error: bool = False) -> None:
        self.query_one("#cp-status", Static).update(("! " if error else "") + text)

    # --- actions -------------------------------------------------------------------------

    def action_next_section(self) -> None:
        self.section = (self.section + 1) % len(COMPARE_SECTIONS)
        self._show()

    def action_previous_section(self) -> None:
        self.section = (self.section - 1) % len(COMPARE_SECTIONS)
        self._show()

    def action_reload(self) -> None:
        self.reload()

    def action_close(self) -> None:
        self.dismiss(None)
```

`packages/tl-tui/src/tl_tui/schedule_text.py (excerpt; final, read only)` (read-only for you):
```python
COMPARE_SECTIONS = (("added", "Added"), ("removed", "Removed"), ("date_shifts", "Date shifts"),
                    ("float_changes", "Float"), ("logic_changes", "Logic"),
                    ("progress_changes", "Progress"), ("duration_changes", "Durations"),
                    ("critical_changes", "Critical"))
def compare_header_lines(c: Comparison) -> list[str]: ...    # two lines
def compare_tabs(c: Comparison) -> list[str]: ...            # one label per section: "Float 8"
def compare_section_lines(c: Comparison, name: str, limit: int = 500) -> list[str]: ...
```

`packages/tl-tui/src/tl_tui/client.py (ClientInterface, schedule part; read only)` (read-only for you):
```python
def compare_snapshots(self, project: str, code: str, *, new: int | None = None, old: int | None = None,
                      limit: int = 200) -> Comparison: ...
    # the module's errors (CLIENT_ERRORS) when a snapshot is missing or has no earlier one
```

## Context (read these, nothing else)
- `packages/tl-tui/src/tl_tui/widgets/compare_screen.py (the file you edit)`
- `packages/tl-tui/src/tl_tui/schedule_text.py`
- `packages/tl-tui/src/tl_tui/widgets/derived_documents.py (the same pattern, complete)`
- `docs/tickets/P1-I4/provided/t09a2-test_compare_screen.py.txt (the test)`
may explore: (none)

## Allowed paths
- `packages/tl-tui/src/tl_tui/widgets/compare_screen.py (edit)`
- `packages/tl-tui/tests/test_compare_screen.py (create; byte-identical copy of the provided test)`
- `docs/reports/P1-I4/P1-I4-T09a2.md (create; commit it)`

Notes:
- pytest runs in importlib mode: a test cannot import a sibling test file; `tests/fakes.py`, `fakes_schedule.py` and `helpers.py` are in the tree and read only (L-P0-I2-B1). The tests use `FakeClient.seed_schedule("P123")`.
- A table cell is a `rich.text.Text`, not a string: a title such as `[a, b]` is not markup (L-P0-I2-T13).
- The screens decide nothing: what a row says comes from `tl_tui/schedule_text.py` and the client; do not rebuild text in the widget, and do not edit `schedule_text.py`.
- A client failure (`CLIENT_ERRORS`) is shown on the status line with `describe_error`; it never crashes the screen.
- The keys do nothing while the filter input has focus (the letters are text).
- Do not name an attribute after a DOM property or a Textual private (`offset`, `_id`, `visible`, `query`): the stub already uses `first` and `_current_id`.
- The test file has no database fixture and runs in a few seconds.

## Lines you must not change
Everything in `compare_screen.py` outside the two functions that have a STEPS comment: the module docstring (apart from the STUB paragraph and the two header lines you remove), the layout, `BINDINGS`, `KEY_HINTS` and the actions. The signatures and docstrings of the two functions. The provided test.

## Steps
1. `uv sync --all-packages` (a new worktree has an empty `.venv`).
2. Copy `docs/tickets/P1-I4/provided/t09a2-test_compare_screen.py.txt` to `packages/tl-tui/tests/test_compare_screen.py`. Do not edit it.
3. Implement the two functions marked STEPS in `compare_screen.py`. Remove the `STUB` paragraph of the module docstring, the STEPS comments and the two header lines (`# ruff: noqa: F401, F841` and `# pyright: ...`); remove the imports that are then unused.
4. Run the acceptance commands. Write the report and commit it with the code.

## Acceptance
```
just check
uv run pytest packages/tl-tui/tests/test_compare_screen.py -q
```
Expected: `just check` clean; 9 pass in the provided file.

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
