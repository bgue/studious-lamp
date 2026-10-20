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
- **L-P0-I5-A8** · 2026-10-09 · tags: tooling, ledger
  pg8000 differences that the adapter hides: it ignores libpq `options` (the schema goes in as the startup parameter `search_path`);
  it raises `IntegrityError` only for SQLSTATE 23505, so `engine.py` re-raises every class-23 error as `IntegrityError` (the append-only
  trigger, NOT NULL); it has no blocking wait for `LISTEN`, so `NotifyListener` runs `SELECT 1` every 50 ms and drains
  `conn.notifications`; result coercions are `register_in_adapter(oid, fn)` with fn taking the text value. The loader behaviour that
  `tl_core` relies on (canonical JSON text, ISO UTC timestamps, 0/1 booleans, int sums) is the same under both drivers.
  Evidence: `postgres/engine.py`, `postgres/notify.py`; 150 adapter tests pass on both adapters. Status: active
- **L-P0-I8D-1** · 2026-10-10 · tags: env, tooling
  pg8000 talks TLS to a loopback Postgres by default, and every statement pays for it: a seed of 1,067 events took 13.6 s with TLS and 9.7 s without. The adapter
  URL now accepts `?sslmode=disable` (the bench datasets use it on loopback). Projection work on Postgres is statement-bound at about 0.5 ms per statement
  (the projectors run 17 statements for a new record and about 15 for a link event, before the ledger's three), so a bulk load or rebuild of 100k records takes about an hour there against 8 minutes on SQLite: count statements
  before optimising anything else.
  Evidence: `docs/reports/P0-I8-D.md`; `tests/bench/bench_data.py`; `packages/tl-adapters/tests/test_postgres_url.py`. Status: active

### tooling: Tool gotchas: pyright strict, ruff, Textual, shell and Bash traps.

- **L-P0-I1-6** · 2026-10-09 · tags: tooling
  pyright strict flags `@contextmanager` functions annotated `Iterator[X]` (use `Generator[X]`), and ruff's
  `E501` applies to docstrings and comments at 100 columns, so wrap prose when writing modules. Provided test files
  must be ruff-clean before commit because implementers may not edit them.
  Evidence: scratch builds of T04b and T07. Status: active
- **L-P0-I1-10** · 2026-10-09 · tags: tooling
  A Protocol attribute (`ledger: Ledger`) is invariant, so an adapter that narrows it (`SqliteLedger`) fails pyright
  strict; declare Protocol attributes that implementers may narrow as read-only `@property`.
  Evidence: T11 blocked on 11 pyright errors; `tl_core/uow.py`. Status: active
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
- **L-P0-I6C-8** · 2026-10-10 · tags: env, tooling
  Two implementer reports found shell traps in the Bash tool: `pkill -f <pattern>` matches the shell that runs it when the pattern is in the command line (exit 144), and a
  multi-line `cat > file <<'EOF'` inside a `&&` chain once hung until the 120 s timeout while the Write tool created the file at once. Use `pgrep` and a PID, and write files with
  the Write tool.
  Evidence: `docs/reports/P0-I6/P0-I6-T41.md`. Status: active
- **L-P0-I8A-10** · 2026-10-10 · tags: tui, tests
  `pytest --snapshot-update` rewrites the tracked `snapshot_report.html` at the repository root as well as the `.raw` files: restore it with `git checkout snapshot_report.html` before committing. A new palette command or key map entry changes the palette snapshot (`test_snapshots_links.py::test_command_palette`) and the key map context list in `test_keymap.py`.
  Evidence: P0-I8-S19 (`git status` after the update). Status: active
- **L-P0-I8A-9** · 2026-10-10 · tags: tooling, security
  Hostile numbers and nesting raise errors other than the ones a parser documents: `yaml.safe_load` raises `RecursionError` (50,000 nested levels) and `ValueError` (integers over 4300 digits); `float(huge_int)` raises `OverflowError`; `json.dumps` of such an integer raises `ValueError`. Wrap the parse, the float conversion and the message formatting, and turn each into the domain error.
  Evidence: `tests/settings/test_exchange.py::test_a_file_that_breaks_the_yaml_reader_is_a_document_error`, `packages/tl-core/tests/test_settings_values.py::test_a_number_too_large_for_a_float_is_out_of_range_not_an_error`. Status: active

### tests: Test conventions that no test enforces.

- **L-P0-I1-11** · 2026-10-09 · tags: tests
  A concurrency invariant needs a deterministic seam, not repetition: the lost-wakeup test replaces the publisher's lock
  with one that runs a second writer right after a given release, and a deliberately wrong `LeakyPublisher` proves the
  test can fail. Three clean runs of a racy test prove nothing. Threads in such tests are `daemon=True` and joined
  with a timeout so a regression fails instead of hanging the suite.
  Evidence: `packages/tl-core/tests/test_bus.py`; mutation (flag cleared outside the lock) fails the test. Status: active
- **L-P0-I4-B8** · 2026-10-09 · tags: tests, cli
  `typer.testing.CliRunner.invoke` catches exceptions and returns them on the result, so a CLI test that only asserts "nothing
  changed" passes against a command that crashes (it passed against a `NotImplementedError` stub). Assert `exit_code` and
  `result.exception is None` in every CLI test, including negative-space ones. Implementer-found, T25.
  Evidence: `docs/reports/P0-I4/P0-I4-T25.md`; `packages/tl-cli/tests/test_cli_file_reconcile_exit.py`. Status: active
- **L-P0-I8A-4** · 2026-10-10 · tags: tests
  Extends L-P0-I5-B6. A fake clock handed to code that compares it with event times must be the real clock plus an offset: a fixed fake "now" taken at set-up was already behind the `recorded_at` of every event the test wrote, so every entry looked "not yet in force" (8 of 12 reader tests failed with the default value). Move time in such a test by changing the offset.
  Evidence: `tests/settings/test_reader.py` `Clock`. Status: active
- **L-P0-I8A-7** · 2026-10-10 · tags: tests, process
  Adding a command to the API table, a tool to `PROPOSABLE_TOOLS` or an event type to the catalog breaks tests that assert literal counts or lists elsewhere: `len(COMMANDS) == 17` and the agent-refusal count of 13 in `tl-api`, `PROPOSE_TOOLS` and `PROPOSING` in `tl-mcp`, `register_write_tools`' assertion on the tool modes, the table lists of `test_generate.py` and `test_ddl.py`, and the webhook scenario. Run `just test` once after the contract amendment and fix all of them in the same commit.
  Evidence: the first full `just test` of P0-I8-A (3 failures, then 1 more in `tl-api`). Status: active
- **L-P0-I8B-7** · 2026-10-10 · tags: process, tickets, tests
  Run `pyright` over a provided test before dispatching it: copy the `.py.txt` into its test directory, run `uv run pyright <package>`, delete the copy. Two provided tests (a
  `tuple(row)` on `Row | None`, a subscript of `get_record_by_id(...)`) passed pytest against the reference but failed `just check` on the ticket branch, and the ticket forbids editing the
  provided file, so the implementers correctly stopped as Blocked and the supervisor had to fix the test on the branch and in the provided source.
  Evidence: T22 at 197b81c, T23 at 938c8ce. Status: active

### process: Process rules: relays, workers, tickets, gates, concurrency and recovery.

- **L-P0-SETUP-9** · 2026-10-09 · tags: process, env
  Workflow agent concurrency is min(16, CPUs - 2); this container has 4 CPUs, so 2 agents run at once. Size DISPATCH
  batches at 2–4 tickets.
  Evidence: workflow-authoring reference; `nproc` = 4. Status: active
- **L-P0-SETUP-10** · 2026-10-09 · tags: process, tooling
  Git cannot hold a branch `p0/i1` and a branch `p0/i1/t01-…` at the same time (ref namespace clash). Ticket branches are
  siblings: `p0/i1-t01-<slug>`. The branch passed by the orchestrator overrides a ticket's Branch field.
  Evidence: `fatal: cannot lock ref 'refs/heads/p0/i1/t01-monorepo-scaffold'` in the first ticket-batch run. Status: active
- **L-P0-I5-O3** · 2026-10-09 · tags: env, process
  Refines L-P0-I3-O1. Before resuming a ticket-batch workflow after a restart, read its journal. For every implementer
  with no `result` line, remove its worktree and delete its ticket branch (`git worktree remove --force`, `git branch -D`),
  so the rerun's `git worktree add -b` starts clean. Keep a worktree whose implementer finished; an interrupted review
  re-creates its own detached worktree. Resume reviewers and supervisors with SendMessage, and tell them their
  background test runs are gone.
  Evidence: second restart during P0-I4/I5; resumed three workflows and four agents. Status: active
- **L-P0-I5-O5** · 2026-10-10 · tags: process, worktrees
  Never bulk-remove `/home/user/wt/review-*` or ticket worktrees while any ticket-batch workflow is running. Reviewers
  work in those directories, and removing one mid-review breaks that review. Clean up only the worktrees of workflows
  that have finished, by exact name, and check the running workflows' journals for `started review` lines first.
  Evidence: the orchestrator removed two in-flight P0-I4 review worktrees (T43, T46) during the P0-I5 cleanup. Status: active
- **L-P0-I8B-6** · 2026-10-10 · tags: process, tests
  With several workstreams sharing four CPUs the whole `just test` took 13.5 minutes (4081 tests). Start it with `run_in_background` and wait with a foreground `timeout N bash -c 'while kill -0 PID ...'`
  rather than a polling `sleep`; `pkill -f <pattern>` killed the shell again (see L-P0-I7-B5). A stub ticket's implementation notes go in comments, not the docstring, when the docstring reaches
  the committed OpenAPI document.
  Evidence: this round's full run; `docs/tickets/P0-I8/T21-api-types.md`. Status: active
- **L-P0-I8C-6** · 2026-10-10 · tags: process, gates
  Run `just check` on the base before relaying it to implementers. A one-line E501 in a supervisor commit made every ticket's acceptance
  command fail, so a whole batch came back BLOCKED for a reason outside the tickets and cost a round. `just check` also lints `dev/`,
  which `pyright` does not cover.
  Evidence: S44 commit f01ab70 (`dev/tools/scan_secrets.py:2`), fixed in the following commit. Status: active
- **L-P0-I8A-8** · 2026-10-10 · tags: process
  A ticket's test count must be counted from the provided file (`grep -c "^def test_"`), not remembered: two of the first six tickets named the wrong number and the implementers had to stop and ask.
  Evidence: reports `docs/reports/P0-I8/P0-I8-T04.md` (8 named, 7 in the file) and `P0-I8-T05.md`. Status: active
- **L-P0-I6A-5** · 2026-10-10 · tags: process, tickets
  A batch may hold only tickets whose dependencies are already merged on the base. T02 and T03 were verified against reference
  implementations that included T01, and their provided tests call T01's handlers (and T03's call T02's queries), so in one batch of
  four three came back BLOCKED on a test they could not make pass. Before dispatch list for each ticket the code its provided test
  imports and calls; if another ticket owns it, the two are not independent. After the fact the fix was an integration merge of the
  base into the ticket branch and a re-run of its tests on both adapters.
  Evidence: relay outcomes of workflow wkzasjo4a; T03 passes 13 of 13 only with T02 merged. Status: active
- **L-P0-I2-3** · 2026-10-09 · tags: process, tests
  A supervisor-written stub (names, signatures, docstrings) plus a provided test file under `docs/tickets/<inc>/provided/`
  plus a spec verified against a scratch reference implementation gave first-attempt passes for 6 of 7 implementer tickets (the seventh, T04b, was flagged only for committing its report file). Keep
  the reference implementation until the ticket merges; it is the takeover path. State in the ticket that the stub's
  `STUB:` docstring paragraph must be removed (T01 left it).
  Evidence: P0-I2 reports T01, T04, T04b, T06, T08, T08a, T10. Status: active
- **L-P0-I2-B7** · 2026-10-09 · tags: process
  The ticket workflow tells implementers to commit their report, so list `docs/reports/<inc>/<ticket-id>.md` in every
  ticket's *Allowed paths* and say "commit your report". A ticket that says "return it in your final message" produced one
  review round lost to a committed report (T12) and one report left uncommitted in a worktree (T15).
  Evidence: T12 attempt 1; T15 worktree; tickets T16b onward. Status: active
- **L-P0-I8E-3** · 2026-10-11 · tags: process
  A brief bullet that no increment plan names gets built by nobody: "upgrade tooling" (§16 ops baseline) and "comments" appear in no ticket of `05-phase0-plan.md`, and the audit at the end found them missing or replaced. At the start of a phase map every bullet and exit clause to an increment ticket, and check the map at each increment report. Likewise a CI workflow that is never pushed is never tested: the repository had no workflow run after eight increments.
  Evidence: `docs/reports/PHASE-0-AUDIT.md` bullets 3f and 8; GitHub Actions run list for the repository (empty, 2026-10-11). Status: active

- **L-P0-I8-O1** · 2026-10-11 · tags: process, budget
  The run hit the account usage limit four times. Each hit followed a stretch with about 8 or more agents active at once
  (3+ supervisors, 2+ ticket workflows of 3, 2 reviewers). After capping at about 3 active agents or workflows the run
  finished without another hit. Recovery each time: read the journal, remove implementer worktrees with no result,
  resume workflows by run id, resume supervisors with a message.
  Evidence: `docs/reports/STATUS.md` timeline; supersedes the 3–4 cap of L-P0-I5-O4. Status: active

- **L-P0-I8-O2** · 2026-10-11 · tags: process
  Read the run's scope and stop conditions from `docs/build-spec/KICKOFF.md` at every phase boundary, not from a summary
  or memory: a compacted summary recorded "to the end of Phase 5" while the file said "until the end of Phase 0".
  Evidence: `docs/build-spec/KICKOFF.md` MISSION. Status: active

### security: Domain: security rules for services that take client input.

- **L-P0-I4-B6** · 2026-10-09 · tags: process, api
  Security review of the upload service found four fixable things a test-by-mutation pass had not: a dedupe gate that counted
  quarantined rows (so a second user could read a file before its scan), `hmac.compare_digest` on a client-controlled `str`
  (raises on non-ASCII), a silent public fallback secret, and a global rejected-hash check (kept on purpose, recorded as a
  decision). Rules: gate any "no bytes needed" shortcut on the state that grants read access, compare secrets as bytes, fail
  closed on missing secrets, and serve client-typed files as attachments with `nosniff`.
  Evidence: `docs/tickets/P0-I4/README-B.md` D8, D9, D12, D13; `tests/services/test_file_service.py`. Status: active

- **L-P1-I0B-1** · 2026-10-11 · tags: tests, process
  To put a service on a second database, convert the existing suites to the parity fixtures first (the `env` fixture takes `new_db` instead of `tmp_path / "tl.db"`) and write no parallel tests. Of 14 CLI test files (about 400 tests) only 8 failed on Postgres once the source took a `DbTarget`, all in hand-written SQL: an integer for a boolean column (`0` for `deduplicated`), a bare year for a timestamp (`'2026'`), and raw `sqlite3`. The failing list is then the exact ticket list.
  Evidence: `docs/tickets/P1-I0/README-B.md` B9; `packages/tl-cli/tests/test_cli_wf.py`, `test_cli_file_reconcile.py`. Status: active
- **L-P1-I0B-2** · 2026-10-11 · tags: process, cli
  `Path(os.environ["TL_DB"])` turns `postgresql://u:pw@h/db` into `postgresql:/u:pw@h/db` and the SQLite adapter then creates a file of that name, with the password in it. Any entry point that takes a database from a flag or the environment goes through `tl_adapters.db.as_target`, and prints `display_target`. A command group that still imports `tl_adapters.sqlite` does this silently, so a half-converted CLI is worse than an unconverted one: convert the root callback and every group in one increment.
  Evidence: `tl_adapters/db.py` (`as_target`), `packages/tl-adapters/tests/test_backend.py::test_as_target_keeps_a_url_whole_and_makes_a_path_of_anything_else`. Status: active
- **L-P1-I0B-3** · 2026-10-11 · tags: process, tooling
  The shell trap of L-P0-I6C-8 hit a supervisor too: a `cat > file <<'EOF'` of 60 lines inside a `&&` chain hung until the 120 s timeout and left a shell running; the file was never written. Write test and doc files with the Write tool, and kill only the PID of the shell you started.
  Evidence: S32 round, `packages/tl-cli/tests/test_cli_target.py`. Status: active
- **L-P1-I0B-4** · 2026-10-11 · tags: security, tests
  Tests of "the password is never printed" must try the spellings a URL can take, not one: a capital `POSTGRESQL://`, `postgresql+pg8000://`, an unescaped `@` in the password (`u:Se@Cr@host`), a `?password=` query parameter, a URL with no user, and a foreign scheme such as `mysql://u:secret@h/d`. The first review of the backend found each of them leaking or creating a directory named after the URL. A "read-only" snapshot is a claim to test with raw `CREATE TABLE`/`DELETE` on both adapters: SQLite's `read_tx` accepted writes until it set `PRAGMA query_only`.
  Evidence: `packages/tl-adapters/tests/test_backend.py` (`test_a_url_that_is_not_a_usable_postgres_url_is_refused_without_echoing_it`, `test_the_read_connection_refuses_raw_sql_writes`). Status: active
- **L-P1-I0A-1** · 2026-10-11 · tags: tests, tooling
  A test helper module shared through pyright `extraPaths` needs a name no other test directory uses: `tests/webhooks/world.py` already exists, so `from world import World` in a second directory resolved to the wrong module under pyright (175 errors) and would clash in `sys.modules` at run time. The auth tests use `authworld.py`.
  Evidence: `tests/auth/authworld.py`; first `pyright` run after adding `tests/auth`. Status: active
- **L-P1-I0A-2** · 2026-10-11 · tags: security, ledger
  Anything that must survive a refusal (the failed-sign-in counter) cannot be written inside the unit of work that then raises: leaving the `with` block by exception rolls it back. `tl_core.auth.sessions` reads in a snapshot, hashes outside any transaction, writes the counter in a short transaction and raises after that block ends. Never hash inside a write transaction: it holds the single writer lock.
  Evidence: `tl_core/auth/sessions.py` module docstring; `tests/auth/test_sessions.py::test_five_failures_lock_the_name_even_against_the_right_password`. Status: active
- **L-P1-I0A-3** · 2026-10-11 · tags: tests, ledger
  Both adapters take the ledger's single writer lock when a write transaction begins, so a barrier test of two concurrent roster changes passes with or without a guard row (a mutation that removed the guard survived three runs). Do not add serialisation rows or tables for roster races; keep a test that fails if the lock ever becomes finer.
  Evidence: `postgres/engine.py` `write_tx`; `tests/auth/test_accounts.py::test_two_admins_cannot_disable_each_other_at_once`. Status: active
- **L-P1-I0A-4** · 2026-10-11 · tags: tests, process
  Adding catalog event types breaks more than `test_catalog.py`: the webhook contract tests assume every catalogued type is delivered (`tests/contract/test_webhook_catalog_contract.py`, `tests/parity/test_webhooks_parity.py`), so internal types must be subtracted there; the lists in `test_ddl.py` and `test_generate.py` need the new tables; a changed `ErrorBody` needs `uv run python -m tl_api.openapi` (about 100 s) before `just check` passes. `packages/tl-mcp/tests/test_dev_gen.py` fails at teardown while `packages/tl-schema` has uncommitted changes, so run the full suite after committing generated files.
  Evidence: the first full `just test` of P1-I0A (3 failures and 1 teardown error). Status: active
- **L-P1-I0A-5** · 2026-10-11 · tags: tests, api
  The Starlette `TestClient` (httpx) refuses a header value with a non-ASCII character. To test a bearer token with one, pass the latin-1 encoded bytes (annotate as `Any` for pyright); the server reads headers as latin-1.
  Evidence: `packages/tl-api/tests/test_auth_roles.py::test_garbage_and_look_alike_tokens_are_401_not_500`. Status: active
- **L-P1-I0A-6** · 2026-10-11 · tags: process, budget
  With workstream B running at the same time the full `just test` took 22 minutes (5,480 tests). Run the packages a change touches first (`tests/auth`, `packages/tl-api`, `tests/archive`), the full suite once per round, and wait for it with `timeout N bash -c 'until grep -q "^EXIT" log; do sleep 10; done'` after starting it in the background.
  Evidence: `/tmp/p1i0a-test.log` of 2026-10-11. Status: active
- **L-P1-I0A-7** · 2026-10-11 · tags: security, api
  A security review found three classes of mistake worth checking in any credential code: (1) a slow hash (or any slow step) inside a write transaction holds the global writer lock, so a flood of sign-ins stalled all writes for 17 s: hash first (`prepare_password`), write after; (2) a lock or message that differs by account kind or history is an oracle for which names exist, so every lock is the same 15 minutes; (3) a token, session or stream that is checked once stays valid after revocation, so long-lived streams re-check on a timer.
  Evidence: D6 review of P1-I0 S2b and S2c; `tests/auth/test_review_fixes.py`, `packages/tl-api/tests/test_auth_review.py`. Status: active
- **L-P1-I0A-8** · 2026-10-11 · tags: api, tooling
  FastAPI turns any exception raised while it reads a request body into a 400, so a body-size guard that raises its own error never reaches its handler. Raise Starlette's `HTTPException(413)` from the wrapped `receive` instead and map status 413 in the app's HTTP error handler. Also: a stub app that has no route for a path never reads the body, so test the guard through a route that does.
  Evidence: `BodyLimitMiddleware` in `tl_api/auth.py`; first run of `test_a_chunked_body_over_the_limit_is_413_too`. Status: active
- **L-P1-I0A-9** · 2026-10-11 · tags: tests, api
  In this FastAPI version `app.routes` holds `_IncludedRouter` objects for included routers; the real routes are in `.original_router.routes`. To list every route's guard action walk those; `guard()` puts the action on its dependency as `.action`.
  Evidence: `route_actions` in `packages/tl-api/tests/test_auth_review.py`. Status: active
- **L-P1-I0A-10** · 2026-10-11 · tags: security, tooling
  `hashlib.scrypt` raises `ValueError` for parameters its own rules refuse (N must be below 2^(16 r)), so a stored hash whose parameters pass a bounds check can still crash a sign-in; treat that `ValueError` as a wrong password after a stand-in hash. Postgres also rejects a NUL in any text parameter and a lone surrogate does not encode to UTF-8: validate sign-in input before it reaches a query, or the pooled connection breaks.
  Evidence: `password.verify_password`, `sessions.authenticate`; `tests/auth/test_review_fixes.py::test_unstorable_input_is_invalid_credentials_and_the_connection_still_works`. Status: active
- **L-P1-I0A-11** · 2026-10-11 · tags: process, tickets
  L-P0-I6A-5 again: T04's provided tests sign in through `/auth/sign-in` and the client's `sign_in` (T03's code), but its `Depends on` named only the supervisor pieces, so both went out in one batch and T04 came back BLOCKED on tests it could not run. For each ticket list the routes, functions and client calls its provided tests use, name the ticket that owns each in `Depends on`, and dispatch dependent tickets in a later batch (or merge the provider into the base first).
  Evidence: T04 blocked at 36f03d2; resolved by merging T03 into the base and the base into the ticket branch. Status: active
- **L-P1-I0A-12** · 2026-10-11 · tags: process, tickets
  Stub STEPS for a client method must not be looked up by the bare function name: the route and the client method share names (`sign_out`, `whoami`), and the server's steps (`request`, `ctx`, `me`) were pasted into three client stubs where they could not run. The implementer noticed and disclosed it. Key steps by module (`name@client`, `name@routes`) and read the pasted Interfaces of a ticket once before dispatch.
  Evidence: `docs/reports/P1-I0/P1-I0-T03.md` deviations; `docs/tickets/P1-I0/T03-api-auth.md`. Status: active
- **L-P1-I0A-13** · 2026-10-11 · tags: security, tests
  A pytest monkeypatch of a private function (`pw._scrypt`) used by provided tests fixes its call shape for as long as a ticket is in flight: to add a parameter (a hash lane) without breaking those tests, carry it in a `ContextVar` and keep the positional signature. Likewise keep `pw._gate.acquire()` and `release()` callable with no arguments.
  Evidence: `password.HashGate`, `_PUBLIC_LANE`; provided tests `t03-test_api_auth.py.txt`, `t04-test_api_admin.py.txt`. Status: active
- **L-P1-I0A-14** · 2026-10-11 · tags: security, postgres
  A lone surrogate in a bound parameter makes pg8000 raise `UnicodeEncodeError` half way through a message; a pooled connection that saw it is out of step with the server and fails every later statement (`ResourceClosedError`). Validating input at the services is not enough for a future path, so the engine's `handle_error` hook drops that one connection (`is_disconnect`, pool kept). A header that arrives in several lines must be read as its last line when a proxy adds its own; IPv6 sources must be keyed by /64 or the limit is free to rotate.
  Evidence: `packages/tl-adapters/tests/test_postgres_poisoned_connection.py`; `tests/auth/test_review_round3.py`; `packages/tl-api/tests/test_ratelimit.py`. Status: active
- **L-P1-I0A-15** · 2026-10-11 · tags: tooling, cli
  Typer 0.27 carries its own copy of click (`typer._click`). `isinstance(param, click.Option)` is False for its commands, so a hook that walks the command tree with click's classes silently does nothing, and tests run with the dev default pass anyway. Walk commands by attribute (`params`, `commands`, `opts`) and test the hook where the default differs (a non-dev `TL_ENV`, a session).
  Evidence: `tl_cli/actor_hook.py`; `test_cli_session.py::test_a_signed_in_session_is_the_default_actor_everywhere` fails with the hook removed. Status: active
- **L-P1-I0A-16** · 2026-10-11 · tags: process, tickets
  A script that pastes repo files into a ticket's *Interfaces* must run against the stubs, not the reference implementation. While mutation checks had the reference copied in, the generator wrote T08 and T09 with the full solution; it was caught by counting `NotImplementedError` in the generated tickets. Generate tickets from a clean tree, restore the stubs before generating, and `git grep` a line that only the reference has.
  Evidence: commit P1-I0-S5b (amended); `grep -c NotImplementedError docs/tickets/P1-I0/T0*.md`. Status: active
- **L-P1-I0A-17** · 2026-10-11 · tags: process, tickets
  L-P1-I0A-11 applies to the supervisor's own tests: a test of the wiring that needs a stub's body (F10 opens the screen) fails until the ticket merges. Hold it in `docs/tickets/<inc>/held/` and add it with the merge. Provided tests must not run another ticket's command either: the T07 tests first used `tl login` (T06) and `tl whoami`; they now sign in through `auth_support.sign_in`, which calls the core and writes the session file as the command does.
  Evidence: `packages/tl-cli/tests/auth_support.py`; `docs/tickets/P1-I0/held/`. Status: active
- **L-P1-I0A-18** · 2026-10-11 · tags: tooling
  `Monitor` loops that wait with `pgrep -f NAME` match their own command line and never end. Wait on a pid, a marker file or a `grep` of the output file instead.
  Evidence: three monitors on `mut2.sh` expired without an event. Status: active
- **L-P1-I0A-19** · 2026-10-11 · tags: process, tests
  The third base-red relay of Phase 1 (L-P0-I8C-6): `just check` plus the new tests were green, but the packages touched by the wiring (tl-cli, tl-tui) had tests of their own that pin the old behaviour (`tl tui` call arguments, the key map's contexts, the palette snapshot). Before relaying a batch run the whole suite of every package the supervisor pieces touched, in parallel shards (`pytest -q packages/tl-cli packages/tl-tui packages/tl-api`, `tests`, the rest), and read the failure list, not the exit code.
  Evidence: S5b relayed with 5 red tests; fixed in P1-I0-S11. Status: active
- **L-P1-I0A-20** · 2026-10-11 · tags: security, cli
  An option default that is only used when the flag is left out does not protect anything: `--actor user:root` bypassed the session check that the default went through. Put the check on the value (a click callback runs on defaults and explicit values alike), and let the target decide how much a stated identity is worth: a file you own, versus a shared database.
  Evidence: `tl_cli/actor_hook.py`, `session.check_actor`; `test_cli_session.py::test_outside_dev_no_actor_can_be_used_without_a_sign_in_not_even_a_named_one`. Status: active
- **L-P1-I0A-21** · 2026-10-11 · tags: process, tickets
  A provided test that passes `ruff` and runs can still fail `pyright` in the package it lands in, and the implementer cannot fix a copy that must stay byte-identical (fourth time: L-P0-I8B-7, L-P1-I0A-11). T08's `ApiUnavailableError(OSError("down"))` was rejected by pyright (it takes an `httpx2.TransportError`). Before a batch, copy each provided test into its target package and run `uv run pyright` and `just check` on the scratch tree, then remove the copies; never trust a run done while stubs and references were swapped in and out.
  Evidence: T08 BLOCKED at d05901f; fixed in b9c3f3f. Status: active
- **L-P1-I0A-22** · 2026-10-11 · tags: security, mcp
  A long-lived stdio server must not trust its start-up check. The MCP server now looks the agent token up on every tool and resource call (`principal_for_bearer`), so a revoked token, an expired one or a disabled agent stops at the next call; a cached principal would have kept working until the process ended. A test revokes mid-session and the mutation that caches the principal fails it.
  Evidence: `tl_mcp/identity.py`; `test_mcp_identity.py::test_a_revoked_token_stops_working_at_the_next_call_not_the_next_start`. Status: active
- **L-P1-I0B-5** · 2026-10-11 · tags: process, security
  When a security workstream (auth) and an infrastructure workstream (a second database) run in parallel, the merge hides the real conflicts in files that merge cleanly: A's CLI session had `db.is_file()`, `Path`-typed parameters and a scheme test in nine places that git merged without complaint and that only fail with a URL. After the textual merge, grep the other side's new code for the assumption (`is_file`, `Path`, `exists`, `sqlite`) and put it under a guard test (`tests/tools/test_no_sqlite_imports.py`); a stored sign-in needs a password-free key per ledger (`target_key`).
  Evidence: the merge `03f1f40`; `packages/tl-cli/src/tl_cli/session.py`, `packages/tl-cli/tests/test_cli_auth_targets.py`. Status: active
- **L-P1-I0B-6** · 2026-10-11 · tags: process, tooling
  `pgrep -f '<pattern>'` run from a Bash command whose own text contains the pattern matches that shell, and `kill` of the result kills it (exit 144): the third time after L-P0-I6C-8 and L-P0-I7-B5. Find a server you started by its port (`ss -ltnp | grep :PORT`) or note the PID when you start it, and kill that PID.
  Evidence: the seed check of S35. Status: active
- **L-P1-I0B-7** · 2026-10-11 · tags: tests, process
  A package may have a boundary test that forbids imports a feature seems to need: the simulator may import nothing from `tl_adapters` (brief 29.1, `packages/tl-sim/tests/test_contract_and_boundary.py`), so passing a Postgres URL through it had to be an opaque `LedgerTarget` that the MCP child validates, and `tl_sim/types.py` is a verbatim contract that cannot take a helper. Run the package's own tests after touching its imports, before the full gate: the first full `just test` after the merge cost 24 minutes to find four failures that `pytest packages/tl-sim` finds in 50 seconds.
  Evidence: S35 fix commit; the failures `test_the_simulator_never_reaches_the_ledger_or_a_handler`, `test_types_py_is_the_contract_of_the_fanout_plan_verbatim`. Status: active
- **L-P1-I0B-8** · 2026-10-12 · tags: tests, process
  Run the parity gate on a merged tree early: it ran 3 hours and 160 tests failed for one reason. Tests written for the file rule ("a dev setup acts as user:dev") met the server rule of the other workstream ("a Postgres target always needs a session") only after the merge. A signed-in account is an event, so every test that names a `seq` or counts events needs an offset on Postgres (`pg_support.account_events`); and a test fixture that signs in must step aside for an unreachable server (three tests of the other workstream failed on it in the next full run). To find such a class quickly, run one package on Postgres only (`pytest packages/tl-cli -m parity --adapters postgres`) before the 1-hour gate.
  Evidence: `packages/tl-cli/tests/conftest.py`, `pg_support.py`; the S35 commits 827bdcc and 2067586. Status: active

- **L-P1-I0B-9** · 2026-10-12 · tags: security, process
  When a value is a URL that carries secrets, allow-list its parts instead of deny-listing the secret ones: a denylist (`password`, `sslpassword`) missed `options=`, a different case, and `host=`/`port=`, which silently replaced the address part and made two keys name one server. `as_target` now accepts `sslmode`, `options`, `application_name` only; display shows two of them; the session key holds `options` as a hash. And a rule that the server side owns ("a Postgres target needs a session") must be checked in every helper that used the file-side shortcut ("TL_ENV=dev and the ledger exists"): the simulator's token minting was such a helper and the review found it, not a test.
  Evidence: `tl_adapters/db.py`, `tl_cli/sim_agent.py`, `test_cli_sim_agent_targets.py`; ADR-0009 addendum. Status: active
- **L-P1-I1-1** · 2026-10-12 · tags: tests, process
  Extends L-P1-I0A-4. A new catalog event type also needs the webhook contract scenario to produce it (`tests/webhooks/scenario.py`), and an event of a module record needs that record's envelope row first: module projectors raise `LookupError` without a `cur_core_record` row. The scenario appends `Record.Created` and then the module's events on one stream per module record type (`append_module_events`).
  Evidence: `tests/contract/test_webhook_catalog_contract.py::test_the_scenario_delivers_every_event_type_of_the_catalog` failed right after the module events entered the catalog. Status: active
- **L-P1-I1-2** · 2026-10-12 · tags: tests, tooling
  `csv.reader` takes a quote that is never closed as the end of the cell unless `strict=True`; use it for any file a person exported. A YAML `title:` or `description:` that contains `: ` must be quoted, or LinkML reports `mapping values are not allowed in this context` with only a column.
  Evidence: `imports/mapping.py` (`read_rows`); `schema/modules/engineering/module.yaml` first load. Status: active
- **L-P1-I1-3** · 2026-10-12 · tags: schema, tooling
  A LinkML root that imports core files shows the core classes in its `SchemaView`. A generator run on a module root keeps only the classes whose own schema carries the module's `tl:module` (`ddl.current_state_classes(view, module)`, `catalog._owner_module`), or every core table and event would be generated again under the module.
  Evidence: first prototype listed `Record` with the module's tables (`cur_core_record`). Status: active
- **L-P1-I1-4** · 2026-10-12 · tags: tests, process, database
  Two defects of the supervisor's base blocked a ticket that was otherwise right. (1) SQL ordering: SQLite sorts NULL first and Postgres last, so a report that says "no class first" needs `ORDER BY (col IS NULL) DESC, col`, and a test that checks the order must run on Postgres before the ticket goes out. (2) A provided test that builds a command with `**more` from a dict literal of mixed values is typed `dict[str, str]` by pyright and fails strict checks in the implementer's tree: give the dict an explicit `dict[str, Any]`. Before a batch goes out: pyright and ruff on every provided test in its target path, and the Postgres variant of every test that touches ordering.
  Evidence: T11 review (`_SUMMARY_SQL`, `test_cli_tag_report.py`); fixed in `reports.py` and the provided test. Status: active
- **L-P1-I1-5** · 2026-10-12 · tags: tests, process
  Extends L-P1-I0A-11. A provided test must set its world up through the module, not through another ticket's CLI command: the first draft of the tag-class CLI test loaded the standards with `tl standards load`, a command that was still a stub. Share the setup as a helper in the tree (`engcli_support.load_acme`) so tickets stay independent.
  Evidence: `packages/tl-cli/tests/engcli_support.py`, `t09e-test_cli_standards_class.py.txt`. Status: active

- **L-P1-I1-6** · 2026-10-12 · tags: tests, process
  From the T03 report. A parity run's count is not "the SQLite count twice": under `--adapters sqlite,postgres` a case that does not use the `db`/`new_db` fixtures runs once, and a database case runs on both. T03 had 28 cases on SQLite (8 without the fixture, 20 with) and 48 with both (8 + 2 x 20). A ticket's *Expected* line must give the split, or a correct run looks short.
  Evidence: `docs/reports/P1-I1/P1-I1-T03.md`; the T09a, T09e and T10c tickets state their skips. Status: active
- **L-P1-I1-7** · 2026-10-12 · tags: process, tickets
  From the T09b report. The STEPS of a ticket must name the keys of any dict a command reads back (`level`, `segment`, `message` on a tag's `violations`), because the implementer can only learn them from the provided test or the handler. `_service_errors` and `tl tag show` read the same three keys; the dict is written by the module's number check. Name the keys in the stub's STEPS or the interface block.
  Evidence: `tl_cli/tag.py` (`show`, `_service_errors`), `docs/reports/P1-I1/P1-I1-T09b.md`. Status: active
- **L-P1-I1-8** · 2026-10-12 · tags: security, architecture
  When a module adds record types, check every generic command that can reach `cur_core_record`: they load a record by id and check only its scope, so they treated a module record like a core one. A tag class or a code list could be retitled by any signed-in person with `UpdateRecord`; the review found it, no test did. A module record type now allows no generic command unless its spec lists it, and the check lives in `tl_core` (`require_generic_command`), so the API, CLI, MCP and proposals all inherit it. Related: a field that records where something came from (`origin`) must not be client input, and a flag that turns off a check (`pattern_policy`) is a separate, role-gated command.
  Evidence: ADR-0010 addendum; `tests/services/test_modules.py`, `packages/tl-modules/engineering/tests/test_generic_commands.py`, `packages/tl-api/tests/test_api_engineering.py`. Status: active
- **L-P1-I1-9** · 2026-10-13 · tags: tickets, tooling
  A stub must be clean under ruff and pyright once it is implemented, or each implementer finds the same defect: its import list has to hold every name the STEPS use (`TagOut`, `TagFamily` were missing, and a `str` passed to a `Literal` field needs a `cast`), a STEPS line must not bind a name that is never read (`made = ...` is F841), and a read typed `X | None` needs a guard the STEPS must mention. The supervisor runs the reference implementation through ruff and pyright before generating the ticket.
  Evidence: T09a, T09e, T09f and T12 reports (deviations). Status: active
- **L-P1-I1-10** · 2026-10-13 · tags: process, database
  `just test-parity` is the whole-repository parity suite and takes about 70 minutes alone (4023 s on the final tree); a tool call stops at 600 s and a background run has a default 30-minute limit that kills it with SIGTERM and no summary. Start it in the background with a log file and a 2-hour limit, and give a ticket a scoped command (a package path or `-k`) instead of "the parity run". Several parity runs at once stall (a stream test waited 25 minutes); run one at a time.
  Evidence: T09c, T09d, T09f and T12 reports; the final run. Status: active

- **L-P1-I2-1** · 2026-10-13 · tags: tickets, tooling
  Generate a stub from its reference with a script (the `ast` module: keep each signature, decorator and docstring, replace the body by a STEPS comment and `raise NotImplementedError`), and wrap the STEPS at 90 columns: a `    # ` prefix pushes any longer line past ruff's 100 and the first run gave 47 E501 in four stubs. Keep the reference in the history (commit it, then commit the stub) so a two-strikes takeover is `git checkout <sha> -- <file>`.
  Evidence: commits `1734486` (references) and the stub commit after it, P1-I2-S5 and S6. Status: active
- **L-P1-I2-2** · 2026-10-13 · tags: schema, tests
  A standards file must be complete on its own: `StandardsDoc.problems` checks that a numbering pattern's code list is in the same file, and the loader skips an entry whose code the registry already holds. A second edition that only adds a pattern therefore repeats the code list it names (`co.acme.documents@1.0.0.yaml` repeats `DocumentType`); loading both registers the list once.
  Evidence: `schema/fixtures/standards/co.acme.documents@1.0.0.yaml`; `tl_mod_engineering.document.pattern_problems`. Status: active
- **L-P1-I2-3** · 2026-10-13 · tags: ledger, database
  `cur_core_record.status` is NULL for a record that never changed state: it means the workflow's first state. The generated views pass `status` through as it is, so every query writes `COALESCE(status, 'Draft')` and every row type reads `status or "Draft"`; a filter `status = 'Draft'` finds nothing.
  Evidence: `tl_mod_documents/registry.py` (`_document`, `list_documents`), `reports.py`. Status: active
- **L-P1-I2-4** · 2026-10-13 · tags: security, architecture
  When a module closes a generic command for its record types (ADR-0010 addendum), its own handlers still have to call the core handler of that command (the workflow transition, a link). Give the core handler a keyword-only Python argument that skips only the allow-list (`handle_transition_workflow(..., by_module=True)`), never a field of the command: a field would be settable by an HTTP client. The guards still run.
  Evidence: `tl_core/services/workflow.py`; `tests/test_generic_commands.py` pins that `TransitionWorkflow` on a Document is refused. Status: active
- **L-P1-I2-5** · 2026-10-13 · tags: ledger, tests
  A command that flags the links to a record and also adds a link to it must flag first: `SupersedeDocument` added the `supersedes` link (new document to old) and then flagged every active link to the old document, which flagged the link it had just made. Only a test that read the new link's status back found it.
  Evidence: `test_supersede_links_the_new_document_and_flags_the_old_ones_links`; `handlers/documents.py`. Status: active
- **L-P1-I2-6** · 2026-10-13 · tags: tests, process
  Extends L-P1-I1-1 and L-P0-I8A-7. Adding a second module broke pinned lists in six places: the DDL file lists of `packages/tl-schema/tests/test_ddl.py` and `test_generate.py` (68 names each; regenerate the block with a ten-line script instead of editing), `tests/webhooks/scenario.py` (`MODULE_STREAMS` needs a stream per record type), `tests/services/test_modules.py` (entry point list), the agent refusal count in `test_api_proposals.py` (28 to 47), the command count in `test_commands.py` and the admin actions of `test_auth_review.py` (`AGENT_MAY_NOT`). Run `pytest packages/tl-schema packages/tl-api/tests/test_auth_review.py packages/tl-api/tests/test_commands.py tests/contract tests/services/test_modules.py` right after the module's commands join the API.
  Evidence: the first runs of S3 and S4. Status: active
- **L-P1-I2-7** · 2026-10-13 · tags: tickets, tests
  Put the module's test world in the package (`tl_mod_documents.testing.DocumentsWorld`, `forge`) from the first test, not in the tests directory: the CLI, API and TUI tests of other packages build documents, revisions and files with the module's own commands through it, and a world under `tests/` cannot be imported from them. In a provided test pass model instances (`ReviewerRequest(...)`, `Recipient(...)`) where a command field is a list of models; a dict literal passes pytest and fails pyright (L-P1-I1-4).
  Evidence: `packages/tl-modules/documents/src/tl_mod_documents/testing.py`; `packages/tl-cli/tests/doccli_support.py`. Status: active
- **L-P1-I2-8** · 2026-10-13 · tags: security, architecture
  An allow-list of generic commands per record type is not enough when the right answer depends on the record's state or on who made it: a revision that is issued must not take a PDF, a transmittal that was sent takes no more links, a link written by a module's rule is not the person's to retract. Give `ModuleSpec` a guard per `(type, command)` (`generic_guards`) called from the same `tl_core` places as the allow-list, including the upload path (pass the file slot), and resolve the type at the end a link starts at for the link-life commands. A command added to `GENERIC_COMMANDS` later (six link commands were missing) is closed for every module until its spec lists it, so check the list whenever a core service gains a command.
  Evidence: ADR-0010 second addendum; `tests/services/test_module_guards.py`, `packages/tl-modules/documents/tests/test_generic_commands.py`, `test_link_rules.py`. Status: active
- **L-P1-I2-9** · 2026-10-13 · tags: tests, process
  A date a command takes from the caller is checked against the server date (`resolve_date`): never in the future, an earlier one needs a reason that the event keeps. A test that hard-codes "tomorrow" passes on the day it is written and then fails for every later run of the same date, and one that hard-codes a past date needs the reason: use a past date with `date_reason`, or leave the date out. A typed number and a typed actor are checked the same way (a transmittal number fits the project pattern; a reviewer is an account), so the module test world has `people(...)` and the numbers are `P123-TRN-0001`, not `TRN-0001`.
  Evidence: the fixes to `test_transmittal_commands.py`, `test_review_commands.py` and `test_reports.py` after the security review. Status: active
- **L-P1-I2-10** · 2026-10-13 · tags: security, tickets
  When a review finds that a stub-plus-provided-test ticket's reference was too permissive (here: any actor could record any reviewer's answer; any date was accepted), the fix lands as a supervisor commit after the merge, together with the tests, and the ticket's provided tests are changed in that same commit. Say so in the report: the ticket passed review against the rules it was given, and the rules changed afterwards.
  Evidence: the post-merge adaptation commits of T08a, T08b and T09a. Status: active
- **L-P1-I2-11** · 2026-10-13 · tags: security, tests
  A field of a command that earns special treatment later (`link_source="rule"`: a link only its module may retract) must not be settable by the client that sends the command, and a test must not create the special state through the public command: `test_module_guards.py` built its rule link with a plain `AddLink`, which hid that any user could make a link nobody could retract. Give the trusted path a Python-only keyword (`by_module`), make the test use it, and add a test that the public path refuses. Likewise a key part a caller types (a document number) must be checked for the characters the module uses to build its own keys (`@`, `/`), not only the generic `CreateRecord`.
  Evidence: ADR-0010 second addendum items 3 and 4; `test_a_person_cannot_claim_a_system_link_source`, `test_a_document_number_that_squats_a_module_key_is_a_422`. Status: active
- **L-P1-I2-12** · 2026-10-13 · tags: security, process
  Three rounds of review on one module found, each time, a rule that held on one entry point and not on the next (HTTP command, upload, completion after issue, first versus replaced signed copy). When a rule has a command and an exception (write-once, then admin replaces), write the rule once as the state it protects and list every command that can change that state, in the ADR and as a test per command. `RegisterSignedRendition` exists because the first signed copy was a path the rule did not name.
  Evidence: ADR-0011; `test_the_signed_copy_is_registered_and_replaced_by_admin_commands_only`. Status: active
- **L-P1-I2-13** · 2026-10-13 · tags: security, api
  Reserve the one character that makes a collision possible, not every character that looks structural. Every key a module builds holds `@`, so refusing `@` in typed keys is enough; also refusing `/` rejected real tag and document numbers. A number that may hold `/` needs a `{number:path}` route (the server decodes `%2F` before it matches) and a test that reads it over HTTP.
  Evidence: ADR-0010 second addendum item 4; `test_a_document_number_with_a_slash_is_registered_and_read_over_http`, `test_a_typed_tag_number_may_hold_a_slash_but_not_an_at_sign`. Status: active
- **L-P1-I2-14** · 2026-10-13 · tags: cli, security
  A CLI command that uploads and then registers must build and validate its command model before the upload (with a placeholder for the id the upload will make), and run every file-free state check first. Otherwise a bad page count or a closed document leaves an orphan file. One test per refusal shows the file count did not change.
  Evidence: `check_rendition` (closed document), `doc_rendition.py`; `test_a_page_count_the_command_refuses_is_refused_before_anything_is_uploaded`, `test_a_closed_document_takes_no_rendition_and_nothing_is_uploaded`. Status: active
- **L-P1-I2-15** · 2026-10-13 · tags: tickets, process
  Wave 1 of the TUI, simulator and import tickets was clean at one attempt in three of four, and the open points were all in ticket text, not code. Check three things when a supervisor writes a ticket from a reference: a STEPS sentence with a list followed by a modifier ("equals state, equals type and contains the needle, compared in lower case") says which item the modifier applies to; a path in *Context* exists (the engineering mapping is `imports/mapping.py`, not `import_/mapping.py`); a pasted excerpt keeps its line breaks (one paste read `import annotationsfrom dataclasses`). Say "matched with `pytest.raises(match=...)`" instead of "compared exactly" when that is what the test does.
  Evidence: the T13b and T12b reports; fixes in `docs/tickets/P1-I2/T12b-mapping.md`. Status: active
- **L-P1-I2-16** · 2026-10-13 · tags: import, decisions
  A legacy export often ends every line with commas, so its header has several blank cells. Blank header names are unnamed columns that nobody can map: ignore them, and still refuse a named column that appears twice. A reviewer who asks for the literal STEPS rule and a supervisor who keeps the practical one both need the decision written down and pinned by a test, not left as an open question.
  Evidence: `read_rows` in `imports/mapping.py`; `test_imports_mapping_headers.py`. Status: active
- **L-P1-I2-17** · 2026-10-13 · tags: security, postgres, core
  A NUL (`\x00`) in any text sent to Postgres raises a driver error that carries the SQL statement and its values, and on SQLite it is stored without complaint, so a SQLite-only test never sees it. Refuse it where input enters: the core `Command` base class rejects a NUL in any string, nested or not, as a validation error (`contains_nul`), and a file reader treats any other control character as a problem of its row so a preview shows it and `--skip-invalid` can leave it out. When a hardening applies to every command, put it on the base class and test it on both adapters instead of fixing one command at a time (the first probe found `RegisterDocument` crashing on number, title, description and originator alike).
  Evidence: a0d5a83; `tests/services/test_command_text.py`, `test_imports_limits.py`, `test_cli_tag_import.py`. Status: active
- **L-P1-I2-18** · 2026-10-13 · tags: tests, process
  A new `ServiceError` subclass needs a row in `tl_api/errors.py`, even when no route can raise it yet: `test_every_service_error_has_its_own_row` finds every subclass that is imported anywhere in the process. Running the suite per package missed it (the package run never imported `tl_mod_documents.imports.apply`); only the whole `just test` run failed. Run the whole suite once after the last ticket merges, before the final gates, and not only the four package shards.
  Evidence: `ImportRefusedError` in `tl_api/errors.py` (`import_refused`, 422); the failing run of `just test` on a814cd7. Status: active
- **L-P0-TOUR-1** · 2026-10-13 · tags: tooling, tests
  To freeze time and ids for a deterministic run, replace the `datetime` and `ULID` names inside `tl_core.util` (and `datetime` in `tl_core.webhooks.base`, `tl_lake.sync`, `tl_lake.query`), not the `utcnow` and `new_ulid` functions: the ledger adapters and the sealer bind `utcnow` as a default argument (`clock=utcnow`), so a rebound module attribute never reaches them.
  Evidence: `freeze()` in `dev/tour/tourkit.py`; two runs of `dev/tour/phase0.py` and `phase1.py` write identical SVG bytes. Status: active
- **L-P0-TOUR-2** · 2026-10-13 · tags: tooling, tests
  Five things made a re-run differ and had to be pinned or masked: a random loopback port inside a `Webhook.SubscriptionCreated` event (it changes every later digest, so the receiver uses a fixed port), SQL with a tied `ORDER BY ... LIMIT` (add a second sort key), elapsed times in the `tl restore` output and real times in the `lake_query` audit log line (mask the first, disable warning logs for the second), and the order in which a loopback receiver sees two deliveries sent in parallel (sort them by `tlseq`). Secrets (passwords, tokens, signing keys) never reach an event, so random salts and tokens did not matter; the archive signing key was derived from a public phrase.
  Evidence: `dev/tour/tourkit.py` (`clean`, `fixed_archive_key`), `dev/tour/phase0.py` (`RECEIVER_PORT`). Status: active
- **L-P0-TOUR-3** · 2026-10-13 · tags: tui, tests
  In a Textual pilot script `app.query(...)` does not see the widgets of a modal screen: use `app.screen.query(...)` (a modal is `app.screen`, and `query` finds descendants only, so test the screen's own text for its title). In the TUI's grid, Enter in the filter bar moves focus to the grid and leaves the bar open: press `/` and then Esc to close it, because a second Enter on the grid opens a record.
  Evidence: `tui_tour` in `dev/tour/phase0.py`. Status: active

- **L-P1-I2b-1** · 2026-10-13 · tags: security, api
  A privilege that a list opens must fail closed when the list is empty or misspelled: the `control.*` actions are an admin's unless `RoleAuthorizer(controller_actions=...)` names them, and the API builds that set from its typed command table (`tl_api.commands.controller_actions()`), so a new `controller` command is open to the role from its declaration while a typo or a hand-written action name opens nothing. Tests pin the ten actions, an unlisted `control.*` name, and that listing an `admin.*` name opens nothing. Keep the default set empty (`RoleAuthorizer()` is what tests and the MCP server build).
  Evidence: `tests/auth/test_document_controller.py`, `packages/tl-api/tests/test_commands.py::test_the_controller_actions_are_exactly_the_commands_marked_controller`. Status: active
- **L-P1-I2b-2** · 2026-10-13 · tags: tests, process
  The tl-cli refusal tests of P1-I2 only refuse on SQLite: the autouse Postgres fixture signs an admin in for every command, so `admin_session()` returns False and the "user is refused" branch never runs there. A new gate test that needs several people at once sets `AUTO_SIGN_IN = False` in its module, makes the accounts through the core, and signs each in to a session file of its own (`test_cli_controller_gates.py`); then it runs on both adapters. Also: a refusal text is pinned in tests and in `dev/demos/*.sh` (`expect "needs the admin role"`), so before changing a message `git grep` its old words in every `tests/` directory and in `dev/demos` (the module's own tests caught three, which a run of the packages I had touched would have missed: only the full `just test` found them, again L-P1-I0A-19).
  Evidence: `packages/tl-cli/tests/conftest.py`, `packages/tl-cli/tests/test_cli_controller_gates.py`, `dev/demos/P1-I2.sh`, `packages/tl-modules/documents/tests/test_review_commands.py`. Status: active
- **L-P1-I2b-3** · 2026-10-13 · tags: tui, tests
  A hint line in a TUI modal is one row high, so a hint string wider than the screen is cut without a warning (81 characters at 80 columns lost `Esc close`). Put a new key on the second hint line and assert its length. A snapshot run rewrites the tracked `snapshot_report.html` in the repository root: `git checkout snapshot_report.html` before every commit. `Ctrl+I` is Tab in a terminal: use another key (`Ctrl+T` in the composer).
  Evidence: `AdminScreen.KEY_HINTS_MORE`, `test_the_hints_name_the_controller_key`. Status: active
- **L-P1-I2b-4** · 2026-10-13 · tags: process, sim
  The name `document_controller` was already taken: Phase 0's simulated person `user:sim-document_controller` (`tl_sim.scenario.ROLE_NAMES`, a `core.Record` actor) is not the Phase 1 role and holds the `user` role like every simulated person (dev tokens never carry more, ADR-0009 section 9). The simulator does not issue; giving it the role needs an owner decision on dev-token roles, so ADR-0013 records it as a follow-up instead of a quiet change.
  Evidence: ADR-0013 consequences, `packages/tl-sim/src/tl_sim/scenario.py`. Status: active
- **L-P1-I2b-5** · 2026-10-13 · tags: security, database
  The account projection stores a role list sorted alphabetically (`projector._roles_json`), so the order that `accounts` writes in the event must be the same or a test that compares lists exactly fails on a rebuilt ledger: `ROLES` is `("admin", "document_controller", "user")`, not the order a person would say. Add a role by extending `ROLES` once (types.py), never a second tuple.
  Evidence: `tests/auth/test_document_controller.py::test_the_role_is_granted_and_taken_back_by_events_and_survives_a_rebuild`. Status: active
- **L-P1-I2b-6** · 2026-10-13 · tags: security, tui
  A role toggle that computes the new list from a row read earlier overwrites a concurrent change (the list is replaced as a whole). `accounts.set_roles` takes `expected_roles` (the list the caller read) and refuses a mismatch with 409 `account_state`; the API body, the clients and the accounts screen pass it, and `tl admin user roles --add/--remove` reads the roles inside the write unit of work instead. A client that gates a command by role must also compare `cmd.actor` with the actor it vetted, or the gate checks one person and the event names another.
  Evidence: `tests/auth/test_document_controller.py`, `packages/tl-tui/tests/test_embedded_controller_gate.py`. Status: active

- **L-P1-I3-1** · 2026-10-17 · tags: schema, tests
  A pset added to the shared sample company package (`co.acme.engineering`) changes every test that lists psets: ten tests in `tl-schema` and `tl-core` pinned `["safety_data", "valve_data"]` style lists, and a pset whose `applies_to` names a module type (`engineering.Tag`) also appears in `psets_for(TAG)` and in the tag form. Run `pytest packages/tl-schema packages/tl-core` right after touching a fixture package, and let a script rewrite the pinned DDL name lists (`test_generate.py`, `test_ddl.py`) instead of editing them.
  Evidence: the first run of P1-I3A-S2; commit 4016789. Status: active
- **L-P1-I3-2** · 2026-10-17 · tags: schema, tooling
  Two LinkML traps in a module class: a slot named `version` clashes with the envelope column in the generated flat view (`DdlError: column 'version' clashes with the envelope`; the schema version slot is `semver`), and a description that holds a quoted JSON example needs its own YAML quoting (L-P1-I1-2 again).
  Evidence: `schema/modules/documents/document_schema.yaml`, `processing_job.yaml`. Status: active
- **L-P1-I3-3** · 2026-10-17 · tags: tickets, tooling
  L-P1-I1-9 for a pyright-strict package (`tl-core`): a stub also fails pyright on unused imports and unused private helpers, so its header needs `# pyright: reportUnusedImport=false, reportUnusedFunction=false` next to the `ruff: noqa: F401` line, and the ticket tells the implementer to remove both. Before dispatch copy the provided test into the package and run ruff and pyright on the stub state, then the test against the reference.
  Evidence: `registry.py` stub of P1-I3-T03 (3 pyright errors before the header was added). Status: active
- **L-P1-I3-4** · 2026-10-17 · tags: env, process
  A container restart kills background test runs and watchers but leaves the worktree and commits; `/tmp/*.log` names are shared with the other workstream, so put logs in the scratchpad directory and re-run `uv sync --all-packages` and Postgres checks first thing after a restart.
  Evidence: restart at about 02:35 UTC on 2026-10-17 during P1-I3 workstream A. Status: active

### L-P1-I3-5 (process) A ticket whose code other pieces cannot be tested without is built, not stubbed
Validation and diff (T04, T06) were Haiku tickets in the plan, but the `extract` and `validate` job kinds, the publication preview and every pipeline test call them. A stub plus held tests would have held back all of those, so they were built and tested in the supervisor piece that needed them and the tickets were closed as "built by supervisor". Decide at planning time: a ticket is Haiku work only if nothing else in the increment has to run before it merges (check the Depends column from the other side). Evidence: `docs/tickets/P1-I3/README.md` rows T04, T06, T08a, T08b.

### L-P1-I3-6 (tests) A screen test that mounts its sibling screens breaks parallel tickets
The first draft of the T07 tests opened the job monitor and the publish preview from the derived-documents screen, so each ticket's test needed the other two to be finished. Tests of a screen ticket mount their own screen directly (`app.push_screen(Screen(...), callback)`) and replace the screens it opens with a probe `ModalScreen` through `monkeypatch.setattr(module, "Name", Probe)`. Evidence: `docs/tickets/P1-I3/provided/t07a-test_job_monitor.py.txt`, `t07b-test_derived_documents.py.txt`.

### L-P1-I3-7 (tests) A CLI test that is about having no session needs AUTO_SIGN_IN = False
`packages/tl-cli/tests/conftest.py` signs an admin in before every command on Postgres. A test of "nobody is signed in" sets `AUTO_SIGN_IN = False` at module level and accepts either `needs the admin role` or `not signed in` (Postgres refuses earlier than SQLite). Evidence: `packages/tl-cli/tests/test_cli_proposal_access.py`.

### L-P1-I3-8 (tooling) pkill -f kills your own shell
`pkill -f "pytest packages/tl-api"` matches the command line of the Bash call that contains the pattern and ends it with exit 144. Kill by PID from `ps`, or avoid the pattern appearing in the same command. Evidence: this session.

### L-P1-I3-9 (tests) The full unit suite of the packages takes about 15 minutes; run it in the background and do not edit sources meanwhile
`pytest packages/tl-tui packages/tl-api packages/tl-modules` took 878 s on a shared container; editing files during a run produced failures that were not real (renamed problem codes, changed fixtures). Start it with output to a log file, work on documents only, then read the log. Evidence: /tmp logs of S13.
- **L-P1-I3B-1** · 2026-10-17 · tags: tooling, security
  openpyxl makes up what a workbook does not say: with no `docProps/core.xml` it answers `workbook.properties` with creator `openpyxl` and the time of the call, and `save()` stamps the time of the save into `modified`. Ask for properties only when the part is in the archive, and patch `modified` (and store, do not deflate, the entries with a fixed time) to make a fixture file byte-for-byte reproducible. In `read_only` mode it fills a gap between rows with empty rows but does not pad after the last row, and `iter_rows(max_col=n)` cuts and pads every record, so a sheet formatted down to row one million is bounded by a limit on blank rows in a row, not by the sheet's own dimension.
  Evidence: `packages/tl-extract/src/tl_extract/xlsxgrid.py`, `tests/golden/make_golden.py`; `test_a_workbook_without_properties_has_none_and_nothing_is_invented`. Status: active
- **L-P1-I3B-2** · 2026-10-17 · tags: security, tests
  A reader of an archive format checks what the archive declares before it parses anything: Python's `zipfile` returns at most the declared size of a part, so the declared sizes are real limits, and a ratio check is useless (deflate cannot exceed about 1000 to 1). Scan every XML part for `<!DOCTYPE` and `<!ENTITY` in chunks that overlap by the marker length, and refuse a part in UTF-16 (a byte search would miss it). To test an encrypted entry, patch the general-purpose flag bit in the central directory bytes: `ZipFile.writestr` resets `ZipInfo.flag_bits`.
  Evidence: `check_archive`, `scan_xml_parts`; `test_an_encrypted_part_is_refused`, `test_a_declaration_that_straddles_a_read_chunk_is_still_found`. Status: active
- **L-P1-I3B-3** · 2026-10-17 · tags: tooling, tests
  A mutation pass over the provided tests of the four readers (remove one guard at a time, run the test file) found 19 survivors; 12 were real gaps (a loop bound, a truncated chunk, the read-only open and the close of the workbook, a blank-run counter never reset, a log handler, a DHT table taken for a frame header, a text length cap) and got a test or lost a redundant line, the rest were safety nets that two guards cover. Do this before generating a ticket from a provided test: an implementer cannot be held to a test that does not fail without the guard. A pydantic model with `ConfigDict(strict=True)` is needed for options, or `"2"` is accepted for an int field.
  Evidence: `docs/tickets/P1-I3/provided/*`; `tests/test_reading.py::test_a_bad_option_is_refused_and_the_value_is_not_echoed`. Status: active
- **L-P1-I3B-4** · 2026-10-17 · tags: tooling
  pypdf reports every repair through `logging`, and Python's last-resort handler prints those warnings to standard error when no handler exists: a library adds `logging.getLogger("pypdf").addHandler(logging.NullHandler())`. With `strict=False` pypdf still raises for a missing `%%EOF`; `reader.is_encrypted` is readable without a password, and touching `reader.pages` or `reader.metadata` of an encrypted file raises, so test the flag first. A page-tree `/Count` that lies does not reach `len(reader.pages)`.
  Evidence: `packages/tl-extract/src/tl_extract/pdfinfo.py`; `test_pypdfs_log_records_do_not_reach_pythons_last_resort_handler`. Status: active
- **L-P1-I3B-5** · 2026-10-17 · tags: process, tickets
  A script that rewrites a file in place must compute the new text before it opens the file for writing: `open(path, "w").write(transform(...))` truncates the file first, and an assertion inside `transform` left an empty module. Restore from git and write `result = transform(...)` on its own line. Also keep the exact messages that tests compare as module constants in the stub, so no STEPS line has to wrap a quoted message.
  Evidence: the first run of the stub generator for P1-I3B-S4; commit 36447c0 (message constants). Status: active
- **L-P1-I3B-6** · 2026-10-17 · tags: process, tickets
  Four stub-plus-provided-test tickets generated from the stubs all passed review at the first attempt with no finding: the mutation pass on the provided tests (L-P1-I3B-3), exact messages as constants, and STEPS with the bounds named were what the implementers' reports credited. Two small defects came back as notes: a pasted excerpt of a module (`reading.py`) was abridged without saying so, and the report template was not in Context. Say "abridged" over an excerpt, and list `docs/templates/haiku-report.md` in Context.
  Evidence: `docs/reports/P1-I3/P1-I3-T09a.md` to `T11.md` (Learnings). Status: active
- **L-P1-I3B-7** · 2026-10-17 · tags: security, tooling
  A library's read-only or lazy mode is not a bound. openpyxl `read_only` still builds a whole row (a cell at column XFD makes 16 384 cells) and the whole shared-strings table before a cap can look at it (99 KB of XLSX: 99 s, 7.7 GB), and pypdf `len(reader.pages)` decodes object streams (1.2 MB of PDF: 113 s, 1.3 GB). The fixes that held: stream the XML with `iterparse` and count elements, depth, strings, cells and characters as they come, removing each row from its parent; for pypdf, read `/Root/Pages/Count` only, read strict, lower its decompression limits per call with `pypdf.apply_configuration`, and scan the bytes first with linear C-speed passes (object streams, `/Length` past the end of the file, strings over a megabyte). A bound is proved by a crafted file of a few hundred kilobytes that finishes in well under a second, or by a limit patched down to a few units; never by a test that spends seconds. Measured with the fixes: the largest legal CSV (41 MB, 1 million cells) 2.7 s and 124 MB over the interpreter; the largest legal XLSX (20 000 x 50 cells) 8 s and 34 MB over.
  Evidence: `tests/test_xlsx_hostile.py`, `tests/test_pdf_hostile.py`; security review of b1c4e60 (H1, H2, H3). Status: active
- **L-P1-I3B-8** · 2026-10-17 · tags: security, tooling
  Three bounds that looked right were not. (1) A regular expression with a group or alternation under a repeat (`(?:[^()\\]|\\.){1048576,}`) keeps state per character: a 47 MB string reached 5.3 GB; a single character class under a repeat does not. For a library that reads through a file object, bound it by counting the operations on the object (a `BytesIO` subclass counting `read`, `readline` and `seek`) and raise a `BaseException` subclass, which the library's own `except Exception` cannot swallow. (2) `iterparse` keeps every element attached to its parent unless it is cleared and removed at its end event: 4.9 million `<x a="1"/>` after the data took 1.7 GB from a 97 KB file. Do it once in the event generator, and count attributes as well as elements. (3) A handler that builds its result inside `except MemoryError` runs while the traceback still holds the frames that ran out of memory, so the result itself raises: set a flag, leave the except block, then build.
  Evidence: `_BudgetStream` in `pdfinfo.py`, `events()` in `xlsxxml.py`, `run_guarded` in `reading.py`; re-review of d1e2b7a (N1, N2, N3). Status: active

### L-P1-I3-10 (security) Put a rule that every body must obey in the body's model, and prove it by walking the published API
`refuse_reserved` was applied in the generic `/commands/*` endpoint and forgotten on the two upload routes, which build their commands from the same `request_model` bodies. A check in each route is a check a new route can forget. It now sits in the model validator `request_model` adds (mode `before`, so it runs on a body that is otherwise incomplete), and a test walks `app.openapi()` and posts a reserved value to every route whose body is one of those models, and fails if any route with a `source` field is not one. Evidence: `packages/tl-api/tests/test_api_reserved_identifiers.py`; security re-review of b5f5d41.

### L-P1-I3-11 (tests) A test that loops over what it found must first assert that it found something
The first version of the walking test read `app.routes`, which in this FastAPI holds `_IncludedRouter` objects and no route paths, found nothing, and passed. Assert the count (and a few known members) of what a walk finds before the loop, and run a new walker once against code that lacks the guard. Evidence: `test_the_walk_finds_the_command_routes_and_the_upload_routes`.

### L-P1-I3-12 (process) Run `ruff check` on a provided test and run the ticket's Depends list against its fixture before dispatch
T14d came back blocked for two reasons that were both in the ticket: the provided test imported two names it never used (ruff F401 fails `just check` and the implementer may not edit the copy), and four of its cases called a command (`tl derive show`) that another ticket in the same batch was writing, which the Depends line did not name. Before dispatch: copy each `.py.txt` into `tests/` and run `ruff check` and `ruff format --check` on it, and read every command its fixture and cases call against the Depends line. Evidence: `docs/reports/P1-I3/P1-I3-T14d.md`; the T14b report said the same about T14a.

### L-P1-I3-13 (tests) Run the demo through every entry point that runs the pipeline; a process must configure what a command needs
`tl proposal accept` of an agent's publication proposal failed in the demo with "no file service for derived data": only `tl derive` configured the derivation module's file service, and the accept command runs the publication in the CLI process. No unit test had run that path with the module unconfigured. A test for such a path calls `store.configure(None)` first, so only the command's own set-up can make it pass (`test_cli_proposal_publish.py`). The demo also found that two fixtures that share tag numbers cannot both be published after one is compensated (a compensated key is never reused): give demo data distinct keys.

- **L-P1-I5-1** · 2026-10-17 · tags: database, tests
  Postgres cannot infer the type of a bare parameter in `CASE WHEN :p IS NOT NULL AND :p > col ...` (`could not determine data type of parameter $1`); SQLite accepts it, so a SQLite-only run passes. Choose the value in Python (read the row, compare, write) or `CAST(:p AS text)`. A slot named `to_json` with `tl:json` gets the column `to_json_json`: name JSON slots without the suffix (`to_parties` gives `to_parties_json`).
  Evidence: `projectors/thread.py` (first version failed `test_a_thread_counts_its_items_and_keeps_the_newest_date[postgres]`); `schema/modules/correspondence/correspondence.yaml`. Status: active
- **L-P1-I5-2** · 2026-10-18 · tags: security, tests
  The viewer defaults to the lowest clearance (ADR-0016), so a test helper that reads a record *after* the test raised its class reads nothing and fails with "not found". Run such a read inside `use_viewer(<a controller>)`; a test that sets a class and then asserts on the record owns the viewer for the whole body. The same default makes every code path that forgets to set a viewer fail closed, which is the point: do not "fix" a red test by widening the default. Evidence: `packages/tl-modules/documents/tests/test_document_commands.py::test_confidentiality_changes_only_through_its_own_command`.
  Status: active
- **L-P1-I5-3** · 2026-10-18 · tags: security, tests
  A child record (a thread, a clock, a revision) is readable only when its parent row is, and a child whose parent row cannot be found is hidden from everyone. A scenario that appends module events raw must therefore point each child at the stream it made for the parent (`PARENTS` in `tests/webhooks/scenario.py`), and must not use a sample payload that changes the class of a record the subscription owner reads. Evidence: the webhook catalog contract failed with the 40 events of the child types until the scenario was fixed.
  Status: active
- **L-P1-I5-4** · 2026-10-18 · tags: process, tests
  Give a ticket's provided test only the helpers its own handlers and the merged ones provide: `CorrWorld.forge_item`, `forge_party` and `forge_clause` write a record with raw events, so a test of one command does not depend on another ticket's command (the `Depends` line then stays short and the batch runs in two waves, not six). The reference suite is validated twice: once with the thread wiring left out (what the first wave has) and once with it.
  Evidence: `packages/tl-modules/correspondence/src/tl_mod_correspondence/testing.py`; `docs/tickets/P1-I5/`. Status: active
- **L-P1-I5-5** · 2026-10-18 · tags: process, tests
  The base of a dispatch must be checked with `just check` on the exact commit the DISPATCH names, with the exit code captured (never judged through `| tail`): the base was called green at one commit and sent at a later one, and four tickets came back blocked by 149 pyright errors that were not theirs. When a protocol grows (`ClientInterface` gained seven methods), every class that implements it is changed in the same commit: `grep -rn "ClientInterface\|class .*Support" packages/tl-tui/tests` lists the fakes, and a test that assigns the fake to the protocol type (`as_protocol: ClientInterface = fake`) makes pyright say so.
  Evidence: `packages/tl-tui/tests/fakes_correspondence.py`, `test_fakes_correspondence.py`; the reports of T07a, T07b1, T07c, T07f. Status: active
- **L-P1-I5-6** · 2026-10-18 · tags: process, tests
  A mutation run proves nothing until its baseline has passed on the unmutated code in a tree whose dependencies are installed, and a kill is a pytest exit code 1 with failures (any other non-zero code is invalid, not a kill). Check each mutation spec before reading its result: a spec whose old and new text are equal, or whose first match is in a docstring, survives for no reason. A survivor is one of three things: a missing test (write it), a redundant check (the same error is raised by a call the line also makes: remove the line or say so in the report), or a bad spec. The first run of this increment (about 120 mutants, 0 survivors) was vacuous because the tree had no installed packages; the repeated run found 24 survivors, 5 of which were redundant code and 3 bad specs. Harness: bash-free Python driver, `uv sync --all-packages` first.
  Evidence: `docs/tickets/P1-I5/provided/` (tests extended), `packages/tl-modules/correspondence/tests/test_hardening.py`. Status: active
- **L-P1-I5-7** · 2026-10-19 · tags: security, tests
  A bound of a parser of untrusted input needs a test that only that bound can fail. Five EML bounds survived mutation because a stricter bound refused the same fixture first: the all-parts header total (the per-part limit fired), the text-size check made before base64 decoding (the decoded-size check fired), the decoded-size check (the pre-decode check fired), and the subject limit. Each now has its own fixture: 40 headers in each of three parts; base64 padded with spaces (decodes to three bytes, so only the text size can refuse it); an unencoded 7bit attachment; a 600-character subject under a 2000-character header limit. When two limits guard one input, tighten one in the test with `EmlLimits(...)` and leave the other loose.
  Evidence: the last tests of `packages/tl-modules/correspondence/tests/test_eml.py`; the `eml` mutation spec went from 5 survivors to 0.
  Status: active
- **L-P1-I5-8** · 2026-10-19 · tags: process, tests
  A mutation check of a read model must damage the stored row, not only the events: `views.clock_view` recomputes the dates from the events and falls back to the stored row, and the tests passed with either, because the two agree on an undamaged ledger. `UPDATE` the projected column to a wrong value and assert the view still shows the replayed one. The same run showed that a register filter applied to the second source of lines (the transmittals) needs a test with a source line in the ledger: the item-only tests cannot see it.
  Evidence: `packages/tl-modules/correspondence/tests/test_views_extra.py`. Status: active
- **L-P1-I5-9** · 2026-10-19 · tags: process, security
  Inheriting a class from what an item answers is for NEW items only. Run for an existing item (`AssignThread`, a plain user command), the same rule let a person named on a privileged thread pull anyone's item into it, so its author and the admins lost it. Any path that re-threads or re-answers an existing item must refuse a higher class unless the actor is a controller, and a controller's move must record a class event (`guard_move`).
  Evidence: `packages/tl-modules/correspondence/tests/test_threads.py` (the four tests after "moving an existing item"), ADR-0016. Status: active
- **L-P1-I5-10** · 2026-10-19 · tags: process, tests
  A module that adds commands, routes or screens breaks tests of other packages that pin the whole set (`test_api_document_controller.py` pinned the controller actions, `test_confidentiality_walk.py` the path parameters of every GET route), and per-file runs of "the files I touched" do not find them. Run the whole `just test` once before the merge, not only at the end. Two workstreams also took the same TUI key (F12); check `tl_tui/keymap.py` on trunk before binding one (the correspondence screen is on F5).
  Evidence: the merge commit of p1/i5 and its fix commit. Status: active
### L-P1-I4-1 (security) In a pattern for numbers write `[0-9]`, not `\d`
`\d` matches the digits of every script (Arabic-Indic, Devanagari) and `float()` and `int()` accept them, so a cost file with `١٢٣` passed a number check that was meant to be plain ASCII. Use `[0-9]` and `fullmatch`. A mutation of the cost CSV reader found it; `test_cost_csv_reader.py` pins it. Evidence: `tl_mod_cost/imports/reader.py` (`_NUMBER`).

### L-P1-I4-2 (security) `str.isdigit()` is not "ASCII digits", and `int()` refuses more than 4300 digits
A text a person typed (a link's pin) went through `int(pin) if pin.isdigit()`: `"²"` is `isdigit()` and `int("²")` raises, and a 5000-digit text raises too. Check `isascii()` and a length before `int()`. Evidence: `tl_mod_schedule/resolver.py` (`_pin_as_of`), `test_a_pin_that_is_not_a_snapshot_number_floats`.

### L-P1-I4-3 (security) A tree limit in a file reader needs the depth of every node, not a walk from the roots
The XER WBS depth limit held for files that list parents before children and was not enforced for other orders: the first version walked up from each node and never remembered. `test_largest.py` (60 000 nodes in a chain) found it; the reader keeps a depth map and a path-length cap and refuses `wbs_too_deep`. Test a limit with the worst shape, in the worst order. Evidence: `tl_xer/typed.py` (`_wbs_rows`).

### L-P1-I4-4 (ledger) The link vocabulary is the thirteen of brief 7.1; a module names its target by the target's type
A module cannot add a relation (`scheduled_by`, `costed_to` are unknown), so links to cost codes and activities use `references` and the type of the record they point at says what they mean. Do not filter links by relation in SQL; join the target table. Evidence: ADR-0015 section 5, `tl_mod_schedule/names.py` (`ACTIVITY_RELATION`).

### L-P1-I4-5 (tests) Two traps of link and lock tests; and test data must be in the past
The same record cannot link twice to one target (`DuplicateLinkError`): use two records or two activities. A write inside an open read unit of work times out on SQLite (the writer lock): evaluate arguments that write before the `with open_uow(...)`, or close the read transaction first. The clock of the build environment is ahead of the dates a test author imagines: a test that writes a future period is refused as such, so cost tests use 2026-05 to 2026-08. Evidence: `test_resolver.py`, `tl_mod_schedule/testing.py`, `tl_mod_cost/tests/test_module.py`.

### L-P1-I4-6 (process) Mutate the reference before it becomes a ticket; a survivor is a missing test or a redundant guard
Before a reference file was stubbed for a Haiku ticket, one guard at a time was removed (`mutate_generic.py` style: replace a line, run the file's tests). The cost reader, the look-ahead and the resolver had 0, 0 and 8 survivors at first; the resolver's were a missing trailing-text test, a missing non-ASCII pin test, a person-flagged link on an absent activity, a retracted link, a `broken` link with the module's own words, a second schedule, and three guards that nothing can reach (kept). Without the tests the Haiku implementer could pass a wrong boundary. Evidence: `docs/tickets/P1-I4/` provided tests.

### L-P1-I4-7 (ledger) Large typed rows of a snapshot are operational tables, with a hash in the ledger
20 000 activities of up to 100 columns would be events of megabytes. The snapshot's typed rows (`sched_*`) are written by the build job in its own transaction, never cleared by a projection rebuild, and checked against the SHA-256 of the canonical rows recorded in `ScheduleSnapshot.Built`; `tl xer reconcile` rewrites them from the source file after a restore. Use the same shape for any derived table a job writes that is bigger than an event should be (ADR-0014, ADR-0015). Evidence: `tl_mod_schedule/projectors/tables.py`, `build.py`.

### L-P1-I4-8 (security) Write invisible characters in a source pattern as escapes
A pattern that refuses control and text-direction characters held the characters themselves; nobody can see in a diff or a file read whether one was added or dropped (the T02a implementer and reviewer both had to prove it with `git diff`). Write them as `\x..` and `\u....` escapes (`_FORBIDDEN` in `tl_mod_cost/imports/reader.py`, same value, compared at the change) and keep a test that feeds each class. Evidence: `docs/reports/P1-I4/P1-I4-T02a.md`.

### L-P1-I4-9 (tooling) A first `just check` in a fresh worktree takes over two minutes: give it a long timeout
All three implementers of batch 1 lost a run to the 120 s default of the shell tool: `just check` (lint, format, pyright, drift, OpenAPI and licence checks) and the Postgres run of a module suite (2.7 minutes for the resolver) need `timeout` 600000 or a background run waited for on its task output. `ruff format <file>` first, because the format check rewrites a hand-wrapped line. `pgrep -f` matches other worktrees' processes. Tickets now say so in Acceptance. Evidence: the three P1-I4 batch-1 reports.

### L-P1-I4-10 (security) `ruff format` turns `\uXXXX` in a plain string into the character itself
L-P1-I4-8 says to write invisible characters as escapes; the formatter undoes that in an ordinary string literal (it leaves `\x..` and raw-string regexes alone). In tests build the character with `chr(0x202e)`; in a pattern use a raw string (`r"[\x00-\x1f‪-‮]"`, as `tl_core/text.py` does). After a format run scan the repository for literal forbidden characters (`grep -rnP "[\x{200e}\x{200f}\x{2028}\x{2029}\x{202a}-\x{202e}\x{2066}-\x{2069}\x{feff}]"`). Evidence: `tl_core/text.py`, `tl_core/tests/test_text.py`.

### L-P1-I4-11 (performance) `executemany` on the pure-Python Postgres driver is one round trip per row
Writing the maximum typed snapshot (about 860 000 rows) with `executemany` took 535 s on Postgres and 13 s on SQLite. One bound JSON text per chunk of 20 000 rows with `INSERT ... SELECT ... FROM json_array_elements(:rows)` and casts took 25 s. Anything that writes more than a few thousand rows on Postgres uses this shape, and its time is measured on both databases and sits well inside the job's lease. Evidence: `tl_mod_schedule/typed_store.py`, ADR-0015 §4.

### L-P1-I4-12 (ledger) Work that grows with what people link belongs in a state-derived job in bounded runs
Flagging the links of a removed activity inside the publish command made the publisher's transaction as long as anyone's links were many. It is now a queued job that derives what to do from state (references out of step with the snapshot, active links of absent references, links this module flagged on present ones), does at most 500 operations a run and queues the next. A run that uses its whole budget cannot know nothing is left, so the last run flags zero and says complete; a test for the chunk sequence expects that. Because anyone signed in can link, the inputs are capped too (100 links per reference, 60 000 references per schedule). The honest consequence is a window in which a link still reads as current; the view says so (`links_being_checked`). Evidence: `tl_mod_schedule/orphans.py`, `tests/test_review_fixes.py`.

### L-P1-I4-13 (security) A per-dimension bound is not a bound on the product; bound the total and the answer
The reader limited columns, rows per table and cells, and a file of 14 one-column tables still cost 45 s and 649 MB. Add a total row bound and a weighted cell budget (a row weighs at least 16), bound the text of the typed rows by the size of the file (a code is copied into every row that links it), make the bound on the child's answer follow the file size, and re-check every figure in the parent. Evidence: `tl_xer/limits.py`, `tests/test_review_fixes.py`, `tests/test_largest.py`.

### L-P1-I4-14 (process) After a restore, write the typed rows before queueing what depends on them
`reconcile` first queued the flagging and build jobs and then wrote the typed rows; a worker could run a flagging job against missing rows. Write the rows first, queue second, and make a job refuse with an error (not flag nothing) when the rows it needs are missing. Evidence: `tl_mod_schedule/reconcile.py`, `orphans.TypedRowsMissingError`.

### L-P1-I4-15 (tui) Two Textual name traps, and a table refill raises RowHighlighted after you have placed the cursor
`self.offset` (a widget's DOM offset) and `self._id` (Textual's own) cannot be attributes or methods of a screen: the first raised `TypeError` in `__init__`, the second `'NoneType' object is not callable` in the first reload; the screens use `first` and `_current_id`. Filling a `DataTable` (`clear`, `add_row`) posts `RowHighlighted` after the fill has returned, so a handler that reloads a dependent table (a schedule's snapshots) must do nothing when the highlighted row is the one already loaded, or every reload puts the dependent cursor back on row 0. The provided test `test_moving_between_schedules_loads_their_snapshots_and_a_reload_keeps_the_place` pins it. Evidence: `tl_tui/widgets/schedule_screen.py`, `activity_screen.py`.

### L-P1-I4-16 (process) Mutating the reference of nine plain read tickets found the same five gaps in every test file
A hard-coded project in a read (the test only used `P123`), a cursor not kept across a reload, a page boundary (`>` against `>=`), one half of an `or` in a filter (the fake's titles held the codes), and a retracted or stale link that still counted. Each gap is a line a Haiku implementer could write wrong and the provided test would pass. Write the test, then mutate: with a second project, a second page size, titles that do not hold the codes, and a link in each status. A survivor that no honest test can tell (a scope condition made redundant by a core invariant) is removed from the SQL, or kept with a comment saying why. Evidence: `docs/tickets/P1-I4/provided/*`, `tl_mod_cost/reports.py`, `tl_mod_schedule/reports.py`.

### L-P1-I4-17 (process) After adding a command, a route or a tool, run the whole suite of its package: pinned lists break far from the change
Adding `propose_publish_schedule_snapshot` left `MCP_ACTIONS` (the closed action list), the pinned tool sets of `test_mcp_server.py` and `test_mcp_write_tools.py` out of step, and adding the `tl xer` controller commands left the count in `test_cli_controller_gates.py` at 11. None showed until the package suite ran, about 20 minutes after S10 and S8 were committed. The failure for an agent was real: the tool was closed (no action in the list). Run the package suite (`uv run pytest packages/tl-mcp`) before the commit that adds the entry point. Evidence: commit 2b10c42.

### L-P1-I4-18 (process) An act the simulated people may not do is setup, and the check that nobody else wrote needs to be told so
Simulated people hold the `user` role only (ADR-0009 section 9), so defining and publishing a schedule (a controller's) and building a snapshot (a worker's) cannot be simulated, yet `sim_assert` fails any event in the run's scope that a simulated actor did not write. The scenario now names them in `operators`; their events and the records they made are excused and nobody else's are. Keep the list short and exact: a name in it excuses everything that actor wrote. The file routes also stamp the source `api` and real time on `File.Uploaded` and the scanner writes `File.Processed`; those two are expected. Evidence: `tl_sim/assertions.py`, `tests/test_assertions.py`, `tests/test_schedule_updater_end_to_end.py`.

### L-P1-I4-19 (testing) A test that "the draw is spent" must use a range: an integer count takes nothing from the generator
`draw(2, rng)` returns 2 without touching `rng`, so a test of "the actor draws even when nothing follows" that used `links_per_day=2` passed whether or not the draw was made; the mutation that moved the draw after the early return survived. Use `CountRange` and compare the next value of the generator with a fresh one that made the same draw. Also: `mimetypes` guesses `application/xcap-error+xml` for `.xer`, which the `xer` slot refuses, so the simulator's client passes the type. Evidence: `tests/test_actor_schedule_updater.py`, `tl_sim/client.py`.

### L-P1-I4-20 (security) A mark the module relies on must be a value a client cannot set, and checked in two fields
The module told its own flags from a person's by the event source `svc:schedule`; the API's source pattern accepted that string, so a person could flag a link with it and have the module restore it. `svc:` is now a reserved source prefix (`tl_core.services.reserved`, with the API walk test), and the module also requires the actor of the flag event to be the service. When a module keys behaviour on a field of an event, grep every route that lets a client write that field, and test the forgery (a flag with the module's source and a person's actor stays flagged). Evidence: `tests/test_publish.py`, `test_api_reserved_identifiers.py`.

### L-P1-I4-21 (security) Names from a file that become lake tables or columns need an allow-list, a fold of case, and a failure that costs one snapshot
Two columns `A` and `a` built a Valid snapshot, and the lake (which lowercases names) then failed every later sync with a catalog error; 250 junk tables would have made 250 lake tables. The reader refuses names that repeat ignoring case; the lake makes a table of its own only for the tables P6 defines (a list, with a test that the synthetic files fit it) and puts everything else, and a table that would pass 300 columns, in one long table; and each snapshot's bronze load is a transaction of its own whose content failure is recorded and skipped (infrastructure failures still stop the pass). Evidence: `tl_lake/xer.py`, `tests/test_xer.py`, `tl_xer/reader.py`.

### L-P1-I4-22 (security) Bound memory in estimated bytes of what the reader keeps, not in cells, and try the wide-character variant
Counting cells (a row weighed its columns, at least 16) let 16 million two-character cells reach 938 MB, because a cell is a 51-byte string and a slot; the same with a euro sign in each cell reached the envelope's 1 GiB and was killed before the reader could refuse it, which reports as a crash, not a refusal. The reader now adds up an estimate per row (slot per column, a string per filled cell at 49 or 72 bytes, the characters, the row) against 420 million, which keeps the worst legal file near 583 MB and refuses both variants with a code. Measure each shape of hostile file with ASCII and with non-ASCII cells, and check the refusal comes from the reader. Evidence: `tl_xer/reader.py` `row_memory`, `tests/test_largest.py`, ADR-0015 section 2.

### L-P1-I4-23 (process) Moving dialect SQL out of a module: put the shape behind one adapter function with its own parity test
The JSON-per-chunk insert for Postgres was inside the schedule module, against AGENTS rule 5. It is `tl_adapters.bulk.bulk_insert` now, with a test on both adapters that stores every kind of value in several chunks, and a module test that fails if `dialect.name` or `json_array_elements` appears in the module again. The speed (25 s at the largest snapshot) is unchanged because the statement is the same. Evidence: `tl_adapters/bulk.py`, `tests/test_bulk.py`.

### L-P1-I4-24 (security) Build a large JSON text as bytes in batches, charge its budget in the bytes it will take, and carry the project into every shared table
A text is as wide as its widest character: one emoji made the typed JSON of a legal 49 MB file a 4-bytes-a-character string next to its bytes, and the envelope killed the child at 1 GiB (716 MB even in ASCII). The child now turns 5 000 rows at a time into bytes, hashes the pieces and joins them once; the text budget counts the UTF-8 size with escapes, so a refusal comes before the work; the worst legal file takes 591 MB whatever the characters. A table in the lake that is keyed by a code a person chooses (the schedule code) must also carry the project, or two projects meet in one mart. A bundle whose hash does not match is the store's fault and stops the pass; only the content of a verified bundle is the file's fault and filed. Evidence: `tl_xer/process.py` `typed_json_parts`, `tests/test_largest.py`, `tl_lake/xer.py`, `tests/test_xer.py`.
- **L-P1-SEC1-1** · 2026-10-17 · tags: security, tests
  A value that grants rights must not be a field of the shared command model: `TransitionWorkflow.actor_roles` was "trusted input" by comment only, and every entry point that builds a command from outside data (HTTP body, accept body, a CLI option, a TUI menu, the sim client) could fill it. Make it an argument of the handler that only the entry point's authenticated code can pass (the pattern of `by_module`), with "none" as the default. When a review finds one such hole, grep for every reader of the field and every writer of a similar one (here: `actor_roles`, the accept body `roles`, `?role=`, `--role`) before fixing only the route reported.
  Evidence: `tl_core/workflow/roles.py`, `test_api_workflow_roles.py::test_the_walk_finds_the_bodies_and_none_takes_workflow_roles`, ADR-0013 addendum. Status: active
- **L-P1-SEC1-2** · 2026-10-17 · tags: tests, process
  The tl-cli conftest signs in an admin `dev` before each command on Postgres, so a test that needs a plain user, or the absence of a role, must set `AUTO_SIGN_IN = False` and sign its own people in (see `test_cli_wf_roles.py`); an admin also holds `document_controller`, so a role test with the default session passes on Postgres and fails on SQLite for the wrong reason.
  Evidence: `packages/tl-cli/tests/test_cli_wf_roles.py` (`Cast`), `conftest.py`. Status: active

- **L-P1-I6-1** · 2026-10-20 · tags: tests, tickets
  Pyright strict does not narrow an attribute through a boolean local computed from it: after `late = waiting and data.required_by is not None and ...`, `if late:` leaves `data.required_by` as `str | None`. A STEPS line that says "when `late`" needs the words "and `data.required_by is not None`" so the code type-checks; the T09a implementer had to add the guard and report it as a deviation.
  Evidence: `docs/reports/P1-I6/P1-I6-T09a.md` (Deviations); `reports_technical.py` (`days_overdue`). Status: active
- **L-P1-I6-2** · 2026-10-20 · tags: tooling
  The first `just check` in a fresh worktree can end with a bare exit 247 at the pyright step and no output (probably the process killed while the machine is busy); the same tree passes on the second run, and `uv run pyright` alone reports 0 errors. Rerun once before reading it as a type error.
  Evidence: `docs/reports/P1-I6/P1-I6-T09b.md` (Learnings). Status: active
- **L-P1-I6-3** · 2026-10-20 · tags: tests, ledger
  A test helper that appends a raw event to an item must use the item's own record type as the stream type (`item.record_type`), not the module's first type: the Technical and Commercial items are streams of `correspondence.TechnicalItem` and `correspondence.CommercialItem`, and confidentiality keys its hidden-stream filter on the stream type. `CorrWorld.forge_item_event` used `correspondence.Correspondence` and would have written a clearance event on the wrong stream type.
  Evidence: `packages/tl-modules/correspondence/src/tl_mod_correspondence/testing.py` (`forge_item_event`); `confseed.py` (the privileged RFI). Status: active
- **L-P1-I6-4** · 2026-10-20 · tags: process, tooling
  A mutation run edits the source files in place, so nothing else can run in that worktree while it works (a test run, a stub generator, a commit with `add -A`). Give the run its own worktree: `git worktree add --detach /home/user/wt/<inc>-mut HEAD`, copy the uncommitted tests, `uv sync --all-packages`, and use a copy of the harness whose temporary files (`last.log`, the mutant list) have their own names so that two runs can go at once. The 170 mutants of four handler files take about an hour at 25 s each.
  Evidence: `scratchpad` harness copies; P1-I6 handler tickets T02a, T02b, T04a, T04b. Status: active
- **L-P1-I6-5** · 2026-10-20 · tags: tickets, process
  When tickets of one batch stub files that other tickets' provided tests call, stub only the files of the tickets in the batch and keep the other references in the tree: T02a's test uses `issue_technical`, so the T02b handlers stay as references until T02a is merged, and T02b's provided test lives in `provided/` (not in `tests/`) until then. Tests that call stubbed handlers from elsewhere (`test_domain_flow.py`, `test_evidence.py`) go to `docs/tickets/<inc>/held/` and are restored after the merge.
  Evidence: `docs/tickets/P1-I6/README.md` (order of work). Status: active
- **L-P1-I6-6** · 2026-10-20 · tags: security, ledger
  A feed card made by the generic rules is hidden only through the records it is tagged with, so an event that names no record in its payload makes a card that nobody can hide: the correspondence events (`Correspondence.Defined`, `ClearanceGranted`) and `File.Processed` (it carries the file, not the record) leaked "ctl defined a commercial" and "svc:scanner processed 2 files". Tag a confidential stream's events with the stream, look the record of a file event up in `cur_files`, and test per reader by comparing counts with a reader who may read nothing: a summary holds no token to search for. Cards projected earlier need `just rebuild-projections feed`.
  Evidence: `tl_core/feed/cards.py` (`subjects_of`), `tl_core/projection/feed.py` (`_subjects`), `test_the_feed_cards_do_not_tell_a_reader_what_happened_to_what_they_may_not_read`. Status: active
- **L-P1-I6-7** · 2026-10-20 · tags: tests, env
  A project id with a hyphen (the simulator's `project:sim-<run>`) could not number anything: `{project}` takes the scope's id and the pattern refuses anything but letters and digits, so every project-scoped pattern failed in a simulation (`value 'sim-rt1' for field 'project' must be letters and digits`). The allocator now spells the project without its symbols (`simrt1`); keys and counters are per scope, so two projects that spell alike never share a number. A second thing a simulated project lacks is a working calendar: the clocks of an issued RFI count on `<project>-default@1`, a file in the schema directory, so a run needs `sim-<run>-default@1.yaml` before the first issue.
  Evidence: `tl_core/numbering/allocator.py` (`segment_values`), `tests/services/test_numbering.py`, `packages/tl-sim/tests/test_rfi_end_to_end.py` (`schema_with_calendar`). Status: active
