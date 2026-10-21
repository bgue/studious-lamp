# P1-UX-T08c — Record grid: type column and property headers in plain words

Status: ready (stage)
Tier: haiku
Kind: ticket
Review: full
Labels: tui, tests
Depends on: T00, S2, S3 (merged)
Branch: `p1/ux-t08c-grid-plain`

## Goal
The record grid shows the `Type` column as the type's label (`Control valve`, not `engineering.ControlValve`) and the property columns from the column chooser under the property's label (`Pressure rating`) instead of the dotted path (`safety_data.pressure_rating`);
technical mode keeps today's text. The text export (`raw_text`) and the stored column keys do not change. The grid redraws on `refresh_for_display_mode` (D14).
The `Ver` column stays (default columns are in every snapshot; the walking test T11 decides).

## Brief references (pasted)
> SCOPE clause 2: plain words; no internal keys; type and property labels with units. Clause 3: technical shows what plain hides. D14: `refresh_for_display_mode(self) -> None`. D27: pure functions keep raw output by default (`technical=True`); the widget passes the mode.

## Interfaces (verbatim from repo)
```python
# tl_tui/widgets/grid.py (today)
@dataclass(frozen=True)
class GridColumn: key: str; label: str; width: int; align: Align = "left"      # key is an envelope key or a "psets.…" path
def available_columns(meta: FormMetadata | None) -> list[GridColumn]    # CORE_COLUMNS + for each pset group field: GridColumn(fld.path, fld.path.removeprefix("psets."), 14)
def cell_text(record: dict[str, Any], column: GridColumn) -> str         # psets.* -> format_value(pset_value(...)); else format_value(record.get(key)); conformance mark; timestamps
def raw_text(record, column) -> str                                       # export: unchanged
# RecordGrid(client, scope, *, record_type="core.Record", columns=None, page_size=200, highlight_seconds=…, id=None): self.client self.scope self.columns;
#   _header_segments(): label = column.label (+ " ▼"/" ▲" for the sort column); _row_segments(index): fit_cell(cell_text(record, column), ...);
#   labels used at: sort status text (self.columns label lookup ~line 518), "Sorting by {column.label} is not available" (~668), action_columns: ColumnChooser(list(mapping.values()), shown_keys) shows column.label
# FieldMeta: path, label (str | None), unit, enum_values;  tl_tui/display.py: Labels, type_label(labels, type), humanize, mode_of(app).technical;  tl_tui/labels_load.py: load_labels(client, scope, record_types)
```

## Context (read these, nothing else)
- `packages/tl-tui/src/tl_tui/widgets/grid.py` (lines 60-120, 195-260, 505-530, 620-680, 725-759), `widgets/column_chooser.py` (read only)
- `packages/tl-tui/tests/test_grid.py`, `test_column_chooser.py`

## Allowed paths
- `packages/tl-tui/src/tl_tui/widgets/grid.py`
- `packages/tl-tui/tests/test_grid.py`, `test_grid_filter.py`, `test_column_chooser.py` (update pinned expectations only)
- `packages/tl-tui/tests/test_grid_plain.py` (create)
- Snapshot files, only by regenerating the failing test: `packages/tl-tui/tests/__snapshots__/test_snapshots/test_column_chooser.raw`
- `docs/reports/P1-UX/T08c.md` (create)

## Steps
1. `GridColumn` gains `plain_label: str | None = None` (last field, default None). `available_columns`: for pset fields `plain_label = fld.label or humanize(fld.path.rpartition(".")[2])`; `label` stays the path-minus-`psets.` (technical).
2. `cell_text(record, column, labels=None, *, technical=True)`: technical = today's text exactly. Plain: for `column.key == "type"` the text is `type_label(labels or Labels(), str(value))`. Nothing else changes.
3. `RecordGrid`: `self.labels = Labels()`; `on_mount` sets `self.labels = load_labels(self.client, self.scope, ())` before `load()`. A method `_label_of(column)` returns `column.plain_label` when set and the mode is plain, else `column.label`; use it in `_header_segments`, the sort status text and the "Sorting by" message.
   `_row_segments` passes `self.labels` and the mode to `cell_text`. `action_columns` hands the chooser copies with `label` replaced by `_label_of(c)` (`dataclasses.replace`) but keeps `mapping` of the originals for the result.
4. `refresh_for_display_mode(self)`: `self.refresh()` (header and rows redraw).
5. Update pinned expectations that read plain through the widget; keep one technical assertion for the type cell and one for a property header.

## Acceptance
```
just check
just gate packages/tl-tui/tests/test_grid.py packages/tl-tui/tests/test_grid_filter.py packages/tl-tui/tests/test_column_chooser.py packages/tl-tui/tests/test_grid_plain.py packages/tl-tui/tests/test_snapshots.py packages/tl-tui/tests/test_app_filter.py packages/tl-tui/tests/test_technical_toggle.py
```
Gate paths: all exist at dispatch except `test_grid_plain.py` (new, this ticket creates it). Expected `gate: PASS`. If a snapshot test fails, regenerate only `test_column_chooser` (`uv run pytest packages/tl-tui/tests/test_snapshots.py -k test_column_chooser --snapshot-update -q`) and name what changed. Do not run the whole suite.

## Tests to add
`packages/tl-tui/tests/test_grid_plain.py` (TlApp or `RecordGrid` on `FakeClient.with_valve_example()` as `test_grid.py` does):
- `test_plain_type_cell_is_the_label_and_technical_the_raw_type` (add the `type` column).
- `test_property_header_is_the_label_in_plain_and_the_path_in_technical` (columns from `available_columns(meta)`).
- `test_the_column_chooser_lists_labels_in_plain_and_returns_the_original_columns`.
- `test_export_text_and_column_keys_do_not_change_with_the_mode` (`raw_text`, `column.key`).
- `test_grid_refreshes_on_the_mode_switch`.

## Report requirements
Standard report. List existing assertions changed and why (one line each).

## Escalation triggers
- `extension_columns.py` builds `GridColumn`s with labels that leak a path (not in Allowed paths): list it in the report.
- A snapshot other than `test_column_chooser` changes: stop and report.

## Blocked
(implementer writes here)

## Decision
(supervisor or orchestrator writes here)
