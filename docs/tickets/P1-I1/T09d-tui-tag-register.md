# P1-I1-T09d — TUI: the tag register (F8)

Status: ready
Tier: haiku
Labels: tui
Depends on: the client methods `list_tags` and `get_tag`, the fake (`fakes_tags.py`) and the F8 binding, all on `p1/i1`; no other ticket (it does not need T09c: the screen uses the client interface)
Branch: `p1/i1-t09d-tui-tag-register`

## Goal
A person sees a project's tags in the TUI: their class, state and conformance, and what each lacks. `packages/tl-tui/src/tl_tui/tag_text.py` (pure text functions) and `packages/tl-tui/src/tl_tui/widgets/tag_register.py` (the screen) have their signatures, docstrings, layout and event handlers final; the marked bodies raise `NotImplementedError`. `F8` opens the screen (the app binding, the key map and the palette entry are already in). You implement the bodies. Two provided test files (`7` + `7` test functions) must pass.

## Brief references (pasted)
> **Brief 10 TUI.** Screens are built on the client interface (`ClientInterface`); they never import the services. A screen shows what the services return and decides nothing.
>
> **Brief 9 M2.** A tag has a number parsed into segments, a class, a workflow status and a conformance level; its class says which property sets it must carry. A constraining change flags existing records non-conformant; nothing is rewritten.

### Specification
- The screen is a modal like `SettingsScreen` (`widgets/settings_screen.py`): a title, a filter input, a table, a detail panel, a status line and a line of key hints. Its layout (`compose`, `on_mount`) and its event handlers are written; you fill the data and action methods the STEPS name.
- `reload` asks the client for the project's tags (`include_ended` as the screen has it); `_fill` applies the screen's own filters (class, violations only, text) to what was read; `_describe` asks for the highlighted tag with `get_tag` so the panel can show its issues.
- A cell is a `rich.text.Text`, not a string: a title such as `[a, b]` is not markup.
- A client failure (`CLIENT_ERRORS`) is shown on the status line with `describe_error`; it never crashes the screen.
- The keys `c`, `v` and `a` do nothing while the filter input has focus (the letters are text).

## Interfaces (verbatim from the repo at the branch point)
`packages/tl-tui/src/tl_tui/tag_text.py` (the stub you complete):
```python
"""What the tag register shows, as pure functions (P1-I1-T09d; brief 9 M2).

The rows, the detail panel and the summary line are text built from ``TagView`` values and nothing
else, so the tests check them without a terminal. None of it decides anything: a number that
breaks the pattern, a class that lacks a property set and a tag in the wrong state are the
module's findings, shown here as they come.

STUB (P1-I1-T09d): the bodies of the functions raise NotImplementedError; their signatures,
docstrings and the column names, `ALL_CLASSES` and the imports are final. Each body has a STEPS
comment. Implement them, then delete this paragraph, the STEPS comments and the `ruff: noqa` line.
"""

# ruff: noqa: F401 -- STUB: these imports are used once the bodies are written

from __future__ import annotations

from collections.abc import Sequence

from tl_mod_engineering.views import TagView

COLUMNS = ("Number", "Class", "Status", "No.", "Conf", "Title")
ALL_CLASSES = "all classes"


def row_cells(view: TagView) -> tuple[str, ...]:
    """The six cells of a table row, in the order of ``COLUMNS``."""
    # STEPS
    # 1. Number, class (``-`` when none), status (``-`` when none), the number check (``ok`` when
    #    ``number_status`` is ``ok``, else ``BAD``), the conformance level as stored, the title.
    raise NotImplementedError


def detail_lines(view: TagView) -> list[str]:
    """The panel under the table for the highlighted tag."""
    # STEPS
    # 1. ``<number>  <title>``.
    # 2. ``class <class or -> | status <status or -> | conformance <level>`` (one line; the three
    #    parts joined by ``  |  ``).
    # 3. ``number <number_status>: <segments>`` where the segments are ``name=value`` pairs in the
    #    order of ``view.segments`` joined by a space, or ``-`` when there are none.
    # 4. One line per entry of ``view.violations``: ``  ! <segment or "number">: <message>
    #    (<level>)``.
    # 5. With ``view.issues``: the line ``lacks:`` and then one line per issue: ``  <level>  <path>
    #    <message>`` (two spaces after the level, one after the path). Without: ``nothing lacking``
    #    when ``view.conformance`` is ``ok``, else ``no detail loaded`` (a listing has no issues).
    raise NotImplementedError


def next_class(current: str | None, classes: Sequence[str]) -> str | None:
    """The class filter after ``current``: ``None`` (all), then each class, then ``None``."""
    # STEPS
    # 1. The cycle is ``[None, *sorted(set(classes))]``.
    # 2. ``current`` is in the cycle: the next one, wrapping to ``None`` after the last. ``current``
    #    is not in it (the class has no tag any more): ``None``.
    raise NotImplementedError


def summary_line(
    shown: int,
    total: int,
    *,
    class_code: str | None,
    violations_only: bool,
    include_ended: bool,
    text: str,
) -> str:
    """The status line under the table."""
    # STEPS
    # 1. ``<shown> of <total> tags`` (``1 of 1 tags`` too).
    # 2. Then, each preceded by two spaces and only when it applies, in this order:
    #    ``class <code>``, ``violations only``, ``incl. ended``, ``filter "<text>"`` (text
    #    stripped; none when it is blank).
    raise NotImplementedError
```

`packages/tl-tui/src/tl_tui/widgets/tag_register.py` (the stub you complete):
```python
"""The tag register: a project's engineering tags, their class, state and conformance (P1-I1-T09d).

A full-size modal opened with ``F8``. The table lists the project's tags by number; ``BAD`` in the
``No.`` column marks a number that breaks the registry pattern, ``Conf`` is the stored conformance
level. The panel under the table describes the highlighted tag: its parts, why its number is
refused or accepted, and what it still lacks. Everything is read through the client; nothing here
changes a tag. The filter keys narrow the list on the screen (class, violations only, text);
``a`` asks the client for the ended tags too.

STUB (P1-I1-T09d): the bodies of the methods marked by a STEPS comment raise NotImplementedError;
their signatures, docstrings and the layout, the events and the other actions are final. Each body
has a STEPS comment. Implement them, then delete this paragraph, the STEPS comments and the `ruff:
noqa` line.
"""

# ruff: noqa: F401 -- STUB: these imports are used once the bodies are written

from __future__ import annotations

from typing import ClassVar

from rich.text import Text
from textual.app import ComposeResult
from textual.binding import Binding, BindingType
from textual.containers import Vertical
from textual.screen import ModalScreen
from textual.widgets import DataTable, Input, Static
from tl_mod_engineering.views import TagView

from tl_tui.client import ClientInterface
from tl_tui.errors import CLIENT_ERRORS, describe_error
from tl_tui.tag_text import COLUMNS, detail_lines, next_class, row_cells, summary_line

MAX_TAGS = 5000


class TagRegisterScreen(ModalScreen[None]):
    """The tags of ``project`` (the id, not the scope)."""

    KEY_HINTS: ClassVar[str] = (
        "c class  v violations only  a ended too  / filter  F5 reload  Esc close"
    )

    BINDINGS: ClassVar[list[BindingType]] = [
        Binding("c", "class_filter", "Class", show=False),
        Binding("v", "violations", "Violations only", show=False),
        Binding("a", "ended", "Ended too", show=False),
        Binding("slash", "filter", "Filter", show=False),
        Binding("f5", "reload", "Reload", show=False),
        Binding("escape", "close", "Close", show=False),
    ]

    DEFAULT_CSS = """
    TagRegisterScreen { background: $surface; }
    TagRegisterScreen > Vertical { padding: 0 1; }
    TagRegisterScreen #tags-title { text-style: bold; height: 1; }
    TagRegisterScreen #tags-filter { height: 3; }
    TagRegisterScreen #tags-table { height: 1fr; min-height: 6; }
    TagRegisterScreen #tags-detail { height: 12; border-top: solid $accent; padding: 0 1; }
    TagRegisterScreen #tags-status { height: 1; }
    TagRegisterScreen #tags-hints { height: 1; color: $text-muted; }
    """

    def __init__(self, client: ClientInterface, project: str) -> None:
        super().__init__()
        self.client = client
        self.project = project
        self.class_code: str | None = None
        self.violations_only = False
        self.include_ended = False
        self.text = ""
        self.views: list[TagView] = []  # as listed, before the screen's own filters
        self.shown: list[TagView] = []
        self.detail: TagView | None = None  # the highlighted tag with its issues

    # --- layout --------------------------------------------------------------------------

    def compose(self) -> ComposeResult:
        with Vertical():
            yield Static(f"Tags of {self.project}", markup=False, id="tags-title")
            yield Input(placeholder="Filter by number or title", id="tags-filter")
            yield DataTable[str](id="tags-table", cursor_type="row", zebra_stripes=True)
            yield Static("", markup=False, id="tags-detail")
            yield Static("", markup=False, id="tags-status")
            yield Static(self.KEY_HINTS, markup=False, id="tags-hints")

    def on_mount(self) -> None:
        self.query_one("#tags-table", DataTable).add_columns(*COLUMNS)
        self.reload()
        self.query_one("#tags-table", DataTable).focus()

    # --- data ----------------------------------------------------------------------------

    def reload(self) -> None:
        """Read the list again and keep the highlighted tag where it is."""
        # STEPS
        # 1. keep = self._number() (the highlighted number, or None).
        # 2. Inside `try:` self.views = self.client.list_tags(self.project,
        #    include_ended=self.include_ended, limit=MAX_TAGS). On `CLIENT_ERRORS` call
        #    self._say(describe_error(exc), error=True) and return.
        # 3. self._fill(keep).
        raise NotImplementedError

    def _fill(self, keep: str | None = None) -> None:
        """Apply the screen's filters to ``self.views`` and fill the table."""
        # STEPS
        # 1. needle = self.text.strip().lower(). self.shown = the views for which: the class
        #    filter is off or view.class_code equals it; the violations filter is off or
        #    view.number_status == "violation"; and the needle is empty or is in view.number.lower()
        #    or view.title.lower().
        # 2. table = the #tags-table DataTable; table.clear(); for each shown view add one row of
        #    Text(cell) for cell in row_cells(view), with key=view.number (Text, not str: a cell is
        #    read as markup).
        # 3. Move the cursor to the row of `keep` when it is shown, else to row 0 (only when rows
        #    exist): table.move_cursor(row=...).
        # 4. Update #tags-status with summary_line(len(self.shown), len(self.views),
        #    class_code=self.class_code, violations_only=self.violations_only,
        #    include_ended=self.include_ended, text=self.text).
        # 5. self._describe().
        raise NotImplementedError

    def _number(self) -> str | None:
        view = self.current()
        return view.number if view is not None else None

    def current(self) -> TagView | None:
        table = self.query_one("#tags-table", DataTable)
        if not self.shown or not 0 <= table.cursor_row < len(self.shown):
            return None
        return self.shown[table.cursor_row]

    def _describe(self) -> None:
        """Show the highlighted tag with what it lacks (one ``get_tag`` call per tag)."""
        # STEPS
        # 1. detail = the #tags-detail Static; view = self.current(). None: detail.update("No tag
        #    matches.") and return.
        # 2. Inside `try:` full = self.client.get_tag(self.project, view.number). On
        #    `CLIENT_ERRORS` set full = view (the listing's copy) and call
        #    self._say(describe_error(exc), error=True).
        # 3. self.detail = full; detail.update("\n".join(detail_lines(full))).
        raise NotImplementedError

    def _say(self, text: str, *, error: bool = False) -> None:
        self.query_one("#tags-status", Static).update(("! " if error else "") + text)

    # --- events --------------------------------------------------------------------------

    def on_data_table_row_highlighted(self, event: DataTable.RowHighlighted) -> None:
        event.stop()
        self._describe()

    def on_input_changed(self, event: Input.Changed) -> None:
        event.stop()
        self.text = event.value
        self._fill(self._number())

    def on_input_submitted(self, event: Input.Submitted) -> None:
        event.stop()
        self.query_one("#tags-table", DataTable).focus()

    # --- actions -------------------------------------------------------------------------

    def action_class_filter(self) -> None:
        """Show the next class: all, then each class that has a tag in the list, then all."""
        # STEPS
        # 1. If an Input has focus (isinstance(self.focused, Input)) return (the key is text).
        # 2. self.class_code = next_class(self.class_code, [v.class_code for v in self.views if
        #    v.class_code is not None]); self._fill(self._number()).
        raise NotImplementedError

    def action_violations(self) -> None:
        """Show only the tags whose number breaks the pattern, or all again."""
        # STEPS
        # 1. Return if an Input has focus. Flip self.violations_only; self._fill(self._number()).
        raise NotImplementedError

    def action_ended(self) -> None:
        """Include the superseded and deleted tags, or leave them out again (reads again)."""
        # STEPS
        # 1. Return if an Input has focus. Flip self.include_ended; self.reload().
        raise NotImplementedError

    def action_filter(self) -> None:
        self.query_one("#tags-filter", Input).focus()

    def action_reload(self) -> None:
        self.reload()

    def action_close(self) -> None:
        if isinstance(self.focused, Input) and self.text:
            self.query_one("#tags-filter", Input).value = ""
            self.query_one("#tags-table", DataTable).focus()
            return
        self.dismiss(None)
```

`packages/tl-modules/engineering/src/tl_mod_engineering/views.py`:
```python
class TagView(BaseModel):
    id: str; number: str; title: str; class_code: str | None; status: str | None
    area: str | None; mnemonic: str | None; sequence: int | None; segments: dict[str, str]
    pattern_code: str | None; number_status: str   # ok | violation
    violations: list[dict[str, Any]]               # each: segment (str | None), level, message (and rule)
    origin: str; conformance: str                  # ok | warning | nonconformant | waived
    version: int; psets: dict[str, Any]
    issues: list[ConformanceIssue] = []            # filled by get_tag, empty in a listing
```
`ConformanceIssue` (`tl_schema.forms`): `path: str`, `level: Literal["warning", "nonconformant"]`, `rule: str`, `message: str`.

`packages/tl-tui/src/tl_tui/client.py` (the two calls you use):
```python
def list_tags(self, project: str, *, class_code: str | None = None, status: str | None = None, number_status: str | None = None, include_ended: bool = False, limit: int = 1000) -> list[TagView]: ...
def get_tag(self, project: str, number: str) -> TagView: ...   # raises TagNotFoundError when unknown
```

`packages/tl-tui/src/tl_tui/errors.py`: `CLIENT_ERRORS` (a tuple of exception classes the screens catch) and `describe_error(exc) -> str`.

## Context (read these, nothing else)
- `packages/tl-tui/src/tl_tui/tag_text.py` and `packages/tl-tui/src/tl_tui/widgets/tag_register.py` (the files you edit)
- `packages/tl-tui/src/tl_tui/widgets/settings_screen.py` (a finished screen of the same shape; read it for style)
- `packages/tl-tui/tests/fakes_tags.py` (the fake the screen test uses; read only)
- `docs/tickets/P1-I1/provided/t09d-test_tag_text.py.txt` and `docs/tickets/P1-I1/provided/t09d-test_tag_register.py.txt` (the tests)
may explore: (none)

Learnings that apply (pasted from `docs/memory/LEARNINGS.md` and the build's conventions):
- Environment: run everything from the repository root. A new worktree needs `uv sync --all-packages` once before `uv run` can import the workspace packages (L-P0-I6A-1). `uv` prints "UV_NATIVE_TLS is deprecated"; ignore it. Do not pipe `just check` into `tail`.
- pyright is `standard` for `packages/tl-tui`; ruff limits lines to 100 columns, docstrings and comments included (L-P0-I1-6). Run `uv run ruff format` before committing.
- Provided files live under `docs/tickets/P1-I1/provided/` as `.py.txt`; copy them into the tree byte for byte (the target names are in *Steps*). Do not edit the copies: they are already `ruff format` and pyright clean.
- Commit your report at `docs/reports/P1-I1/<ticket-id>.md` (it is inside your Allowed paths). Say "commit your report" in your final message (L-P0-I2-B7).
- A failing test that is not in your Allowed paths is not yours to fix: report it under *Blocked*.
- No new dependencies. Remove the `STUB` paragraph from the module docstring, every `STEPS` comment and the `# ruff: noqa: F401` line when you implement a stub.
- The test counts below were counted from the provided files (`grep -c "^def test_"`); parametrized tests expand to more cases when run, and the pytest summary is the number of cases (L-P0-I8A-8).
- Never name a module `types.py`, `enum.py` or `json.py` inside a package (L-P0-I5-B1).
- Never write a hand-made `cur_*` table or change `schema/**` or anything under `generated/` unless this ticket says so.
- TUI tests (L-P0-I2-4): the pilot tests run headless through `helpers.run_pilot`; `screen_text(app)` is the rendered screen as text.
- After a table `clear()` and new rows, move the cursor with `table.move_cursor(row=...)`; the highlighted-row event then calls `_describe`, so do not call it twice in a row for no reason (one `get_tag` per highlight is fine).
- Do not change the snapshot files: the palette snapshot already includes the new `Tags` command.
- `FakeClient.add_tag(...)` (in `fakes_tags.py`) seeds the fake: a listing carries no issues, `get_tag` carries the ones the test gave the tag.


## Allowed paths
- `packages/tl-tui/src/tl_tui/tag_text.py` (edit)
- `packages/tl-tui/src/tl_tui/widgets/tag_register.py` (edit)
- `packages/tl-tui/tests/test_tag_text.py` (create; byte-identical copy of the provided test)
- `packages/tl-tui/tests/test_tag_register.py` (create; byte-identical copy of the provided test)
- `docs/reports/P1-I1/P1-I1-T09d.md` (create)

## Steps
1. `uv sync --all-packages`.
2. Copy the two provided tests (`t09d-test_tag_text.py.txt`, `t09d-test_tag_register.py.txt`) to `packages/tl-tui/tests/test_tag_text.py` and `test_tag_register.py`.
3. Implement the functions of `tag_text.py` first, then the marked methods of `tag_register.py`, by their STEPS comments; remove the STUB paragraphs, the STEPS comments and the `ruff: noqa` lines.
4. Run the acceptance commands.

## Acceptance
```
just check
uv run pytest packages/tl-tui/tests/test_tag_text.py packages/tl-tui/tests/test_tag_register.py -q
uv run pytest packages/tl-tui -q
```
Expected: `just check` clean; 7 + 7 test functions pass (the text test has parametrized cases, so the count of cases is higher); the whole tl-tui package passes.

## Tests to add
None beyond the provided file(s).

## Report requirements
Standard report (`docs/templates/haiku-report.md`) plus: the output of the parity run (decisive lines).

## Escalation triggers
- Stop and report *Blocked* if a STEPS line and the provided test disagree.
- Stop if a test needs a change outside the Allowed paths.

## Blocked
(implementer writes here)

## Decision
(supervisor or orchestrator writes here)
