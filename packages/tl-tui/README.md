# tl-tui (`tl_tui`)

The Textual application shell, grid, record view, and forms; every screen reads and writes through `ClientInterface`, so the same screens run embedded or remote (§4, §10.1–§10.4, §10.6 sketches 1, 2, 11).

## Public interface
| Symbol | Kind | Purpose |
|---|---|---|
| `tl_tui.client.ClientInterface` | Protocol | The only way a screen reads or writes. Contract from P0-I2; `list_records` also takes `order_by` (additive, P0-I2 decision B7); P0-I3 added link, search, workflow, key-detection and `edit_record` methods (additive) |
| `tl_tui.embedded.EmbeddedClient` | class | `ClientInterface` over in-process `tl_core` services; `EmbeddedClient.for_sqlite(path)` |
| `tl_tui.errors.CLIENT_ERRORS`, `describe_error` | tuple, function | Expected failures a screen catches, and the one-line text to show |
| `tl_tui.messages` | module | Messages widgets post and the app routes (`OpenRecord`, `RecordHighlighted`, `SelectionChanged`, `RecordChanged`, `CloseRecord`, `StepRecord`, `StatusMessage`, `NavSelected`) |
| `tl_tui.paths.pset_value`, `relative_key` | functions | Layer-aware pset path lookup and `SetPsetValues` key derivation |
| `tl_tui.text` | module | Display helpers: `format_value`, `short_hash`, `timestamp`, `conformance_mark`, `unit_label` |
| `tl_tui.forms.save_record_edits`, `pset_batches` | functions | Group form edits by (pset, layer) and send them with the field changes as one `EditRecord`; the save is atomic (all parts or none) |
| `tl_tui.keymap.KEYMAP`, `help_text` | data, function | The documented key map; a test ties every entry to a real binding |
| `tl_tui.app.TlApp` | App | Shell: header, nav tree, main area, context panel, footer; F2/F3 panel collapse; overlays at 80 columns or less; `n` new record; `F1`/`?` help |
| `tl_tui.widgets.grid.RecordGrid` | widget | Virtualised grid: server-side sort, paging, End loads up to 5,000 rows in a worker, multi-select, column chooser, TSV |
| `tl_tui.widgets.record_view.RecordView` | widget | Header with badges (workflow state and time in state, link counts), Details, Psets, Links, History, Trace tabs (`1` to `5`); `e` edit, `[` `]` step, Esc back |
| `tl_tui.widgets.psets_tab.PsetsTab` | widget | Layer-grouped pset values with enforcement and conformance marks |
| `tl_tui.widgets.form_fields.FieldEditor` | widget | One editor per `FieldMeta` kind with inline validation |
| `tl_tui.widgets.edit_form.EditForm`, `new_record_form.NewRecordForm` | modals | Edit (Ctrl+S saves changed fields) and create (explicit key until numbering) |
| `tl_tui.commands`, `widgets.palette.CommandPalette` | module, modal | Command palette (`Ctrl+P` or `:`): fuzzy over commands, record types and keys |
| `tl_tui.widgets.link_picker.LinkPicker` | modal | Link picker (`l`): search, relation (follows the highlighted record's type until changed), pin, note, tick several, create and link |
| `tl_tui.widgets.links_tab.LinksTab` | widget | Links tab: grouped by relation, status marks, accept, decline, verify, repin, retract, expected-but-missing rows |
| `tl_tui.widgets.feed_pane.FeedPane` | widget | Activity feed (`F`): posts with highlighted tags, event cards, reactions, the `#hold` suggestion stub, filters All/Posts/Events/#hold (`1` to `4`), `j/k`, `Enter`/`o` open the first referenced record, `.` `+` `x` react, `L` linked records, `p` asks the app for the composer |
| `tl_tui.widgets.composer.ComposerScreen` | modal | Post composer (`p`): completion after `#` (records, signal tags, codes, topics) and `@` (people), Tab accepts, Enter posts through `client.feed_post` |
| `ClientInterface.feed_page`, `feed_post`, `feed_edit`, `feed_retract`, `feed_react`, `feed_complete` | methods | The feed calls; the embedded client uses `tl_core.services.feed*`; a remote client implements the same methods |
| `tl_tui.tray.ReferenceTray`, `widgets.ref_tray.ReferenceTrayScreen` | class, modal | Reference tray (`R` adds, `F4` opens): tick, remove, clear, link the ticked records to the open record; a partly refused batch stays open with the reasons |
| `tl_tui.navigation.NavHistory` | class | Back and forward trail (`Alt+Left`, `Alt+Right`) |
| `tl_tui.widgets.trace_tab.TraceTab` | widget | Trace tab (`t`): n-hop tree, depth `+`/`-`, direction `o`, Enter follows |
| `tl_tui.widgets.workflow_menu.WorkflowMenu` | modal | Workflow actions (`w`) listing each transition with its guards; a blocked one says why |
| `tl_tui.widgets.prompt.PromptScreen` | modal | One-line input used by the links tab for notes and reasons |
| `tl_tui.main.main` | function | `tl-tui` / `python -m tl_tui` entry point (embedded mode) |

## Depends on / used by
- Depends on: `textual`, `tl_core` (services), `tl_schema` (form metadata models), `tl_adapters` (only `EmbeddedClient.for_sqlite` and `just tui`).
- Used by: `just tui`, `dev/demos/P0-I2.sh`, `dev/demos/P0-I3.sh`. Runbook: `docs/runbooks/tui-dev.md`.

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
Introduced in P0-I1 (skeleton). First interface: P0-I2 workstream B (shell, grid, record view, forms, key map). P0-I3 added the link, workflow, trace and tray screens, the palette, and `ClientInterface` methods for links, search, workflow, key detection and `edit_record` (atomic form save). Remote client: P0-I4.
