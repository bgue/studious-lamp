# tl-tui (`tl_tui`)

The Textual application shell, grid, record view, and forms; every screen reads and writes through `ClientInterface`, so the same screens run embedded or remote (§4, §10.1–§10.4, §10.6 sketches 1, 2, 11).

## Public interface
| Symbol | Kind | Purpose |
|---|---|---|
| `tl_tui.client.ClientInterface` | Protocol | The only way a screen reads or writes. Contract from P0-I2; `list_records` also takes `order_by` (additive, P0-I2 decision B7) |
| `tl_tui.embedded.EmbeddedClient` | class | `ClientInterface` over in-process `tl_core` services; `EmbeddedClient.for_sqlite(path)` |
| `tl_tui.errors.CLIENT_ERRORS`, `describe_error` | tuple, function | Expected failures a screen catches, and the one-line text to show |
| `tl_tui.messages` | module | Messages widgets post and the app routes (`OpenRecord`, `RecordHighlighted`, `SelectionChanged`, `RecordChanged`, `CloseRecord`, `StepRecord`, `StatusMessage`, `NavSelected`) |
| `tl_tui.paths.pset_value`, `relative_key` | functions | Layer-aware pset path lookup and `SetPsetValues` key derivation |
| `tl_tui.text` | module | Display helpers: `format_value`, `short_hash`, `timestamp`, `conformance_mark`, `unit_label` |
| `tl_tui.forms.save_record_edits`, `pset_batches` | functions | Group form edits by (pset, layer), send core `UpdateRecord` then chained `SetPsetValues`; not atomic, a partial save is reported |
| `tl_tui.keymap.KEYMAP`, `help_text` | data, function | The documented key map; a test ties every entry to a real binding |
| `tl_tui.app.TlApp` | App | Shell: header, nav tree, main area, context panel, footer; F2/F3 panel collapse; overlays at 80 columns or less; `n` new record; `F1`/`?` help |
| `tl_tui.widgets.grid.RecordGrid` | widget | Virtualised grid: server-side sort, paging, End loads up to 5,000 rows in a worker, multi-select, column chooser, TSV |
| `tl_tui.widgets.record_view.RecordView` | widget | Header, Details, Psets, History tabs; `e` edit, `[` `]` step, Esc back |
| `tl_tui.widgets.psets_tab.PsetsTab` | widget | Layer-grouped pset values with enforcement and conformance marks |
| `tl_tui.widgets.form_fields.FieldEditor` | widget | One editor per `FieldMeta` kind with inline validation |
| `tl_tui.widgets.edit_form.EditForm`, `new_record_form.NewRecordForm` | modals | Edit (Ctrl+S saves changed fields) and create (explicit key until numbering) |
| `tl_tui.main.main` | function | `tl-tui` / `python -m tl_tui` entry point (embedded mode) |

## Depends on / used by
- Depends on: `textual`, `tl_core` (services), `tl_schema` (form metadata models), `tl_adapters` (only `EmbeddedClient.for_sqlite` and `just tui`).
- Used by: `just tui`, `dev/demos/P0-I2.sh`. Runbook: `docs/runbooks/tui-dev.md`.

## Commands
```
just test-tui            # every test in this package, including snapshots
just tui                 # run the TUI on the dev ledger (TL_DB, TL_PROJECT)
uv run pytest packages/tl-tui/tests/test_grid.py -q
```

## Configuration
| Setting or env var | Default | Notes |
|---|---|---|
| `TL_DB` | `./dev/data/tl.db` | SQLite ledger file for embedded mode |
| `TL_PROJECT` | `P123` | Project whose records the grid shows (scope `project:<id>`) |
| `TL_SCHEMA_DIR` | `schema/fixtures` | Package directory the pset services read (see `tl_core.schema_provider`) |

## Rules specific to this package
See `AGENTS.md` in this directory.

## Status
Introduced in P0-I1 (skeleton). First interface: P0-I2 workstream B (shell, grid, record view, forms, key map). Remote client: P0-I4.
