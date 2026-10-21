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
| `ClientInterface` admin calls (`list_accounts`, `create_account`, `set_roles`, `disable_account`, `enable_account`, `reset_password`, `list_agent_tokens`, `issue_agent_token`, `revoke_agent_token`, `get_account`) | methods | Same names and signatures as `tl_api.client.AdminApi`. The embedded client refuses any actor that is not an active admin account (`ForbiddenError`; `issue_transmittal` needs an active admin or document controller) and hashes passwords before its write transaction |
| `tl_tui.widgets.admin_screen.AdminScreen`, `account_forms`, `tl_tui.admin_text` | modal, forms, helpers | Accounts and agent tokens (`F10`, admins only): table and detail, `d` disable or enable, `r` admin role, `c` document controller role (ADR-0013; people and sim accounts, not agents), `t` tokens, `a` add, `p` password, `i` issue (shown once, `TokenShown`), `x` revoke. The service decides every rule; text helpers are pure and carry the `✓ ! ✗ ■` symbols |
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
| `tl_tui.widgets.document_register.DocumentRegisterScreen`, `tl_tui.document_text` | modal, module | The document register (`F7`): the project's documents with state and the current revision (`B(IFC)`); the panel shows the highlighted document's revisions with their status class and files, and its links, a stale pin marked `!`. `s` walks the states, `y` the types, `a` void too, `/` filters, `F5` reloads. `r` opens the re-pin dialog for the first stale link, `t` the transmittal composer |
| `tl_tui.widgets.schema_screen.SchemaWorkbenchScreen`, `schema_review_screen.SchemaReviewScreen`, `tl_tui.schema_text`, `schema_review_text` | modals, modules | The schema workbench (`Ctrl+O`): package versions with Properties, Lint and Diff tabs (`1`-`3`, `[` `]`, `F5`, `Esc`); `v` opens the review (`a` analyse, `t` sample, `i` project impact, `s` submit, `y` approve, `c` send back, `p` publish with the word typed). Every read and write is a client call (P1-I8) |
| `tl_tui.widgets.repin_dialog.RepinScreen` | modal | Shows the diff between the pinned revision and the current one; Enter or `y` sends `RepinDocumentLink`, Esc or `n` leaves the link. A refusal stays on screen |
| `tl_tui.widgets.transmittal_composer.TransmittalComposerScreen` | modal | Tick issued revisions, type a subject, purpose, recipients (`Name:Organisation:email; ...`) and an optional due date; `ctrl+s` drafts the transmittal; a document controller or an admin also gets `ctrl+t`, which drafts and issues it (`issue_transmittal`; the server and the embedded client refuse anyone else, ADR-0013) |
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
| `tl_tui.widgets.derived_documents.DerivedDocumentsScreen`, `job_monitor.JobMonitorScreen`, `publish_preview.PublishPreviewScreen`, `tl_tui.derive_text` | modals, module | Derived documents (`F11`, P1-I3): the table with state, pass, rows and errors; the panel shows the validation report or (`d`) the diff against the previous pass; `x` queues an extraction, `v` a validation, `j` opens the job monitor (refreshes every 2 s, `c` cancels a queued job), `p` the publish preview (counts, rows, `s` skip existing, `p` twice to create, `c` shows and `u` does the compensation; role-gated: admin for tags, controller for documents). The text is pure functions in `derive_text` |
| `tl_tui.widgets.review_queue.ReviewQueueScreen`, `integration_screen.IntegrationScreen`, `tl_tui.integration_text` | modals, module | The integration layer (P1-I7). Review queue (`Ctrl+R`, any person): the values enrichers proposed, `a` accept, `x` reject (asks for a reason), `s` waiting or all. Registry (`Ctrl+E`, admins): endpoints, rules, actions, enrichers, apps, invocations and the inbound error queue (`[` `]` or `1`-`7`), `e` switches an app, endpoint, rule or enricher, `y` retries a failed delivery, the kill switch is in the title (changed in `F9`). Both call the allow-listed commands through `ClientInterface.integration_command` and read with `list_integration`; the service decides every rule |
| `tl_tui.widgets.schedule_screen.ScheduleScreen`, `compare_screen.CompareScreen`, `activity_screen.ActivityScreen`, `tl_tui.schedule_text` | modals, module | Schedules (`F12`, P1-I4): the schedules and the snapshots of the highlighted one (the current one marked `*` and "(current)"), the panel with the snapshot, the look-ahead (`l`) or the orphaned links (`o`); `c` opens the comparison (sections added, removed, date shifts, float, logic, progress, durations, critical, `Right`/`Left` to move), `a` the activities (paged, `c` critical only, `/` filter) with the relationships and float trend of the highlighted one, `p` publishes the highlighted snapshot (the service decides who may). A short note shows while the links are still being checked. The text is pure functions in `schedule_text` |
| `tl_tui.widgets.domain_screen.DomainScreen`, `tl_tui.rfi_text`, `tl_tui.commercial_text`, `tl_tui.evidence_text` | modal, module | RFIs, Commercial notices and the evidence trail (`Ctrl+G`, P1-I6): `1` the RFI log (response days, timing, impact flags), `2` the Commercial register (time bars with `LATE`, values by currency), `3` the evidence trail of the highlighted item (`e`) as the ledger knew it at the end of a day (`[` and `]` step the day, `0` is today). `o` open only, `v` overdue RFIs or running and late bars, `i` impact (RFI log). A person below a controller gets an empty register and is told why; the trail leaves out what the person may not read today. Reads only: `list_rfis`, `get_rfi`, `list_commercial`, `get_commercial`, `get_evidence_trail`. The text is pure functions |

## Plain and technical display (P1-UX)
Every screen speaks plain language by default and an admin can switch the technical detail on with `Ctrl+D`
(palette "Technical details"; a plain user gets "Technical details are for admins"). New screens follow this:
- Labels come from `tl_tui.display` (`Labels`, `type_label`, `code_label`, `domain_label`, `actor_label`, `quantity`,
  `humanize`), loaded once with `tl_tui.labels_load.load_labels(client, scope, types)`. No per-screen string tables.
- The mode lives on the app as `app.display_mode` (a `DisplayMode`, off at start, not remembered). Read it with
  `mode_of(self.app).technical`; `mode_of` takes the app, never a widget. Never name an attribute `display`.
- Text modules take `technical` and `labels` arguments: `fn(x, labels=None, *, technical=...)`. A function another
  screen still calls keeps raw output as its default.
- A widget whose text depends on the mode defines `refresh_for_display_mode()`; the toggle calls it on every widget of
  every stacked screen.
- A register opens `widgets.record_screen.open_record` on `DataTable.RowSelected` (not a priority Enter binding).
- `tests/test_plain_walk.py` walks every key-map screen as a plain user and as an admin, and fails on ids, hashes,
  package refs, internal keys and record-type or property keys (`display.find_technical`). A new screen or key either
  gets walked or is listed in the test's exclusions. `KNOWN_LEAKS` stays empty.
- `dev/tour/tourkit.py` runs the same check on every TUI screenshot and prints `LEAK <shot> <tokens>`.

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

### Record threads (P1-I7 WS-B)
The record view's Thread tab (`T`; `widgets/thread_tab.py`, text in `thread_text.py`) and the thread composer (`c`;
`widgets/thread_composer.py`, text in `compose_text.py`): `/` offers the verbs, a command line is previewed and then
confirmed with the preview's token. The client calls are `thread_page`, `thread_post`, `thread_preview`, `thread_dispatch`.

## Rules specific to this package
See `AGENTS.md` in this directory.

## Status
P1-I2: the document register (`F7`), the re-pin dialog and the transmittal composer, with the document reads and the writes (`repin_document_link`, `create_transmittal`, and for controllers `issue_transmittal`) of `ClientInterface` (`docs/tickets/P1-I2/README.md`). P1-I1: the tag register (`F8`) and the tag reads of `ClientInterface` (`docs/tickets/P1-I1/README.md`). Sign-in, the accounts screen and the admin client calls added in P1-I0 workstream A (`docs/tickets/P1-I0/README-A.md`; `docs/runbooks/accounts-and-access.md`). Introduced in P0-I1 (skeleton). First interface: P0-I2 workstream B (shell, grid, record view, forms, key map). P0-I3 added the link, workflow, trace and tray screens, the palette, and `ClientInterface` methods for links, search, workflow, key detection and `edit_record` (atomic form save). P0-I4 workstream D added the remote client, live updates in both modes, the filter bar and the conflict banner (plan: `docs/tickets/P0-I4/README-D.md`). P0-I6 workstream B: the six feed methods of `RemoteClient` now go to the API (`GET /feed`, the feed command routes), and an open feed pane reads its first page again when any event of its project arrives (`TlApp._refresh_feed_pane`). Review-queue screens and `RemoteClient` proposal methods are not built (`ClientInterface` has no proposal methods). P0-I8 workstream A added the settings calls and the about:config screens (`F9`); not built in the screen: diff against another project, Enter toggling a boolean, origin as scope ids, lock on `L` (it is `k`), scheduled changes (`applies_at`) and company bounds (use `tl config`). Known limit: the grid load, record view and filter calls still run on the UI thread (3 s timeout in remote mode); moving them to workers is a P0-I8 hardening follow-up. Extension type grid and forms added in P0-I8 workstream B (`docs/tickets/P0-I8/README-B.md`; runbook `docs/runbooks/extension-types.md`).
P1-I5: the correspondence screen (`F5`; `tl_tui.widgets.correspondence_screen.CorrespondenceScreen`, text in `tl_tui.correspondence_text`): the master register, the triage inbox (`a` confirms the suggestion) and the response clocks (`s` sweeps, `c` adds the closed ones), with the correspondence reads and `correspondence_command` on the client. The fake client takes them from `tests/fakes_correspondence.py`.

P1-I6: the RFI, Commercial and evidence screen (`Ctrl+G`; `tl_tui.widgets.domain_screen.DomainScreen`, text in `rfi_text`, `commercial_text` and `evidence_text`), with the five domain reads on the client (embedded, remote and the fake in `tests/fakes_correspondence.py`, `seed_domains`).

P1-I8: the schema workbench and review screen (`Ctrl+O`, `v`), with the package reads and the review writes on the client (embedded, remote and `FakeClient`). A keymap or palette addition changes the command-palette snapshot (L-P1-I8-13).
