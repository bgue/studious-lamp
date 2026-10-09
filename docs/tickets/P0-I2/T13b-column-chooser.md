# P0-I2-T13b — Grid column chooser and copy as TSV

Status: ready
Tier: haiku
Labels: tui
Depends on: P0-I2-T13 (grid core, merged on `p0/i2b`)
Branch: `p0/i2b-t13b-column-chooser`

## Goal
Two grid actions. `c` opens a modal that lists every available column (core columns and pset properties) with check
boxes and applies the user's choice to the grid. `y` copies the selected rows, or the cursor row, as tab-separated text
to the terminal clipboard and tells the footer.

## Brief references (pasted)
> Data grid: Virtualised; column chooser incl. pset properties and linked-record fields; sort, filter, group, inline edit,
> multi-select, freeze columns, copy as TSV/CSV  (§10.2)
> Every action shown in the footer for the focused context ... (§10.3)

Learnings that apply:
- `uv` prints a harmless "UV_NATIVE_TLS is deprecated" warning on every call; ignore it.
- ruff `E501` is 100 columns, docstrings and comments included. Before `just check`, run
  `uv run ruff format packages/tl-tui` and `uv run ruff check --fix packages/tl-tui`.
- Do not name an attribute after a Textual `Widget`/`Screen` attribute: `visible` breaks a `ModalScreen` at runtime
  (it is a DOM property). The chooser's constructor parameter and attribute is `shown`.
- Tests have no async plugin: use `helpers.run_pilot` and `helpers.screen_text`.
- `widgets/column_chooser.py` imports `GridColumn` from `widgets/grid.py`, and the grid opens the chooser. Import
  `ColumnChooser` inside `RecordGrid.action_choose_columns` (a function-level import) to avoid a circular import.

## Interfaces (verbatim from repo at the branch point)
```python
# packages/tl-tui/src/tl_tui/widgets/grid.py (existing; you extend RecordGrid only)
@dataclass(frozen=True)
class GridColumn:
    key: str; label: str; width: int; align: Align = "left"
CORE_COLUMNS: tuple[GridColumn, ...]; DEFAULT_COLUMNS: tuple[GridColumn, ...]
def available_columns(meta: FormMetadata | None) -> list[GridColumn]: ...   # core columns + one per pset property
class RecordGrid(ScrollView, can_focus=True):
    KEY_HINTS: ClassVar[str]
    BINDINGS: ClassVar[list[BindingType]]
    client: ClientInterface; scope: str; record_type: str | None; columns: list[GridColumn]
    def set_columns(self, columns: list[GridColumn]) -> None: ...
    def copy_text(self) -> str: ...                  # TSV of selected rows, or the cursor row
    def selected_records(self) -> list[dict[str, Any]]: ...
    cursor_record -> dict[str, Any] | None           # property

# packages/tl-tui/src/tl_tui/client.py (existing)
def form_metadata(self, scope: str, record_type: str) -> FormMetadata: ...   # may raise CLIENT_ERRORS or NotImplementedError

# packages/tl-tui/src/tl_tui/errors.py
CLIENT_ERRORS: tuple[type[Exception], ...]

# packages/tl-tui/src/tl_tui/messages.py
class StatusMessage(Message):
    def __init__(self, text: str, severity: Severity = "info") -> None: ...

# NEW: packages/tl-tui/src/tl_tui/widgets/column_chooser.py
class ColumnChooser(ModalScreen[list[str] | None]):
    KEY_HINTS: ClassVar[str] = "Space toggle  Ctrl+S apply  Esc cancel"
    def __init__(self, available: list[GridColumn], shown: list[str]) -> None: ...
```

Rules for `ColumnChooser`:
- Layout (centred, about 50 cells wide): a `Static` title `"Choose columns"` (`markup=False`); a `SelectionList[str]` with
  id `columns`, one `Selection(column.label, column.key, column.key in shown)` per available column; a `Static` with id
  `chooser-error` (`markup=False`, empty at first); two `Button`s: `Apply` (id `apply`, variant `primary`) and `Cancel` (id `cancel`).
- Bindings: `escape` dismisses `None`; `ctrl+s` applies. The Apply button applies, the Cancel button dismisses `None`.
- Apply: the checked values, ordered as in `available`. If none is checked, set the error `Static` to
  `"Choose at least one column"` and do not dismiss. Otherwise dismiss with the list of keys.

Rules for the grid (edit `grid.py` only as described):
- Add bindings `c` (`choose_columns`) and `y` (`copy`), both `show=False`. Set
  `KEY_HINTS = "Enter open  Space select  Ctrl+A all  ←→ column  s sort  c columns  y copy  r reload"`.
- `action_choose_columns`: read `self.client.form_metadata(self.scope, self.record_type or "core.Record")`; on
  `CLIENT_ERRORS` or `NotImplementedError` use `None` (pset columns are then not offered). Build an ordered mapping
  `key -> GridColumn` from `available_columns(meta)` and then overwrite it with the grid's current `self.columns`
  (so a column the user already shows keeps its width). Push `ColumnChooser(list(mapping.values()), [c.key for c in self.columns])`
  with a callback that, for a non-empty result, calls `self.set_columns([mapping[k] for k in keys])`.
- `action_copy`: `count = len(self.selected_records())`, or `1` when nothing is selected but the cursor is on a row, else `0`.
  With `count == 0` post `StatusMessage("Nothing to copy", "warning")` and stop. Otherwise call
  `self.app.copy_to_clipboard(self.copy_text())` and post `StatusMessage(f"Copied {count} row(s) as TSV")` where the text is
  `Copied 1 row as TSV` or `Copied 2 rows as TSV` (singular for 1).

## Context (read these, nothing else)
- `AGENTS.md`, `packages/tl-tui/AGENTS.md`
- `packages/tl-tui/src/tl_tui/widgets/grid.py`
- `packages/tl-tui/tests/fakes.py` (read only; `FakeClient`)
- `packages/tl-tui/tests/helpers.py`
- `docs/tickets/P0-I2/provided/test_column_chooser.py.txt` (the test you must make pass)
may explore: (none)

## Allowed paths
- `packages/tl-tui/src/tl_tui/widgets/column_chooser.py` (create)
- `packages/tl-tui/src/tl_tui/widgets/grid.py` (edit: the bindings, `KEY_HINTS`, and the two actions only)
- `packages/tl-tui/tests/test_column_chooser.py` (create by copying the provided file; do not edit it)

## Steps
1. `cp docs/tickets/P0-I2/provided/test_column_chooser.py.txt packages/tl-tui/tests/test_column_chooser.py`
2. Create `column_chooser.py`; add the grid bindings and actions.
3. Run the acceptance commands.

## Acceptance
```
just check
uv run pytest packages/tl-tui/tests/test_column_chooser.py -q
uv run pytest packages/tl-tui -q
```
Expected: all pass (`test_grid.py` and `test_app_shell.py` must still pass unchanged).

## Tests to add
None beyond the provided file. It covers ordered results, unchecking, the empty-selection refusal, cancel, `c` from the
grid with pset columns offered, applying a pset column, `y` for a selection, for the cursor row, and for an empty grid.

## Report requirements
Standard report. State that the provided test file is byte-identical to the `.txt`, and list the lines you changed in `grid.py`.

## Escalation triggers
- Stop and report *Blocked* if making a provided test pass needs a change in `grid.py` beyond the bindings, hints and two actions.

## Blocked

## Decision
