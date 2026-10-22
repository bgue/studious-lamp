# Throughline build learnings

Project memory for the agents building Throughline. It holds facts that are too small for an ADR but
expensive to rediscover: environment quirks, tool gotchas, conventions that emerged, mistakes not to repeat.
It lives in git so every worktree and every future session sees the same memory, and humans can review it.

**Who reads it:** the orchestrator and supervisors, at the start of every session. Implementers do not read it;
a supervisor pastes a relevant entry into a ticket's *Brief references* when it matters.

**Who writes it:** any supervisor or the orchestrator, by appending entries at the end of the *Active* list in
the same commit as the work that taught the lesson. Implementers propose entries in their report under
*Learnings*; the supervisor decides. The file uses `merge=union`, so parallel appends merge cleanly.
Load the `throughline-docs` skill for the full rules.

**Entry format** (one entry per bullet block, IDs unique per increment):

```
- **L-<increment-id>-<n>** · <yyyy-mm-dd> · tags: <env|tooling|schema|ledger|tui|api|mcp|sync|tests|process>
  <one or two sentences: the fact, stated so it can be acted on>
  Evidence: <ticket, report, command output, or file:line>. Status: active
```

**Status values:** `active`; `superseded by L-…`; `promoted to <ADR-nnnn | AGENTS.md | skill | build-spec file>`; `archived (phase <n>, still true)` for a fact that holds but only mattered to finished work.
Entries are never deleted. At each phase exit the orchestrator marks superseded and promoted entries and moves
them to `docs/memory/archive/<phase>.md`, keeping the *Active* list under about 150 lines.
Archived entries keep their IDs: `grep -rn -A6 "<id>" docs/memory/archive/` finds one (`phase-0.md`, `phase-1.md`).

**Not for:** decisions that change a contract or interface (write an ADR), secrets or credentials, anything a
test or a generated artefact already enforces, or narrative history (that belongs in reports).

## Active

### env: Environment and dependencies: container limits, drivers, licences, worktree setup.

- **L-P0-SETUP-1** · 2026-10-09 · tags: env
  The build container has the Docker CLI but no Docker daemon. Anything that needs MinIO, Postgres, or other
  services must run natively or be mocked; `docker compose` is documentation only.
  Evidence: `docker ps` fails on `/var/run/docker.sock`; ADR-0002. Status: active

- **L-P0-SETUP-5** · 2026-10-09 · tags: env, tests
  Native PostgreSQL 16 starts with `sudo pg_ctlcluster 16 main start`; parity tests use
  `TL_PG_URL=postgresql://postgres:postgres@localhost:5432/tl_test`, which the SessionStart hook exports.
  Evidence: hook validation run. Status: active

- **L-P0-I6A-1** · 2026-10-09 · tags: env, process
  A new worktree has an empty `.venv`: run `uv sync --all-packages` once (plain `uv sync` installs no workspace package, and `just check`
  then reports 1790 pyright errors about unresolved imports). After a trunk merge that adds a dependency (pg8000), run it again.
  Evidence: first `just check` in `/home/user/wt/p0-i6a`; `ModuleNotFoundError: pg8000` after the P0-I5 merge. Status: active

- **L-P0-I5-O1** · 2026-10-09 · tags: dependencies, gates
  Check the licence of every new dependency and its transitive tree before adding it. psycopg 3 is LGPL-3.0, and
  linkml's hard `jsonschema[format]` pulls rfc3987 (GPL-3.0+). Both are copyleft, which is a human gate. Use pg8000 for
  Postgres, and keep the root `override-dependencies` that swaps in `jsonschema[format-nongpl]`. Name the licence in
  the relay NOTE and in APPROVALS.md. Policy and allow-list: ADR-0006.
  Evidence: orchestrator licence scan during P0-I5. Status: active

- **L-P0-I6C-8** · 2026-10-10 · tags: env, tooling
  Two implementer reports found shell traps in the Bash tool: `pkill -f <pattern>` matches the shell that runs it when the pattern is in the command line (exit 144), and a
  multi-line `cat > file <<'EOF'` inside a `&&` chain once hung until the 120 s timeout while the Write tool created the file at once. Use `pgrep` and a PID, and write files with
  the Write tool.
  Evidence: `docs/reports/P0-I6/P0-I6-T41.md`. Status: active

#### L-P1-I8-5 (env) Never clean `/tmp/pytest-of-root`: it is shared by every agent
The standing instruction to remove folders older than an hour from `/tmp/pytest-of-root` between runs is wrong when other supervisors run suites at the same time (it caused 767 errors in another run). Give each heavy run its own base temp (`--basetemp=/tmp/pt-p1i8-<name>`), read its exit code, and then remove that one directory. Evidence: coordinator correction of 2026-10-20; one age-based clean-up was run at the start of P1-I8 before the correction.

#### L-P1-I8-8 (env) One pytest session over several large packages is killed by the memory limit
`pytest packages/tl-core packages/tl-api packages/tl-mcp tests/...` in one process grew to 7 GB and was OOM-killed at 67 % (exit 137) with no failure before it. Run the packages one per process (`tl-api` alone takes 13 minutes, `tl-core` 36 seconds, `tl-mcp` 6 minutes, the root `tests/` shards under 2 minutes). Evidence: kernel `oom-kill` line for `pytest`, P1-I8 S6.

### tooling: Tool gotchas: pyright strict, ruff, Textual, shell and Bash traps.

- **L-P0-I5-A8** · 2026-10-09 · tags: tooling, ledger
  pg8000 differences that the adapter hides: it ignores libpq `options` (the schema goes in as the startup parameter `search_path`);
  it raises `IntegrityError` only for SQLSTATE 23505, so `engine.py` re-raises every class-23 error as `IntegrityError` (the append-only
  trigger, NOT NULL); it has no blocking wait for `LISTEN`, so `NotifyListener` runs `SELECT 1` every 50 ms and drains
  `conn.notifications`; result coercions are `register_in_adapter(oid, fn)` with fn taking the text value. The loader behaviour that
  `tl_core` relies on (canonical JSON text, ISO UTC timestamps, 0/1 booleans, int sums) is the same under both drivers.
  Evidence: `postgres/engine.py`, `postgres/notify.py`; 150 adapter tests pass on both adapters. Status: active

- **L-P0-I5-B1** · 2026-10-09 · tags: tooling, process
  Never name a module `types.py` (or `enum.py`, `json.py`) inside a package: a script or `python -` run from that directory puts
  it first on `sys.path` and the standard library's own imports break (`cannot import name 'MethodType' from 'types'`). The webhook
  package uses `base.py`.
  Evidence: `packages/tl-core/src/tl_core/webhooks/base.py` (renamed from `types.py` after the first ad-hoc script failed). Status: active

- **L-P0-I3-7** · 2026-10-09 · tags: tui, tooling
  Textual `OptionList` prompts and `DataTable` cells that are plain `str` are parsed as Rich markup, so `[x]` vanished from a
  row (`▶ [x] KEY` rendered as `▶  KEY`). Wrap row text in `rich.text.Text(...)`. `query_one("#id", Select[str])` raises
  `TypeError` at run time (subscripted generic): query `Select` and annotate the variable `Select[str]`. A screen method named
  `action_toggle` overrides `DOMNode.action_toggle` and fails pyright; use `action_toggle_select`. Textual's own command palette
  owns Ctrl+P: set `ENABLE_COMMAND_PALETTE = False` on the app before binding it.
  Evidence: `widgets/link_picker.py`, `app.py`, first pilot runs of `test_link_picker`. Status: active

- **L-P0-I8A-10** · 2026-10-10 · tags: tui, tests
  `pytest --snapshot-update` rewrites the tracked `snapshot_report.html` at the repository root as well as the `.raw` files: restore it with `git checkout snapshot_report.html` before committing. A new palette command or key map entry changes the palette snapshot (`test_snapshots_links.py::test_command_palette`) and the key map context list in `test_keymap.py`.
  Evidence: P0-I8-S19 (`git status` after the update). Status: active

- **L-P0-I8A-9** · 2026-10-10 · tags: tooling, security
  Hostile numbers and nesting raise errors other than the ones a parser documents: `yaml.safe_load` raises `RecursionError` (50,000 nested levels) and `ValueError` (integers over 4300 digits); `float(huge_int)` raises `OverflowError`; `json.dumps` of such an integer raises `ValueError`. Wrap the parse, the float conversion and the message formatting, and turn each into the domain error.
  Evidence: `tests/settings/test_exchange.py::test_a_file_that_breaks_the_yaml_reader_is_a_document_error`, `packages/tl-core/tests/test_settings_values.py::test_a_number_too_large_for_a_float_is_out_of_range_not_an_error`. Status: active

#### L-P1-I4-15 (tui) Two Textual name traps, and a table refill raises RowHighlighted after you have placed the cursor
`self.offset` (a widget's DOM offset) and `self._id` (Textual's own) cannot be attributes or methods of a screen: the first raised `TypeError` in `__init__`, the second `'NoneType' object is not callable` in the first reload; the screens use `first` and `_current_id`. Filling a `DataTable` (`clear`, `add_row`) posts `RowHighlighted` after the fill has returned, so a handler that reloads a dependent table (a schedule's snapshots) must do nothing when the highlighted row is the one already loaded, or every reload puts the dependent cursor back on row 0. The provided test `test_moving_between_schedules_loads_their_snapshots_and_a_reload_keeps_the_place` pins it. Evidence: `tl_tui/widgets/schedule_screen.py`, `activity_screen.py`.

### tests: Test conventions that no test enforces.

- **L-P0-I8A-7** · 2026-10-10 · tags: tests, process
  Adding a command to the API table, a tool to `PROPOSABLE_TOOLS` or an event type to the catalog breaks tests that assert literal counts or lists elsewhere: `len(COMMANDS) == 17` and the agent-refusal count of 13 in `tl-api`, `PROPOSE_TOOLS` and `PROPOSING` in `tl-mcp`, `register_write_tools`' assertion on the tool modes, the table lists of `test_generate.py` and `test_ddl.py`, and the webhook scenario. Run `just test` once after the contract amendment and fix all of them in the same commit.
  Evidence: the first full `just test` of P0-I8-A (3 failures, then 1 more in `tl-api`). Status: active

- **L-P1-I1-4** · 2026-10-12 · tags: tests, process, database
  Two defects of the supervisor's base blocked a ticket that was otherwise right. (1) SQL ordering: SQLite sorts NULL first and Postgres last, so a report that says "no class first" needs `ORDER BY (col IS NULL) DESC, col`, and a test that checks the order must run on Postgres before the ticket goes out. (2) A provided test that builds a command with `**more` from a dict literal of mixed values is typed `dict[str, str]` by pyright and fails strict checks in the implementer's tree: give the dict an explicit `dict[str, Any]`. Before a batch goes out: pyright and ruff on every provided test in its target path, and the Postgres variant of every test that touches ordering.
  Evidence: T11 review (`_SUMMARY_SQL`, `test_cli_tag_report.py`); fixed in `reports.py` and the provided test. Status: active

#### L-P1-I3-7 (tests) A CLI test that is about having no session needs AUTO_SIGN_IN = False
`packages/tl-cli/tests/conftest.py` signs an admin in before every command on Postgres. A test of "nobody is signed in" sets `AUTO_SIGN_IN = False` at module level and accepts either `needs the admin role` or `not signed in` (Postgres refuses earlier than SQLite). Evidence: `packages/tl-cli/tests/test_cli_proposal_access.py`.

#### L-P1-I3-11 (tests) A test that loops over what it found must first assert that it found something
The first version of the walking test read `app.routes`, which in this FastAPI holds `_IncludedRouter` objects and no route paths, found nothing, and passed. Assert the count (and a few known members) of what a walk finds before the loop, and run a new walker once against code that lacks the guard. Evidence: `test_the_walk_finds_the_command_routes_and_the_upload_routes`.

- **L-P1-I7A-14** · 2026-10-19 · tags: tests, tooling
  A test that provokes a constraint violation inside a unit of work must wrap it in a savepoint (`conn.begin_nested()`): Postgres aborts the whole transaction on the error and the unit of work's own commit then fails with "in failed transaction block", where SQLite carries on.
  Evidence: `tests/integration/test_int_runner_access.py::test_a_service_actor_is_unique_in_its_table`. Status: active

- **L-P1-I5-1** · 2026-10-17 · tags: database, tests
  Postgres cannot infer the type of a bare parameter in `CASE WHEN :p IS NOT NULL AND :p > col ...` (`could not determine data type of parameter $1`); SQLite accepts it, so a SQLite-only run passes. Choose the value in Python (read the row, compare, write) or `CAST(:p AS text)`. A slot named `to_json` with `tl:json` gets the column `to_json_json`: name JSON slots without the suffix (`to_parties` gives `to_parties_json`).
  Evidence: `projectors/thread.py` (first version failed `test_a_thread_counts_its_items_and_keeps_the_newest_date[postgres]`); `schema/modules/correspondence/correspondence.yaml`. Status: active

#### L-P1-I8-4 (tests) A module that joins every ledger breaks the pinned lists of other packages
Installing `tl-mod-schemareg` made seven tests fail at once (three DDL file lists, the view list, the webhook scenario that must produce every catalog event, the entry-point list): `pytest packages/tl-schema tests/contract tests/services/test_modules.py tests/webhooks` finds them in six minutes (L-P1-I2-6, again). A script rewrote the file lists. The scenario also needs one stream per new record type (`MODULE_STREAMS`).

#### L-P1-I8-13 (tests) A keymap or palette addition makes a TUI snapshot stale: put it in the ticket's tests
Adding `Ctrl+O` and its palette entry left `part 2` of the DONE gate red (the command-palette snapshot) although every ticket gate was green, because no ticket ran the snapshot test. A ticket that adds a binding, a keymap line or a palette command names `packages/tl-tui/tests` snapshot and keymap tests in its gate and regenerates the snapshot. Evidence: fix 4e1bba8.

#### L-P1-I8-15 (tests) `app.pop_screen()` does not run a `push_screen` callback; `screen.dismiss(None)` does
A modal that opens another (workbench to review) and must re-read when it closes only gets its callback from `dismiss`. A test that closes it with `pop_screen()` passes while the real `Esc` path is untested. Also: a `ruff: noqa` stub header sits in lines 1-2, so `sed 1s` clobbers it. Evidence: `schema_screen.py` `action_review`, T04a/T04b reports.

### process: Process rules: relays, workers, tickets, gates, concurrency and recovery.

#### L-P1-I7B-9 (process) Before a DISPATCH, grep every command and function a provided test calls
Third Depends miss in one workstream (T10d needed T10a's `/link`; T09b's tests call `tl thread show` and `tl thread post` of T09a). Procedure before each DISPATCH: for each provided test, list every CLI command, API route, tool and imported function it uses (`grep -n '"thread"\|^from tl_'`), and check that each is on the base or is named in the ticket's Depends. A ticket that depends on an unmerged ticket goes in a later batch. Also check the test count the ticket states against `grep -c '^def test'` of the file (T09a said 10, the file has 11; T09b said 9, it has 10).

#### L-P1-I8-3 (process) A reference-first ticket needs the provided test to fail on the stub and to be mutated against the reference before it goes out
T03 and T08: the stub fails 24 of 28 and 22 of 22 cases; 22 mutants of the impact reference and 29 of the mart references were killed except three that needed a test or are equivalent (a date cast that DuckDB does the same with or without `SUBSTR`; a `sorted()` on a set that only a hash seed can tell, covered with more paths; a table-presence test, then covered). Two survivors were missing tests (a table-presence check with only some silver tables; a one-decimal average that every fixture made whole). Evidence: `docs/tickets/P1-I8/provided/`.

#### L-P1-I8-14 (process) The whole-suite DONE gate exceeds the two-hour background limit: run it as separate background runs per part
`just gate` (4 parts, about 2 h with the parity of touched directories) was stopped by the background limit. The orchestrator starts each part (`dev/gate.sh` part k) and `gate-pg` as its own background run and reads each summary; a rerun after a fix covers the touched directories only. `test_int_inbound_worker` (live secrets = 112) failed in part 3 and passes alone: record it as flaky (112), not as a failure.

### security: Domain: security rules for services that take client input.

- **L-P1-I0A-7** · 2026-10-11 · tags: security, api
  A security review found three classes of mistake worth checking in any credential code: (1) a slow hash (or any slow step) inside a write transaction holds the global writer lock, so a flood of sign-ins stalled all writes for 17 s: hash first (`prepare_password`), write after; (2) a lock or message that differs by account kind or history is an oracle for which names exist, so every lock is the same 15 minutes; (3) a token, session or stream that is checked once stays valid after revocation, so long-lived streams re-check on a timer.
  Evidence: D6 review of P1-I0 S2b and S2c; `tests/auth/test_review_fixes.py`, `packages/tl-api/tests/test_auth_review.py`. Status: active

- **L-P1-I0A-20** · 2026-10-11 · tags: security, cli
  An option default that is only used when the flag is left out does not protect anything: `--actor user:root` bypassed the session check that the default went through. Put the check on the value (a click callback runs on defaults and explicit values alike), and let the target decide how much a stated identity is worth: a file you own, versus a shared database.
  Evidence: `tl_cli/actor_hook.py`, `session.check_actor`; `test_cli_session.py::test_outside_dev_no_actor_can_be_used_without_a_sign_in_not_even_a_named_one`. Status: active

- **L-P1-I1-8** · 2026-10-12 · tags: security, architecture
  When a module adds record types, check every generic command that can reach `cur_core_record`: they load a record by id and check only its scope, so they treated a module record like a core one. A tag class or a code list could be retitled by any signed-in person with `UpdateRecord`; the review found it, no test did. A module record type now allows no generic command unless its spec lists it, and the check lives in `tl_core` (`require_generic_command`), so the API, CLI, MCP and proposals all inherit it. Related: a field that records where something came from (`origin`) must not be client input, and a flag that turns off a check (`pattern_policy`) is a separate, role-gated command.
  Evidence: ADR-0010 addendum; `tests/services/test_modules.py`, `packages/tl-modules/engineering/tests/test_generic_commands.py`, `packages/tl-api/tests/test_api_engineering.py`. Status: active

- **L-P1-I2-17** · 2026-10-13 · tags: security, postgres, core
  A NUL (`\x00`) in any text sent to Postgres raises a driver error that carries the SQL statement and its values, and on SQLite it is stored without complaint, so a SQLite-only test never sees it. Refuse it where input enters: the core `Command` base class rejects a NUL in any string, nested or not, as a validation error (`contains_nul`), and a file reader treats any other control character as a problem of its row so a preview shows it and `--skip-invalid` can leave it out. When a hardening applies to every command, put it on the base class and test it on both adapters instead of fixing one command at a time (the first probe found `RegisterDocument` crashing on number, title, description and originator alike).
  Evidence: a0d5a83; `tests/services/test_command_text.py`, `test_imports_limits.py`, `test_cli_tag_import.py`. Status: active

- **L-P1-I3B-7** · 2026-10-17 · tags: security, tooling
  A library's read-only or lazy mode is not a bound. openpyxl `read_only` still builds a whole row (a cell at column XFD makes 16 384 cells) and the whole shared-strings table before a cap can look at it (99 KB of XLSX: 99 s, 7.7 GB), and pypdf `len(reader.pages)` decodes object streams (1.2 MB of PDF: 113 s, 1.3 GB). The fixes that held: stream the XML with `iterparse` and count elements, depth, strings, cells and characters as they come, removing each row from its parent; for pypdf, read `/Root/Pages/Count` only, read strict, lower its decompression limits per call with `pypdf.apply_configuration`, and scan the bytes first with linear C-speed passes (object streams, `/Length` past the end of the file, strings over a megabyte). A bound is proved by a crafted file of a few hundred kilobytes that finishes in well under a second, or by a limit patched down to a few units; never by a test that spends seconds. Measured with the fixes: the largest legal CSV (41 MB, 1 million cells) 2.7 s and 124 MB over the interpreter; the largest legal XLSX (20 000 x 50 cells) 8 s and 34 MB over.
  Evidence: `tests/test_xlsx_hostile.py`, `tests/test_pdf_hostile.py`; security review of b1c4e60 (H1, H2, H3). Status: active

#### L-P1-I3-10 (security) Put a rule that every body must obey in the body's model, and prove it by walking the published API
`refuse_reserved` was applied in the generic `/commands/*` endpoint and forgotten on the two upload routes, which build their commands from the same `request_model` bodies. A check in each route is a check a new route can forget. It now sits in the model validator `request_model` adds (mode `before`, so it runs on a body that is otherwise incomplete), and a test walks `app.openapi()` and posts a reserved value to every route whose body is one of those models, and fails if any route with a `source` field is not one. Evidence: `packages/tl-api/tests/test_api_reserved_identifiers.py`; security re-review of b5f5d41.

#### L-P1-I7B-3 (security) A preview token must hash the plan, not the viewer or the clock
Hashing `permitted`, `access`, the dry run's findings or a resolved `+2h` would make the token differ between the agent that proposed and the person that accepted (and between a preview and its confirmation a second later), so every proposal would fail as stale. The token is the SHA-256 of the record id and version, the command line and the planned commands' type and fields; a relative reminder time stays as typed and is resolved when it runs. The confirmation still plans again with the caller's own `holds` and refuses what they may not run. Evidence: `token_of` in `tl_core/threads/planner.py`; `test_the_token_names_the_plan_and_not_who_may_run_it`.

- **L-P1-I7A-15** · 2026-10-20 · tags: security, process
  Every new reader of records that arrives after a confidentiality rule exists (a worker, a dispatcher, a registry list, a thread route, a key or mention resolver) is a leak until it reads as a viewer. Automation has no session, so it needs a viewer of its own: `viewer_of(conn, actor)` gives every service actor the lowest viewer (what it may run and what it may read are separate questions) and never a person's clearance. Three places leak that the record reads do not show: the event log (a stream id of a record's thread, an enrichment value or an invocation names its target), the error text of a lookup (a hidden record must answer exactly as a missing one, down to the message) and a "no such account" answer (an account that cannot read the record is an unknown account). Test each surface with one restricted and one privileged record and compare the hidden answer with the missing one.
  Evidence: `tl_core/integration/actor_access.py` `viewer_of`, `confidentiality.hidden_event_streams`, `threads/visibility.py`, `packages/tl-api/tests/test_integration_confidentiality.py`. Status: active

- **L-P1-I7A-17** · 2026-10-20 · tags: security, process
  The job runner wraps every job in `system_view`, so any shared parser or resolver a job kind calls (`post_message` tag detection, `handle_post`, key lookups) resolves as the system and leaks ids to the thread's readers. A `JobKind` that writes text a person supplied must run that call under `use_viewer(viewer_of(conn, <the person or service actor it acts for>))`. Audit each new JobKind for it, and test with a plain user and a restricted record. A tag that names a record the poster may not read is a leak in the other direction too: readers of a thread must not be given the ids a message tags (`read_thread` drops them; the event is hidden by the payload scan of `core.Thread`).
  Evidence: `threads/reminders.py` `settle`, `integration/actions/jobs.py` `_complete`, `test_integration_confidentiality.py::test_a_reminder_tags_only_what_the_person_who_set_it_may_read`. Status: active

- **L-P1-I5-2** · 2026-10-18 · tags: security, tests
  The viewer defaults to the lowest clearance (ADR-0016), so a test helper that reads a record *after* the test raised its class reads nothing and fails with "not found". Run such a read inside `use_viewer(<a controller>)`; a test that sets a class and then asserts on the record owns the viewer for the whole body. The same default makes every code path that forgets to set a viewer fail closed, which is the point: do not "fix" a red test by widening the default. Evidence: `packages/tl-modules/documents/tests/test_document_commands.py::test_confidentiality_changes_only_through_its_own_command`.
  Status: active

- **L-P1-I5-3** · 2026-10-18 · tags: security, tests
  A child record (a thread, a clock, a revision) is readable only when its parent row is, and a child whose parent row cannot be found is hidden from everyone. A scenario that appends module events raw must therefore point each child at the stream it made for the parent (`PARENTS` in `tests/webhooks/scenario.py`), and must not use a sample payload that changes the class of a record the subscription owner reads. Evidence: the webhook catalog contract failed with the 40 events of the child types until the scenario was fixed.
  Status: active

#### L-P1-I4-20 (security) A mark the module relies on must be a value a client cannot set, and checked in two fields
The module told its own flags from a person's by the event source `svc:schedule`; the API's source pattern accepted that string, so a person could flag a link with it and have the module restore it. `svc:` is now a reserved source prefix (`tl_core.services.reserved`, with the API walk test), and the module also requires the actor of the flag event to be the service. When a module keys behaviour on a field of an event, grep every route that lets a client write that field, and test the forgery (a flag with the module's source and a person's actor stays flagged). Evidence: `tests/test_publish.py`, `test_api_reserved_identifiers.py`.

- **L-P1-SEC1-1** · 2026-10-17 · tags: security, tests
  A value that grants rights must not be a field of the shared command model: `TransitionWorkflow.actor_roles` was "trusted input" by comment only, and every entry point that builds a command from outside data (HTTP body, accept body, a CLI option, a TUI menu, the sim client) could fill it. Make it an argument of the handler that only the entry point's authenticated code can pass (the pattern of `by_module`), with "none" as the default. When a review finds one such hole, grep for every reader of the field and every writer of a similar one (here: `actor_roles`, the accept body `roles`, `?role=`, `--role`) before fixing only the route reported.
  Evidence: `tl_core/workflow/roles.py`, `test_api_workflow_roles.py::test_the_walk_finds_the_bodies_and_none_takes_workflow_roles`, ADR-0013 addendum. Status: active

#### L-P1-I8-2 (security) Counts in a stored report are data for every reader
The impact report of a package is stored in an event the whole company can read, so its record counts are taken as the lowest reader (`confidentiality.LOWEST`), never as the analyst. A count that includes a restricted record tells every reader that one exists. Evidence: `tl_mod_schemareg/analysis.py` `gather_facts`.

#### L-P1-I8-6 (security) A reclassified parent leaves its children in the lake unless the sync looks for them
`last_seq` moves for the document that is reclassified, not for its revisions, so "replace the rows whose `last_seq` changed" left the revisions (and their core records and values) of a newly restricted document in silver, and never copied them back after a declassification. The sync now deletes every silver row with a hidden record at an end and copies the readable records of the confidential families that the lake lacks. Storing the hidden ids in the lake to compare with was wrong: it put the ids of restricted records into a table every reader can query (`test_confidential_rows` caught it). Evidence: `tl_lake/sync.py` `_purge_hidden`, `_visible_again`; `packages/tl-lake/tests/test_document_silver.py`.

#### L-P1-I8-10 (security) Reserve the source and correlation prefixes of a new bulk writer in the same commit
`tl_core.services.reserved` lists the source prefixes (`svc:`, `compensation:`, ...) and correlation prefixes (`derive:`, ...) that no client command may carry. The loaders write as `legacy:<system>` with a `load:<ulid>` correlation id, so both were added there; compensation still reverses the ids the run recorded, not the events that carry the correlation id. Evidence: `reserved.py`; `LoadRun.Loaded.record_ids`.

- **L-P1-I6-6** · 2026-10-20 · tags: security, ledger
  A feed card made by the generic rules is hidden only through the records it is tagged with, so an event that names no record in its payload makes a card that nobody can hide: the correspondence events (`Correspondence.Defined`, `ClearanceGranted`) and `File.Processed` (it carries the file, not the record) leaked "ctl defined a commercial" and "svc:scanner processed 2 files". Tag a confidential stream's events with the stream, look the record of a file event up in `cur_files`, and test per reader by comparing counts with a reader who may read nothing: a summary holds no token to search for. Cards projected earlier need `just rebuild-projections feed`.
  Evidence: `tl_core/feed/cards.py` (`subjects_of`), `tl_core/projection/feed.py` (`_subjects`), `test_the_feed_cards_do_not_tell_a_reader_what_happened_to_what_they_may_not_read`. Status: active

- **L-P1-UX-1** · 2026-10-21 · tags: process
  Narrow Allowed paths plus a consequential pin cost the most time in P1-UX: a test or snapshot outside the paths broke only because the screen now showed the intended words, and each one cost a block, decide, respawn, regate, review loop of 20-50 minutes. Skill rule 12 now lets the author update such a pin, keep a technical-mode counterpart and list it in the report; size work by coherence (a builder piece per area), not many tickets with narrow paths.
  Evidence: T05, T08c, T09b, T10 reports; `5a05125`. Status: active

- **L-P1-UX-2** · 2026-10-21 · tags: tui, tooling
  Never name a Textual `App` attribute `display`: it is a CSS property, so the display mode lives on `app.display_mode` and `mode_of` takes the app (or any object with `display_mode`), never a widget; a widget gives plain mode silently. A `DataTable` consumes Enter, so a register opens records on `RowSelected`, not a priority Enter binding. A widget whose text depends on the mode defines `refresh_for_display_mode()`.
  Evidence: D10, D22; `tl_tui/display.py`; S2 and T00 reports. Status: active

- **L-P1-UX-3** · 2026-10-21 · tags: tests
  A fixed-date fake world needs a pinned today: tests that read the wall clock broke on trunk in October 2026 (domain_screen, fixed in `2e8285c`) and the same class will break again. Pass a clock or pin `today` in the world builder instead of reading the system date. Seed a fake with the shape the screen needs (`add_stored_record`, `metadata_by_type`, a labelled `Labels`), or a plain-word test passes for the wrong reason.
  Evidence: STATE TRAPS; T01, T05, T08c reports. Status: active

- **L-P1-UX-4** · 2026-10-21 · tags: process
  Verify every gate path exists before dispatch: `just gate` with a missing test path exits 4 and reads red (T10 named `test_help_screen.py`, which did not exist). A tl-tui ticket is always `review: full`: `reviewer-lite` excludes tl-tui, and T05 and T09e merged as lite before this was learned (D32).
  Evidence: T10 Q1; D32. Status: active

- **L-P1-UX2-1** · 2026-10-22 · tags: process, licences
  Read a dependency's licence from its installed metadata (`importlib.metadata`, `dev/tools/check_licences.py`) before an owner decision is framed as "permissive": textual-image was approved on that word and is LGPL-3.0-or-later, so S4 stopped on its first attempt and a replacement (rich-pixels 3.0.1, MIT) needed a second decision. A wheel with no licence field and only a LICENSE file needs a named allow-list entry, not a looser rule.
  Evidence: S4 report, STATE D9, `dev/tools/check_licences.py` (`MIT_FILE_ONLY`), `caf2a9a`. Status: active

- **L-P1-UX2-2** · 2026-10-22 · tags: process, tooling
  A container restart ends every running workflow run and agent; the work on disk survives. Resume a lost run by its run id, from its last commit, instead of dispatching the piece again, and check `git status` in the worktree before anything is re-run. P1-UX2 lost work to three restarts this way.
  Evidence: `docs/reports/P1-UX2.md` (Deviations), STATE TRAPS. Status: active

- **L-P1-UX2-3** · 2026-10-22 · tags: tui, standards
  The columns of a company standard hold codes (`STR`, `ISO`, `PIP`, `47`). A screen shows plain words only if the standard's code lists are read: `list_code_lists(scope)` gives `{list: {code: label}}` and `labels_load` keys each list by its column and by its list name. A new log that shows a standards column needs one test with a code in the cell (plain shows the label, technical keeps the code).
  Evidence: S3 report (D10), `labels_load.py`, `test_standard_code_labels.py`. Status: active
