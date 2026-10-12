# tl-tui (`tl_tui`)

The Textual application shell, grid, record view, and forms; every screen reads and writes through `ClientInterface`, so the same screens run embedded (a SQLite file or a Postgres database opened in this process) or remote (a running API server), and in both modes they show other writers' changes live (§4, §5.3, §10.1–§10.4, §10.6 sketches 1, 2, 11).

## Public interface
| Symbol | Kind | Purpose |
|---|---|---|
| `tl_tui.client.ClientInterface` | Protocol | The only way a screen reads or writes. Contract from P0-I2; `list_records` also takes `order_by` (additive, P0-I2 decision B7); P0-I3 added link, search, workflow, key-detection and `edit_record` methods; P0-I4 added `query_records(scope, q, ...)` and `count_records(scope, q)` (the query language, decision O3) |
| `tl_tui.embedded.EmbeddedClient` | class | `ClientInterface` over in-process `tl_core` services; `EmbeddedClient.for_target(target)` (a SQLite path or a `postgresql://` URL; `for_sqlite` is an alias) keeps one engine and bus, so the live feed works on either database; `.change_feed(scope)` and `.own_writes` |
| `tl_tui.remote.RemoteClient`, `RemoteFeed` | classes | `ClientInterface` over `tl_api.client.ApiClient` (`RemoteClient.connect(url, token)`): converts `RelationOut`, reports `unreachable` / `live` to `connection_listener`, 3 s call timeout, `.change_feed(scope)` is the SSE stream resumed by `seq` |
| `tl_tui.live` | module | `ChangeFeed` / `FeedSink` protocols, `EmbeddedFeed`, `LiveUpdates` (feed thread posting `LiveEvents` / `ConnectionChanged`), `OwnWrites`, and the pure rules `touched_record_ids`, `detect_conflict`, `describe_changes` |
| `tl_tui.errors.CLIENT_ERRORS`, `describe_error` | tuple, function | Expected failures a screen catches (now including `ApiError`, `ApiUnavailableError` = "server unreachable"), and the one-line text to show |
| `tl_tui.sign_in` (`SignedIn`, `Authenticator`, `SignInScreen`, `SignInApp`) | module | The sign-in screen the TUI shows first (P1-I0): username, masked password, the service's refusal under the fields, Esc quits. `EmbeddedAuthenticator` (`embedded.py`) checks the ledger file's accounts with lockout and audit; `RemoteAuthenticator` (`remote.py`) signs in over `POST /auth/sign-in` and the 12-hour token lives in memory; `remote.sign_out` ends it on every exit. `main.run` signs in unless `tl tui` passes the `tl login` session or a token is given; the screen warns about plain http to a non-loopback host |
| `ClientInterface` admin calls (`list_accounts`, `create_account`, `set_roles`, `disable_account`, `enable_account`, `reset_password`, `list_agent_tokens`, `issue_agent_token`, `revoke_agent_token`, `get_account`) | methods | Same names and signatures as `tl_api.client.AdminApi`. The embedded client refuses any actor that is not an active admin account (`ForbiddenError`) and hashes passwords before its write transaction |
| `tl_tui.widgets.admin_screen.AdminScreen`, `account_forms`, `tl_tui.admin_text` | modal, forms, helpers | Accounts and agent tokens (`F10`, admins only): table and detail, `d` disable or enable, `r` admin role, `t` tokens, `a` add, `p` password, `i` issue (shown once, `TokenShown`), `x` revoke. The service decides every rule; text helpers are pure and carry the `✓ ! ✗ ■` symbols |
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
| `ClientInterface.list_settings`, `get_setting`, `setting_history`, `set_setting`, `reset_setting`, `lock_setting`, `revert_setting` | methods | The settings calls (P0-I8), with the names and signatures of `tl_api.client.ApiClient`; the embedded client calls `tl_core.settings` and records its `actor` (an `agent:` actor is refused) with source `tui`; the remote client passes them through |
| `ClientInterface.feed_page`, `feed_post`, `feed_edit`, `feed_retract`, `feed_react`, `feed_complete` | methods | The feed calls; the embedded client uses `tl_core.services.feed*`; a remote client implements the same methods |
| `tl_tui.widgets.tag_register.TagRegisterScreen`, `tl_tui.tag_text` | modal, module | The tag register (`F8`): the project's tags by number with class, state, number check (`BAD` for a number that breaks the pattern) and conformance; the panel shows the highlighted tag's segments, violations and what it lacks (`get_tag`). `c` walks the classes, `v` violations only, `a` ended tags too, `/` filters, `F5` reloads. Reads only: `ClientInterface.list_tags` / `get_tag` (embedded, remote through `EngineeringApi`, and the fake) |
| `tl_tui.widgets.settings_screen.SettingsScreen`, `setting_form.SettingForm`, `setting_history.SettingHistory`, `tl_tui.settings_text` | modals, module | about:config (`F9`, or `about:config` in the palette): every setting with its value, type, origin (`●` = set at the layer a change goes to) and lock; filter (`/`), modified only (`m`), `L` sends changes to the project or the company, `e` edit, `r` reset, `k` lock, `h` history with `u` undo of the latest change at a layer. The form asks for the reason and, for a dangerous key, "I accept the risk"; the service decides what is allowed. `settings_text` holds the pure text and the layer rule |
| `tl_tui.tray.ReferenceTray`, `widgets.ref_tray.ReferenceTrayScreen` | class, modal | Reference tray (`R` adds, `F4` opens): tick, remove, clear, link the ticked records to the open record; a partly refused batch stays open with the reasons |
| `tl_tui.navigation.NavHistory` | class | Back and forward trail (`Alt+Left`, `Alt+Right`) |
| `tl_tui.widgets.trace_tab.TraceTab` | widget | Trace tab (`t`): n-hop tree, depth `+`/`-`, direction `o`, Enter follows |
| `tl_tui.widgets.workflow_menu.WorkflowMenu` | modal | Workflow actions (`w`) listing each transition with its guards; a blocked one says why |
| `tl_tui.widgets.prompt.PromptScreen` | modal | One-line input used by the links tab for notes and reasons |
| `ClientInterface.list_types`, `get_type`, `create_instance`, `get_record_body`, `put_record_body` | methods | Extension record types (brief 31): both clients and the fakes implement them (`EmbeddedClient(object_store=, actor=)` refuses an `agent:*` actor and reports an object store failure as `BodyStoreUnavailableError`) |
| `tl_tui.extension_columns` | module | `columns_for_type`: the grid columns `form.yaml` names (only slots stored as pset values); `form_for_type`, `form_for_record_type`, `type_warning` (a status-line warning when `--type` names a type with no active version) |
| `tl_tui.extension_fields`, `widgets.extension_form.ExtensionRecordForm` | module, modal | The generated new-record form (`n` on an extension type): editors from the type's form, values sent as psets (managed) or a body (object-backed), a slot only when changed or required |
| `tl_tui.extension_body`, `widgets.extension_edit_form.ExtensionEditForm` | module, modal | `e` on an object-backed record edits its stored body: only changed slots are applied, the rest of the body is kept, a stale version blocks the save |
| `tl_tui.main.make_app`, `run`, `main` | functions | `tl-tui` / `python -m tl_tui` / `tl tui`: embedded by default, remote with `--remote URL` and a token |

## Depends on / used by
- Depends on: `textual`, `tl_core` (services, query language, change feed), `tl_schema` (form metadata models), `tl_adapters` (only `tl_adapters.backend` / `tl_adapters.db`, in `embedded.py` and `main.py`), `tl_api` and `httpx2` (only `remote.py`).
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
| `TL_DB` | `./dev/data/tl.db` | The ledger for embedded mode: a SQLite file or a `postgresql://` URL (prefer the variable for a URL; the sign-in screen shows it without the password) |
| `TL_PROJECT` | `P123` | Project whose records the grid shows (scope `project:<id>`) |
| `TL_TYPE` / `--type` | `core.Record` | Record type the grid lists; an extension type (`co.acme.LiftPlan`) gets the columns of its `form.yaml` |
| `TL_OBJECT_STORE`, `TL_OBJECT_ROOT`, `TL_OBJECT_SECRET` | see `tl_adapters` | Object store for record bodies in embedded mode |
| `TL_SCHEMA_DIR` | `schema/fixtures` | Package directory the pset services read (see `tl_core.schema_provider`) |
| `TL_REMOTE` | (unset) | API URL; when set the TUI runs remote (`--remote` overrides) |
| `TL_TOKEN` | (unset) | Dev token for remote mode (ADR-0005); prefer it to `--token`, which shows in `ps` |

## Rules specific to this package
See `AGENTS.md` in this directory.

## Status
P1-I1: the tag register (`F8`) and the tag reads of `ClientInterface` (`docs/tickets/P1-I1/README.md`). Sign-in, the accounts screen and the admin client calls added in P1-I0 workstream A (`docs/tickets/P1-I0/README-A.md`; `docs/runbooks/accounts-and-access.md`). Introduced in P0-I1 (skeleton). First interface: P0-I2 workstream B (shell, grid, record view, forms, key map). P0-I3 added the link, workflow, trace and tray screens, the palette, and `ClientInterface` methods for links, search, workflow, key detection and `edit_record` (atomic form save). P0-I4 workstream D added the remote client, live updates in both modes, the filter bar and the conflict banner (plan: `docs/tickets/P0-I4/README-D.md`). P0-I6 workstream B: the six feed methods of `RemoteClient` now go to the API (`GET /feed`, the feed command routes), and an open feed pane reads its first page again when any event of its project arrives (`TlApp._refresh_feed_pane`). Review-queue screens and `RemoteClient` proposal methods are not built (`ClientInterface` has no proposal methods). P0-I8 workstream A added the settings calls and the about:config screens (`F9`); not built in the screen: diff against another project, Enter toggling a boolean, origin as scope ids, lock on `L` (it is `k`), scheduled changes (`applies_at`) and company bounds (use `tl config`). Known limit: the grid load, record view and filter calls still run on the UI thread (3 s timeout in remote mode); moving them to workers is a P0-I8 hardening follow-up. Extension type grid and forms added in P0-I8 workstream B (`docs/tickets/P0-I8/README-B.md`; runbook `docs/runbooks/extension-types.md`).
