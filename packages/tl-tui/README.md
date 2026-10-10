# tl-tui (`tl_tui`)

The Textual application shell, grid, record view, and forms; every screen reads and writes through `ClientInterface`, so the same screens run embedded (a SQLite file in this process) or remote (a running API server), and in both modes they show other writers' changes live (§4, §5.3, §10.1–§10.4, §10.6 sketches 1, 2, 11).

## Public interface
| Symbol | Kind | Purpose |
|---|---|---|
| `tl_tui.client.ClientInterface` | Protocol | The only way a screen reads or writes. Contract from P0-I2; `list_records` also takes `order_by` (additive, P0-I2 decision B7); P0-I3 added link, search, workflow, key-detection and `edit_record` methods; P0-I4 added `query_records(scope, q, ...)` and `count_records(scope, q)` (the query language, decision O3) |
| `tl_tui.embedded.EmbeddedClient` | class | `ClientInterface` over in-process `tl_core` services; `EmbeddedClient.for_sqlite(path)` keeps one engine and bus; `.change_feed(scope)` and `.own_writes` |
| `tl_tui.remote.RemoteClient`, `RemoteFeed` | classes | `ClientInterface` over `tl_api.client.ApiClient` (`RemoteClient.connect(url, token)`): converts `RelationOut`, reports `unreachable` / `live` to `connection_listener`, 3 s call timeout, `.change_feed(scope)` is the SSE stream resumed by `seq` |
| `tl_tui.live` | module | `ChangeFeed` / `FeedSink` protocols, `EmbeddedFeed`, `LiveUpdates` (feed thread posting `LiveEvents` / `ConnectionChanged`), `OwnWrites`, and the pure rules `touched_record_ids`, `detect_conflict`, `describe_changes` |
| `tl_tui.errors.CLIENT_ERRORS`, `describe_error` | tuple, function | Expected failures a screen catches (now including `ApiError`, `ApiUnavailableError` = "server unreachable"), and the one-line text to show |
| `tl_tui.messages` | module | Messages widgets post and the app routes (`OpenRecord`, `RecordHighlighted`, `SelectionChanged`, `RecordChanged`, `CloseRecord`, `StepRecord`, `StatusMessage`, `NavSelected`) |
| `tl_tui.paths.pset_value`, `relative_key` | functions | Layer-aware pset path lookup and `SetPsetValues` key derivation |
| `tl_tui.text` | module | Display helpers: `format_value`, `short_hash`, `timestamp`, `conformance_mark`, `unit_label` |
| `tl_tui.forms.save_record_edits`, `pset_batches` | functions | Group form edits by (pset, layer) and send them with the field changes as one `EditRecord`; the save is atomic (all parts or none) |
| `tl_tui.keymap.KEYMAP`, `help_text` | data, function | The documented key map; a test ties every entry to a real binding |
| `tl_tui.app.TlApp` | App | Shell: header, nav tree, main area, context panel, footer; F2/F3 panel collapse; overlays at 80 columns or less; `n` new record; `F1`/`?` help |
| `tl_tui.widgets.grid.RecordGrid` | widget | Virtualised grid: server-side sort, paging, End loads up to 5,000 rows in a worker, multi-select, column chooser, TSV; `apply_filter(text)` (query language, `FilterResult` with the error position), `refresh_live(ids)` (worker thread; rows changed by others get a `•` for 4 s) |
| `tl_tui.widgets.filter_bar.FilterBar` | widget | Filter bar (`/`): Enter applies, shows `N matches` or the parser's message with a caret under the bad character, blank clears, Esc leaves |
| `tl_tui.widgets.connection_banner.ConnectionBanner` | widget | "Server unreachable" / "reconnecting" line under the header; hidden while live |
| `tl_tui.widgets.record_view.RecordView` | widget | Header with badges (workflow state and time in state, link counts), Details, Psets, Links, History, Trace tabs (`1` to `5`); `e` edit, `[` `]` step, Esc back; "! Updated by X (now vN)" line when someone else changed the record |
| `tl_tui.widgets.psets_tab.PsetsTab` | widget | Layer-grouped pset values with enforcement and conformance marks |
| `tl_tui.widgets.form_fields.FieldEditor` | widget | One editor per `FieldMeta` kind with inline validation |
| `tl_tui.widgets.edit_form.EditForm`, `new_record_form.NewRecordForm` | modals | Edit (Ctrl+S saves changed fields; a conflict banner and a blocked save when the record moved under the form) and create (explicit key until numbering) |
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
| `tl_tui.main.make_app`, `run`, `main` | functions | `tl-tui` / `python -m tl_tui` / `tl tui`: embedded by default, remote with `--remote URL` and a token |

## Depends on / used by
- Depends on: `textual`, `tl_core` (services, query language, change feed), `tl_schema` (form metadata models), `tl_adapters` (only `EmbeddedClient.for_sqlite`), `tl_api` and `httpx2` (only `remote.py`).
- Used by: `just tui`, `tl tui`, `dev/demos/P0-I2.sh`, `P0-I3.sh`, `P0-I4.sh`. Runbook: `docs/runbooks/tui-dev.md`.

## Commands
```
just test-tui            # every test in this package, including snapshots
just tui                 # run the TUI on the dev ledger (TL_DB, TL_PROJECT), embedded
TL_TOKEN=<token> uv run tl tui --remote http://127.0.0.1:8765   # remote, against `tl serve`
just demo P0-I4          # remote TUI, SSE client and MCP agent see one change in < 2 s
uv run pytest packages/tl-tui/tests/test_grid.py -q
```

## Configuration
| Setting or env var | Default | Notes |
|---|---|---|
| `TL_DB` | `./dev/data/tl.db` | SQLite ledger file for embedded mode |
| `TL_PROJECT` | `P123` | Project whose records the grid shows (scope `project:<id>`) |
| `TL_SCHEMA_DIR` | `schema/fixtures` | Package directory the pset services read (see `tl_core.schema_provider`) |
| `TL_REMOTE` | (unset) | API URL; when set the TUI runs remote (`--remote` overrides) |
| `TL_TOKEN` | (unset) | Dev token for remote mode (ADR-0005); prefer it to `--token`, which shows in `ps` |

## Rules specific to this package
See `AGENTS.md` in this directory.

## Status
Introduced in P0-I1 (skeleton). First interface: P0-I2 workstream B (shell, grid, record view, forms, key map). P0-I3 added the link, workflow, trace and tray screens, the palette, and `ClientInterface` methods for links, search, workflow, key detection and `edit_record` (atomic form save). P0-I4 workstream D added the remote client, live updates in both modes, the filter bar and the conflict banner (plan: `docs/tickets/P0-I4/README-D.md`). P0-I6 workstream B: the six feed methods of `RemoteClient` now go to the API (`GET /feed`, the feed command routes), and an open feed pane reads its first page again when any event of its project arrives (`TlApp._refresh_feed_pane`). Review-queue screens and `RemoteClient` proposal methods are not built (`ClientInterface` has no proposal methods). Known limit: the grid load, record view and filter calls still run on the UI thread (3 s timeout in remote mode); moving them to workers is a P0-I8 hardening follow-up.
