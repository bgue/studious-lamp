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
