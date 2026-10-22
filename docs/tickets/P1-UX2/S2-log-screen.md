# P1-UX2-S2 — The shared LogScreen and the "Log screens" standard

Status: ready
Tier: sonnet
Kind: piece
Review: full
Labels: tui, tests, docs
Depends on: none (the actions it shows are supplied by the host screen; S1 wires the real source in S3 and S4)
Branch: `p1/ux2-s2-log-screen`

## Goal
One base screen every log uses: breadcrumb, list, selected-record panel (below, or to the right at 160+ columns),
actions bar, keys row, status line. A log written on it needs only to say what its rows, panel and actions are.
After this piece the standard exists, is tested and is written down; no existing log is changed (S3, S4 migrate them).

## Brief references (pasted, abridged)
> SCOPE §1. Layout, top to bottom: Breadcrumb always current `P123 › RFI Log › P123-RFI-0328: Conflict in
> piling/utilities at AZ203` (project, log name, highlighted record number and title; the record part is empty when
> nothing is selected). List (DataTable), plain labels in every cell. Selected record panel below the list; on
> terminals >= 160 columns it sits to the right of the list; the switch happens on resize. Actions bar: only the
> actions the viewer may take on the highlighted record in its current state, each with its key, e.g.
> `[a] Answer  [c] Close  [e] Escalate  [Enter] Open record`; nothing is shown that would be refused. Keys row:
> navigation and filters only (`/ filter`, `o open only`, `F5 reload`, `Esc back`). A count/summary line stays where
> each log has one. The standard is written in packages/tl-tui/README.md ("Log screens").
> SCOPE §2: a refusal from the command is shown in the status line.
> P1-UX README "Plain and technical display": labels from `tl_tui.display`; `refresh_for_display_mode()`;
> Enter opens `open_record` on `DataTable.RowSelected`; text modules are pure functions.

## Interfaces
```python
# tl_tui/log_text.py (new, pure)
WIDE_COLUMNS = 160
def breadcrumb_text(project: str, log: str, number: str | None, title: str | None, width: int) -> str
    # "P123 › RFI Log › P123-RFI-0328: Conflict in piling/..." ; no record: "P123 › RFI Log";
    # too long for width: the TITLE is shortened with "…"; project, log and number are never cut; never raises.
def actions_text(actions: Sequence[LogAction], *, can_open: bool) -> str
    # "[a] Answer  [c] Close  [Enter] Open record" ; empty list and not can_open -> "" ; key names shown as a person reads them
def is_wide(columns: int) -> bool          # columns >= WIDE_COLUMNS

# tl_tui/widgets/log_screen.py (new)
@dataclass(frozen=True)
class LogAction:
    key: str                  # textual key name, "a", "ctrl+e", "f6"
    label: str                # plain words; shown in the bar
    run: Callable[[], None]   # runs the existing command / form; may raise CLIENT_ERRORS

class LogScreen(ModalScreen[None], Generic[Row]):      # Row = the host's item type
    LOG_NAME: ClassVar[str]                              # "RFI Log"
    KEY_HINTS: ClassVar[str]                             # the keys row text (navigation and filters only)
    # --- the host fills these in ---
    def log_project(self) -> str
    def columns(self) -> Sequence[str]
    def load_rows(self) -> Sequence[Row]                 # called off the UI thread; replaced rows keep the cursor by row_key
    def row_key(self, row: Row) -> str
    def row_cells(self, row: Row) -> Sequence[str]       # plain text, never raw codes
    def row_record(self, row: Row) -> tuple[str, str]    # (number, title) for the breadcrumb
    def panel_text(self, row: Row | None) -> str         # the selected-record panel (wraps, scrolls)
    def actions_for(self, row: Row) -> Sequence[LogAction]   # called off the UI thread
    def summary_text(self) -> str                        # the count/summary line, "" if the log has none
    def open_row(self, row: Row) -> None                 # Enter / RowSelected, normally open_record(...)
    # --- the base provides ---
    ids: #log-crumb #log-filter #log-table #log-panel #log-actions #log-keys #log-status
    layout: vertical; class "-wide" (list left, panel right) when is_wide(self.size.width), recomputed on Resize
    async refresh of actions on every highlight with a generation counter: a slower answer for a row
        that is no longer highlighted is dropped; failure -> empty bar and one status line (describe_error)
    key dispatch: a pressed key equal to an offered action's key runs it (never while an Input has focus); a
        CLIENT_ERRORS refusal goes to #log-status prefixed "! "; after a run the rows reload and the bar refreshes
    refresh_for_display_mode(); F5 reload; "/" filter focus; Esc closes (clears filter first when it has text)
```
```python
# tl_tui/widgets/action_form.py (new): what an action asks before it runs (the answer text for Answer, a reason for Close/Void)
@dataclass(frozen=True)
class FormField: name: str; label: str; kind: Literal["line", "text", "choice"] = "line"; choices: tuple[str, ...] = (); required: bool = True; default: str = ""
class ActionFormScreen(ModalScreen[dict[str, str] | None]):
    def __init__(self, title: str, fields: Sequence[FormField] = (), *, confirm: str | None = None) -> None
    # no fields + confirm text: a yes/no confirmation; with fields: required fields block Enter/ctrl+s with a one-line reason;
    # Esc returns None; multi-line "text" wraps and scrolls; "choice" cycles with Left/Right; nothing is sent anywhere here.
```
The host builds the command from the returned dict and sends it with the client; `ActionFormScreen` knows no command.

The bar never shows a key that collides with a binding of the host screen: `LogScreen` raises `ValueError` in
`on_mount` of a test-mode app when two offered keys are equal or one equals a reserved key (`escape`, `enter`, `slash`, `f5`).

## Context (≤ 10 files)
- `packages/tl-tui/src/tl_tui/widgets/document_register.py` (the shape every log has today)
- `packages/tl-tui/src/tl_tui/widgets/record_screen.py`, `filter_bar.py`, `footer.py`
- `packages/tl-tui/src/tl_tui/display.py` (`mode_of`, `Labels`), `errors.py`, `text.py`
- `packages/tl-tui/tests/test_document_register.py`, `helpers.py`, `conftest.py` (how a screen is driven in a test)
- `packages/tl-tui/README.md` (section "Plain and technical display" for style)
may explore: `packages/tl-tui/src/tl_tui/widgets/main_area.py`

## Allowed paths
- `packages/tl-tui/src/tl_tui/log_text.py` (create), `packages/tl-tui/src/tl_tui/widgets/log_screen.py` (create), `packages/tl-tui/src/tl_tui/widgets/action_form.py` (create)
- `packages/tl-tui/src/tl_tui/app.tcss` (only a block for `LogScreen`), if the widget needs it
- `packages/tl-tui/tests/test_log_text.py`, `test_log_screen.py` (create), `packages/tl-tui/tests/__snapshots__/test_log_screen/**` (create)
- `packages/tl-tui/README.md` (a new section "Log screens", ≤ 45 lines, and one row in the public-interface table), `packages/tl-tui/AGENTS.md` if it exists (one line)
- `docs/reports/P1-UX2/S2.md` (create)
No existing log screen, no client file, no fake is touched.

## Steps
1. `log_text.py` with its tests (long titles, empty record, width 40/80/160, wide-character titles).
2. `LogScreen` with a test host (a small subclass in the test file with 3 rows and fake actions).
3. Tests: breadcrumb follows the highlighted row and is empty with no rows; layout flips at 159/160 columns on resize, cursor kept; actions bar shows only supplied actions, updates on highlight, drops a stale answer (slow `actions_for` for row 1 while row 2 is highlighted); a pressed action key runs it, an Input-focused key does not; a refusal lands in the status line with "! "; Esc/filter behaviour; two snapshots (80 and 170 columns).
4. `ActionFormScreen` with tests (required field blocks, Esc, choice cycling, confirm-only, multi-line wraps).
5. README "Log screens": layout, the hooks, how a log registers actions, the 160-column rule, key-collision rule, testing a log (the test host pattern), and that every new log uses it.

## Acceptance (run these, once)
```
just check
just gate packages/tl-tui/tests/test_log_text.py packages/tl-tui/tests/test_log_screen.py packages/tl-tui/tests/test_action_form.py packages/tl-tui/tests/test_plain_walk.py | tee .gate/summary.txt
```
Expected: gate PASS; no other snapshot changed.

## Tests to add
As Steps 1 and 3 (names: `test_breadcrumb_*`, `test_layout_switches_at_160_columns`, `test_stale_actions_answer_is_dropped`,
`test_refusal_goes_to_the_status_line`, `test_action_key_ignored_in_an_input`, `test_colliding_keys_are_refused`).

## Mutation (builder, own worktree, 3 lines in the report)
Sentinel plus at most 5: (1) `is_wide` boundary `>=` to `>`; (2) drop the generation check; (3) allow action keys while an Input is focused; (4) cut the number instead of the title in the breadcrumb; (5) swallow a refusal. Each killed.

## Report requirements
`docs/reports/P1-UX2/S2.md` ≤ 60 lines, deviations first, commands with ≤ 5 decisive lines, candidate learnings.

## Escalation triggers
- The base class cannot host a current log's behaviour without a business-logic change in the TUI: stop and list which log.
- A Textual limitation prevents the 160-column switch on resize: stop with the evidence.
