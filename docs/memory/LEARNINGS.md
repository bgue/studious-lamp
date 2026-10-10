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

**Status values:** `active`; `superseded by L-…`; `promoted to <ADR-nnnn | AGENTS.md | skill | build-spec file>`.
Entries are never deleted. At each phase exit the orchestrator marks superseded and promoted entries and moves
them to `docs/memory/archive/<phase>.md`, keeping the *Active* list under about 150 lines.

**Not for:** decisions that change a contract or interface (write an ADR), secrets or credentials, anything a
test or a generated artefact already enforces, or narrative history (that belongs in reports).

## Active

- **L-P0-SETUP-1** · 2026-10-09 · tags: env
  The build container has the Docker CLI but no Docker daemon. Anything that needs MinIO, Postgres, or other
  services must run natively or be mocked; `docker compose` is documentation only.
  Evidence: `docker ps` fails on `/var/run/docker.sock`; ADR-0002. Status: active

- **L-P0-SETUP-2** · 2026-10-09 · tags: env
  The egress proxy refuses `dl.min.io` and similar binary hosts with a 403 on CONNECT. PyPI via `uv` and apt work.
  Try a binary download once, then fall back to the PyPI or mock path; never loop on retries.
  Evidence: curl exit 56 on dl.min.io; ADR-0002. Status: active

- **L-P0-SETUP-3** · 2026-10-09 · tags: env, tooling
  `just` is not preinstalled; install it with `uv tool install rust-just` and keep `$HOME/.local/bin` on PATH.
  The SessionStart hook does both.
  Evidence: `.claude/hooks/session-start.sh`. Status: active

- **L-P0-SETUP-4** · 2026-10-09 · tags: env
  Agents run as root. A `$SUDO` variable that is empty for root breaks `$SUDO -u postgres psql` silently, because the
  shell then runs `-u` as a command. Use `sudo -u postgres` directly (sudo exists) and `cd /tmp` first to avoid
  chdir warnings.
  Evidence: SessionStart hook fix, `as_postgres` helper. Status: active

- **L-P0-SETUP-5** · 2026-10-09 · tags: env, tests
  Native PostgreSQL 16 starts with `sudo pg_ctlcluster 16 main start`; parity tests use
  `TL_PG_URL=postgresql://postgres:postgres@localhost:5432/tl_test`, which the SessionStart hook exports.
  Evidence: hook validation run. Status: active

- **L-P0-SETUP-6** · 2026-10-09 · tags: tooling
  `uv` prints "UV_NATIVE_TLS is deprecated" on every call in this container. It is harmless noise from the
  environment; do not try to fix it from the repo and do not count it as a failure in reports.
  Evidence: `uv run` output. Status: active

- **L-P0-SETUP-7** · 2026-10-09 · tags: tooling
  `git push` may print "fatal: expected 'acknowledgments', received 'packfile'" and "push negotiation failed;
  proceeding anyway" and still succeed. Check for the `->` ref-update line before retrying.
  Evidence: pushes of the first two commits. Status: active

- **L-P0-SETUP-8** · 2026-10-09 · tags: process
  Subagents cannot spawn subagents in this harness (no `Agent` tool inside a supervisor). Only the top-level session
  spawns; supervisors return DISPATCH/DONE/BLOCKED and the orchestrator runs `.claude/workflows/ticket-batch.js`.
  Evidence: capability probe of a supervisor agent; ADR-0004. Status: active

- **L-P0-SETUP-9** · 2026-10-09 · tags: process, env
  Workflow agent concurrency is min(16, CPUs - 2); this container has 4 CPUs, so 2 agents run at once. Size DISPATCH
  batches at 2–4 tickets.
  Evidence: workflow-authoring reference; `nproc` = 4. Status: active

- **L-P0-I1-1** · 2026-10-09 · tags: tests, tooling
  A `conftest.py` only applies to tests beneath its directory, so shared fixtures live in a root `conftest.py`
  (not `tests/conftest.py`), and pytest runs with `--import-mode=importlib` so identically named test files in
  different packages (`test_import.py`) do not collide.
  Evidence: root `pyproject.toml` `[tool.pytest.ini_options]`; `03` §10. Status: active

- **L-P0-I1-2** · 2026-10-09 · tags: tooling
  pyright strict rejects a pydantic subclass that narrows a base field type (`datetime | None` to `datetime`), so
  `Event` is not a subclass of `NewEvent`. `linkml` ships no type stubs, so modules importing it start with
  `# pyright: basic`. Strict applies to `src` directories only; tests use standard mode.
  Evidence: `docs/tickets/P0-I1/T05-ledger-types-and-hashing.md`, `T03-codegen-wiring.md`. Status: active

- **L-P0-I1-3** · 2026-10-09 · tags: tooling
  Codegen drift is checked by comparing generator output with the committed files (`python -m tl_schema.generate
  --check`), not by `git diff`, because a diff fails on any dirty tree and misses untracked files. LinkML generators
  embed the schema path they were given, so they must run inside `schema/core/` with a relative file name.
  Evidence: `justfile` `check` recipe; `docs/tickets/P0-I1/T03-codegen-wiring.md`. Status: active

- **L-P0-I1-4** · 2026-10-09 · tags: schema
  `gen-json-schema` renders a custom `dict`-based LinkML type as `string`. JSON-valued slots therefore use
  `range: Any` (class `Any`, `class_uri: linkml:Any`) plus the annotation `tl:json: true`. `linkml-lint` also warns
  when the prefix `tl` is mapped to a non-canonical namespace, so schemas declare the prefix `throughline` and use
  `tl:` only as the annotation tag namespace.
  Evidence: `schema/core/record.yaml`, `annotations.yaml`; `linkml-lint schema/core/core.yaml` clean. Status: active
- **L-P0-SETUP-10** · 2026-10-09 · tags: process, tooling
  Git cannot hold a branch `p0/i1` and a branch `p0/i1/t01-…` at the same time (ref namespace clash). Ticket branches are
  siblings: `p0/i1-t01-<slug>`. The branch passed by the orchestrator overrides a ticket's Branch field.
  Evidence: `fatal: cannot lock ref 'refs/heads/p0/i1/t01-monorepo-scaffold'` in the first ticket-batch run. Status: active

- **L-P0-I1-5** · 2026-10-09 · tags: tooling, ledger
  SQLite through SQLAlchemy: pysqlite's legacy transaction control breaks an explicit `BEGIN IMMEDIATE`. Set
  `dbapi_connection.isolation_level = None` on connect and issue `BEGIN IMMEDIATE` (writes) or `BEGIN` (reads) from the
  SQLAlchemy `begin` event, chosen by a connection execution option. `executescript` (via `engine.raw_connection()`)
  is needed to run schema files whose trigger bodies contain semicolons.
  Evidence: `docs/tickets/P0-I1/T06-sqlite-ledger-adapter.md` (`engine.py`); two-thread race test passes. Status: active

- **L-P0-I1-6** · 2026-10-09 · tags: tooling
  pyright strict flags `@contextmanager` functions annotated `Iterator[X]` (use `Generator[X]`), and ruff's
  `E501` applies to docstrings and comments at 100 columns, so wrap prose when writing modules. Provided test files
  must be ruff-clean before commit because implementers may not edit them.
  Evidence: scratch builds of T04b and T07. Status: active

- **L-P0-I1-7** · 2026-10-09 · tags: tooling
  ruff 0.16 formats Markdown as well as Python, so `ruff format --check .` flags files under `docs/`. The root
  `[tool.ruff]` therefore sets `include = ["*.py", "*.pyi", "**/pyproject.toml"]`. A scratch build without `docs/`
  missed this; verify scaffold tickets in a checkout that contains the whole repo.
  Evidence: T01 implementer report `docs/reports/P0-I1/P0-I1-T01.md`. Status: active

- **L-P0-I1-8** · 2026-10-09 · tags: process, tests
  A supervisor-provided failing test committed in the package test tree makes `just check` (pyright includes tests)
  red on every other ticket branch cut from the same base. Store provided tests under
  `docs/tickets/<inc>/provided/<name>.py.txt` and have the ticket `cp` them into place; the reviewer `diff`s the pair.
  Evidence: attempted commit of `test_sqlite_ledger.py` failed pyright with unresolved imports. Status: active

- **L-P0-I1-9** · 2026-10-09 · tags: ledger, tests
  A bus with per-subscriber `seq` cursors drops any event published after a later one, so publish order must equal
  commit order. Do not publish while holding a lock (a nested write from a subscriber deadlocks, and re-entrancy would
  reorder); commit and enqueue under the lock, then drain from a single drainer (`OrderedPublisher`). A test that delays
  every third publish proves the ordering; a nested-write test and a slow-subscriber test prove liveness. A plain concurrent-writer test did not catch the bug until the
  delay was added. Projector test helpers use portable SQL (UPDATE then INSERT) and non-`cur_` table names.
  Evidence: `packages/tl-adapters/tests/test_sqlite_uow.py` `SlowBus`; reviewer finding on `bus.py`. Status: active

- **L-P0-I1-10** · 2026-10-09 · tags: tooling
  A Protocol attribute (`ledger: Ledger`) is invariant, so an adapter that narrows it (`SqliteLedger`) fails pyright
  strict; declare Protocol attributes that implementers may narrow as read-only `@property`.
  Evidence: T11 blocked on 11 pyright errors; `tl_core/uow.py`. Status: active

- **L-P0-I1-11** · 2026-10-09 · tags: tests
  A concurrency invariant needs a deterministic seam, not repetition: the lost-wakeup test replaces the publisher's lock
  with one that runs a second writer right after a given release, and a deliberately wrong `LeakyPublisher` proves the
  test can fail. Three clean runs of a racy test prove nothing. Threads in such tests are `daemon=True` and joined
  with a timeout so a regression fails instead of hanging the suite.
  Evidence: `packages/tl-core/tests/test_bus.py`; mutation (flag cleared outside the lock) fails the test. Status: active

- **L-P0-I2-O1** · 2026-10-09 · tags: process
  The workflow tells implementers to commit a report at docs/reports/<inc>/<ticket>.md, which is outside the ticket's
  Allowed paths. One reviewer flagged it and forced a retry that deleted the report. The review prompt now says that
  path is always allowed. Supervisors may also add it to every ticket's Allowed paths.
  Evidence: P0-I2-T12 attempt 1 review. Status: active
- **L-P0-I2-B1** · 2026-10-09 · tags: tests, tui
  pytest runs in importlib mode, so a test cannot `import` a sibling helper file. `packages/tl-tui/tests/conftest.py`
  puts its own directory on `sys.path`, which lets tests write `from fakes import FakeClient`; pyright resolves the
  same import from the file's directory. Do not add `__init__.py` to test directories.
  Evidence: `packages/tl-tui/tests/conftest.py`, `test_grid.py`. Status: active

- **L-P0-I2-B2** · 2026-10-09 · tags: tests, tui
  No async pytest plugin is installed, and none may be added without a ticket. Drive a Textual app with
  `tests/helpers.run_pilot(app, scenario, size=(120, 40))` (a plain `asyncio.run` around `app.run_test`) and assert on
  `screen_text(app)`. Snapshot tests use `snap_compare(app_instance, terminal_size=(120, 40))`; the plugin writes
  `__snapshots__/<module>/<test>.raw` beside the test file and passes across separate processes.
  Evidence: `packages/tl-tui/tests/helpers.py`; a spike snapshot test ran twice with identical output. Status: active

- **L-P0-I2-B3** · 2026-10-09 · tags: tooling, tui
  `App[None]` is not assignable to `App[object]` (the type parameter is invariant), so test helpers take `App[Any]`
  and `Pilot[Any]`. `ScrollView` widgets draw only in `render_line(y)`, with `y` relative to the viewport; add
  `scroll_offset.y` yourself and keep a sticky header on line 0 by adding one to `virtual_size.height`.
  Evidence: pyright errors in the first `test_grid.py`; `widgets/grid.py`. Status: active

- **L-P0-I2-B4** · 2026-10-09 · tags: tui, tooling
  Do not name a widget or screen attribute after a Textual DOM property: `self.visible = [...]` on a `ModalScreen`
  raised `TypeError: unhashable type: 'list'` at runtime because `visible` is a DOM property (`shown` works). Textual
  `Static` also parses `[...]` as markup, so any text that can hold user data needs `markup=False` or `rich.text.Text`.
  Evidence: T13b scratch build; `widgets/column_chooser.py`. Status: active

- **L-P0-I2-B5** · 2026-10-09 · tags: tui, process
  A grid must never load every page on the UI thread: the first `RecordGrid` did, and froze for 2.7 s at 20k rows
  (about 15 s at 50k). Sort goes to the server (`order_by`), and "go to end" pages in a `run_worker(thread=True)`
  worker that reports through `post_message` and applies results with `call_from_thread`, guarded by a generation
  counter. A moving cursor must not trigger paging inside that apply step or the cap is overshot.
  Evidence: supervisor-pieces review of 73bb88c; `test_grid.py::test_end_pages_in_a_worker_reports_progress_and_caps`. Status: active

- **L-P0-I2-B6** · 2026-10-09 · tags: tui, tooling
  In Textual 8.2.8 an `Input` built with a non-empty value raises `NoActiveAppError` outside a running app, so a widget
  that wraps one must create it in `compose()`, not `__init__`. An `Input` also posts `Changed` once at mount with its
  initial value; compare against the last seen raw value so that echo is not treated as an edit.
  Evidence: `widgets/form_fields.py`, T16a review. Status: active
- **L-P0-I2-1** · 2026-10-09 · tags: tests, tooling
  With `--import-mode=importlib` a test module cannot `from conftest import ...`; share helpers between test files as
  pytest fixtures (`build_docs`, `effective`, `fixture_dir` in `packages/tl-schema/tests/conftest.py`). pyright strict
  also rejects partly typed third-party calls: annotate `jsonschema` validators and errors as `Any`, and linkml
  metamodel objects as `Any` (their dict/list unions make every attribute access an error).
  Evidence: `docs/tickets/P0-I2/provided/test_registry.py.txt`; `tl_schema/linkml_render.py`. Status: active

- **L-P0-I2-2** · 2026-10-09 · tags: schema, tooling
  To render an effective schema as LinkML, load `core.yaml` with `SchemaView`, call `merge_imports()`, mutate the
  `SchemaDefinition` (classes, enums, annotations), then wrap it in a fresh `SchemaView(definition)`; renaming the
  root schema of the original view breaks its import resolution. Annotations assigned in memory must be `Annotation`
  objects (`tag`, `value`) to match what a YAML load produces.
  Evidence: `packages/tl-schema/src/tl_schema/linkml_render.py`, `tests/test_linkml_render.py`. Status: active

- **L-P0-I2-3** · 2026-10-09 · tags: process, tests
  A supervisor-written stub (names, signatures, docstrings) plus a provided test file under `docs/tickets/<inc>/provided/`
  plus a spec verified against a scratch reference implementation gave first-attempt passes for 6 of 7 implementer tickets (the seventh, T04b, was flagged only for committing its report file). Keep
  the reference implementation until the ticket merges; it is the takeover path. State in the ticket that the stub's
  `STUB:` docstring paragraph must be removed (T01 left it).
  Evidence: P0-I2 reports T01, T04, T04b, T06, T08, T08a, T10. Status: active

- **L-P0-I2-4** · 2026-10-09 · tags: tooling
  `ruff format` moves a trailing `# type: ignore[...]` off a call it re-wraps, so the ignore stops working. Type the helper
  parameter instead (`layer: Literal[...]`). pyright strict also widens tuple elements to `str`, so build typed values
  (`FieldKind`) through a helper with annotated parameters rather than a list of tuples.
  Evidence: `docs/tickets/P0-I2/provided/test_pset_commands.py.txt`; T04b ticket text. Status: active

- **L-P0-I2-5** · 2026-10-09 · tags: schema, ledger
  Runtime schema changes that add columns (promoted pset properties) are dialect-neutral when the existing columns are found
  with `sqlalchemy.inspect(conn).get_columns(...)` and the `ALTER TABLE ... ADD COLUMN` text is generated per dialect in
  `tl_schema` (SQLite has no `ADD COLUMN IF NOT EXISTS`). Projectors stay deterministic by reading only the event payload
  and existing rows: schema-derived facts (conformance, units) are computed by the command handler and carried in the event.
  Evidence: `tl_core/projection/promoted.py`, `pset.py`; decisions A5, A9. Status: active

- **L-P0-I2-B7** · 2026-10-09 · tags: process
  The ticket workflow tells implementers to commit their report, so list `docs/reports/<inc>/<ticket-id>.md` in every
  ticket's *Allowed paths* and say "commit your report". A ticket that says "return it in your final message" produced one
  review round lost to a committed report (T12) and one report left uncommitted in a worktree (T15).
  Evidence: T12 attempt 1; T15 worktree; tickets T16b onward. Status: active

- **L-P0-I3-O1** · 2026-10-09 · tags: env, process
  A container restart stops background workflows and agents, but the filesystem (repo, worktrees, branches, ~/.local/bin,
  the Postgres data dir) survives. Recover a ticket batch with `Workflow({scriptPath, resumeFromRunId, args})` using
  the same args: finished implementer and reviewer calls replay from the journal and only the interrupted ones rerun.
  Read `<transcriptDir>/journal.jsonl` first to see which agents finished.
  Evidence: P0-I3 batch 2 restart; resumed wf_3b2e992f-50a. Status: active

- **L-P0-I3-O2** · 2026-10-09 · tags: ledger, sync
  Workflow guards are safe on SQLite only because they read inside the BEGIN IMMEDIATE write transaction. On Postgres
  (P0-I5) the guard reads need `SELECT ... FOR UPDATE` on the record row or SERIALIZABLE isolation, or a concurrent
  link retraction can slip between the guard check and the append.
  Evidence: P0-I3 workflow engine review. Status: active
- **L-P0-I3-1** · 2026-10-09 · tags: tests, process
  A provided `*.py.txt` is not covered by `ruff format`, so a hand-written one fails `just check` the moment an implementer
  copies it. Format provided files before committing: copy to a temp `.py`, `ruff format --config pyproject.toml`, copy back. Verify
  a ticket by dropping a scratch reference implementation over the stub in a clean tree, running the provided test, `ruff` and
  `pyright`, then `git checkout . && git clean -fd`; formatting and E501 problems in the reference show up the same way.
  Evidence: `docs/tickets/P0-I3/provided/`, T03 and T05 verification runs. Status: active

- **L-P0-I3-2** · 2026-10-09 · tags: process, ledger
  A stub projector that is registered in `default_registry()` must implement `ddl` and `reset` (only `apply` may raise
  `NotImplementedError`), or every test that calls `create_schema` fails on every ticket branch cut from the base. Decouple
  tickets that read a projection from the ticket that writes it by letting the provided test INSERT projection rows with SQL (T04
  does this for `cur_links`).
  Evidence: `projection/links.py` stub, `test_expected_links.py.txt`. Status: active

- **L-P0-I3-3** · 2026-10-09 · tags: tests, schema
  Adding a `tl:current_state` class to `schema/core` changes the generated file list, so two tests that enumerate it must be
  edited in the same commit: `packages/tl-schema/tests/test_generate.py` (`EXPECTED_KEYS`) and `test_ddl.py`
  (`test_only_current_state_classes_get_tables`).
  Evidence: first `just test` after adding links.yaml failed 4 tests. Status: active

- **L-P0-I3-4** · 2026-10-09 · tags: ledger, tests
  Numbering is safe under SQLite because a write transaction is exclusive, so a thread test alone cannot show that the allocator
  defends itself. The second line of defence (the counter stream's expected version) is tested by monkeypatching the counter read
  to a stale value and expecting `ConcurrencyError`; mutating the allocator to ignore the version makes that test fail.
  Evidence: `tests/services/test_numbering.py::test_a_stale_counter_read_is_stopped_by_the_ledger_version_check`. Status: active

- **L-P0-I3-5** · 2026-10-09 · tags: tooling, tests
  ruff's import sorting treats `tl_*` packages as first-party inside a package's `src` tree (a blank line separates them from
  third-party imports) but as third-party in test files. A reference implementation written outside the repo gets the wrong
  grouping; run `ruff check --fix` on it in place before using it to verify a ticket.
  Evidence: T07 reference failed `I001` on first verification. Status: active

- **L-P0-I3-6** · 2026-10-09 · tags: tui, tests, process
  Growing `ClientInterface` forces every test double to follow, so the fake's new behaviour went into one mixin
  (`packages/tl-tui/tests/fakes_links.py`, tested by `test_fakes_links.py`) before any TUI ticket was cut; tickets then use the
  fake without editing `fakes.py`. The fake reuses the real vocabulary, `next_status` and error types, so a screen tested on it
  meets the same refusals as on the embedded client.
  Evidence: `tests/test_fakes_links.py` (10 tests). Status: active

- **L-P0-I4-B1** · 2026-10-09 · tags: env, tooling
  A fresh `git worktree` has no `.venv` of its own; `uv sync` (without `--all-packages`) installs only the root and leaves
  the workspace packages out, so `just check` shows about 1500 pyright "import could not be resolved" errors and `just test`
  fails at collection. Run `uv sync --all-packages` once per new worktree.
  Evidence: first `just check` in `/home/user/wt/p0-i4b`; `.claude/hooks/session-start.sh` line 60. Status: active

- **L-P0-I4-B2** · 2026-10-09 · tags: tests, tooling
  moto's in-process `mock_aws()` is enough for the s3 backend: no server, no network, and a presigned URL can be used with
  `requests` inside the mock. Bucket names must be at least 3 characters (`"b"` raises `InvalidBucketName`); set fake
  `AWS_*` variables with `monkeypatch`. A same-content `put_object` keeps the same ETag, so "never replaced" cannot be proved
  by comparing object metadata: spy on `client.put_object` (a first version of the test survived a mutation).
  Evidence: `docs/tickets/P0-I4/provided/test_objectstore_s3.py.txt`. Status: active

- **L-P0-I4-B3** · 2026-10-09 · tags: tests
  Test doubles for `io.BufferedReader` must subclass `io.RawIOBase` and implement `readinto`, not `read`: the buffered wrapper
  never calls `read` on the raw object. To prove a store does not read an endless stream to the end, count the bytes asked of
  `readinto`.
  Evidence: `test_objectstore_fs.py.txt` `CountingReader`. Status: active

- **L-P0-I4-B4** · 2026-10-09 · tags: ledger, process
  The `ObjectStore` Protocol has no delete, list or size call. Consequences already handled: presigned uploads go to a
  `staging/` key and are streamed into the content key through `put` (which verifies), staging leftovers need a bucket
  lifecycle rule, and reconciliation uses `iter_keys` on the concrete backends. An object is written before the database
  commit, so a rolled-back upload leaves an unreferenced object; that is harmless because keys are content-addressed.
  Evidence: `tl_core/files/service.py` module docstring, `docs/tickets/P0-I4/README-B.md` D7, D11. Status: active

- **L-P0-I4-B5** · 2026-10-09 · tags: process, tests
  Stub-plus-provided-test tickets again passed the supervisor's verification on the first try because the check dropped a
  scratch reference over the stub and ran `ruff`, `pyright` and the provided test; three references needed a fix at that stage
  (a RawIOBase double, an over-long docstring line, a test that could not fail). Keep the references outside the repo
  (`/home/user/wt/p0-i4b-refs/`) until the tickets merge.
  Evidence: this round's verification runs. Status: active

- **L-P0-I4-B6** · 2026-10-09 · tags: process, api
  Security review of the upload service found four fixable things a test-by-mutation pass had not: a dedupe gate that counted
  quarantined rows (so a second user could read a file before its scan), `hmac.compare_digest` on a client-controlled `str`
  (raises on non-ASCII), a silent public fallback secret, and a global rejected-hash check (kept on purpose, recorded as a
  decision). Rules: gate any "no bytes needed" shortcut on the state that grants read access, compare secrets as bytes, fail
  closed on missing secrets, and serve client-typed files as attachments with `nosniff`.
  Evidence: `docs/tickets/P0-I4/README-B.md` D8, D9, D12, D13; `tests/services/test_file_service.py`. Status: active

- **L-P0-I4-B7** · 2026-10-09 · tags: process, ledger
  Writing a recovery runbook step by step exposed a real defect: an idempotent-retry shortcut ("already attached") returned
  before checking that the object still existed, so re-uploading could not heal a lost object. Every recovery step in a runbook
  needs a test or a demo line that performs it (`test_reuploading_to_the_same_slot_restores_a_lost_object`).
  Also: when restoring stubs over scratch references, `git checkout <dir>` reverts uncommitted doc edits in that directory too;
  commit docs first or restore file by file.
  Evidence: `docs/runbooks/object-store-reconciliation.md` step 3; commit 34fe583. Status: active

- **L-P0-I4-B8** · 2026-10-09 · tags: tests, cli
  `typer.testing.CliRunner.invoke` catches exceptions and returns them on the result, so a CLI test that only asserts "nothing
  changed" passes against a command that crashes (it passed against a `NotImplementedError` stub). Assert `exit_code` and
  `result.exception is None` in every CLI test, including negative-space ones. Implementer-found, T25.
  Evidence: `docs/reports/P0-I4/P0-I4-T25.md`; `packages/tl-cli/tests/test_cli_file_reconcile_exit.py`. Status: active

- **L-P0-I4-B9** · 2026-10-09 · tags: ledger, process
  A spec that says two different things about one case ("a content key is never replaced" for `put`, "always replacing" for
  `put_via_url`) makes the implementer follow the literal text and flag it; the review then rules. Write the invariant once
  at the top of a ticket and derive per-method wording from it. Also: `FsObjectStore` objects are mode 0600 (from
  `mkstemp`), which is kept on purpose: a service running as another user must be given access explicitly.
  Evidence: `docs/reports/P0-I4/P0-I4-T20.md`; orchestrator ruling D14 in README-B. Status: active
- **L-P0-I4-A1** · 2026-10-09 · tags: ledger, tests
  A SQL comparison against a NULL column is NULL, so `NOT (status = 'open')` silently drops records with no status. Compile every
  query predicate two-valued (`col IS NOT NULL AND col = :v`, `NOT EXISTS (...)` for psets) so `-x` and `x!=v` agree and a record
  matches exactly one of `x` and `-x`. `test_not_partitions_the_result` (hypothesis) fails when one comparison loses its NULL guard.
  Evidence: `tl_core/query/compiler.py`, `tests/query/test_query_properties.py`. Status: active

- **L-P0-I4-A2** · 2026-10-09 · tags: ledger, sync
  The change-feed registry drops an event whose `seq` is at or below a subscriber's cursor, which is safe only because each source
  (the bus, a poller) hands over a contiguous ascending run: a source never delivers 10 before 9. SQLite commits serially so this
  holds. Postgres sequences can become visible out of order (a transaction holding seq 9 commits after one holding 10), so the
  P0-I5 poller must lag behind in-flight transactions or re-read a short window before trusting its cursor.
  Evidence: `tl_core/changefeed/registry.py` (`_deliver`), `test_two_sources_feeding_the_same_events_deliver_each_once_in_order`. Status: active

- **L-P0-I4-A3** · 2026-10-09 · tags: process, tooling
  Run `just check` on the branch tip after every supervisor commit, including a docstring-only edit: a 102-column line in
  `api.py` (my A7 docstring change) turned `just check` red for every ticket branch cut from that tip, and the T03 implementer
  correctly stopped as *Blocked*. A *Blocked* caused by the base is not a strike; fix the base, merge it into the ticket branch.
  Evidence: `docs/reports/P0-I4/P0-I4-T03.md` (Blocked, then Decision), commits 56bb651 and 34e109f. Status: active


- **L-P0-I5-B1** · 2026-10-09 · tags: tooling, process
  Never name a module `types.py` (or `enum.py`, `json.py`) inside a package: a script or `python -` run from that directory puts
  it first on `sys.path` and the standard library's own imports break (`cannot import name 'MethodType' from 'types'`). The webhook
  package uses `base.py`.
  Evidence: `packages/tl-core/src/tl_core/webhooks/base.py` (renamed from `types.py` after the first ad-hoc script failed). Status: active

- **L-P0-I5-B2** · 2026-10-09 · tags: ledger, process
  State that a lagging consumer reads later must keep its history. A subscription row holding only its latest enable and disable
  seq made a dispatcher pass that ran after a disable and re-enable drop the events from before the disable; `active_windows`
  (a list of seq intervals) fixed it, and `test_the_active_window_follows_disable_and_enable` runs the late pass on purpose.
  Operational tables that no event produces (`wh_*`) are created by a projector with empty `handles` and a no-op `reset`, so
  `create_schema` makes them and a rebuild never clears a secret or a retry state.
  Evidence: `tests/webhooks/test_dispatcher.py`, `packages/tl-core/src/tl_core/webhooks/state.py`. Status: active

- **L-P0-I5-B3** · 2026-10-09 · tags: process, tests
  When a stub-plus-provided-test ticket sits under code that other tests already exercise, make the stub fail loudly only for the
  part it lacks (`matches_row` raises `NotImplementedError` when one of the five unbuilt filter parts is set) instead of ignoring
  it or raising everywhere: the rest of the suite stays green, and a silently ignored filter part could never leak events.
  Reference implementations for T20 to T23 were checked with `/tmp`-style scripts that copy the reference over the stub, run
  `ruff`, `pyright` and the provided test, then `git checkout -- packages` (commit supervisor edits first: the checkout also reverts them).
  Evidence: `packages/tl-core/src/tl_core/webhooks/filters.py`; docs/tickets/P0-I5/T22-webhook-filter-match.md. Status: active

- **L-P0-I5-B4** · 2026-10-09 · tags: api, tests
  An address allow/deny check must unwrap every IPv6 form that carries an IPv4 address, not only `::ffff:x`: NAT64
  `64:ff9b::/96` and 6to4 `2002::/16` are judged by the address inside, local-use NAT64 `64:ff9b:1::/48` and Teredo
  `2001::/32` are refused. `verify` must also turn non-UTF-8 body bytes into `SignatureError`. Both were found by the
  orchestrator's review of 7b6c704; the cases are rows in `test_webhook_egress.py` and `test_webhook_signing.py`.
  Evidence: `egress.is_public`; orchestrator review at 7b6c704. Status: active

- **L-P0-I5-B5** · 2026-10-09 · tags: ledger, tests
  `uow.ledger.stream_version()` reads through another connection, so it misses events appended earlier in the same unit of
  work and chained commands on one stream fail with `ConcurrencyError`. Read the version with `SELECT MAX(stream_version)`
  on `uow.conn()` (`webhooks.subscriptions.current_version`). The contract scenario chains update, rotate, disable and enable
  in one unit of work on purpose. Also: pyright does not see a sibling test helper in another directory; the root
  `extraPaths = ["tests/webhooks"]` lets `tests/contract` import `world.py`.
  Evidence: `tests/contract/test_webhook_catalog_contract.py`; first run raised `expected version 1, found 2`. Status: active
- **L-P0-I5-A1** · 2026-10-09 · tags: ledger, sync
  On Postgres every write transaction takes one advisory lock first (`engine.write_tx`), the analogue of `BEGIN IMMEDIATE`. That
  resolves L-P0-I4-A2 (commit order equals seq order, so a poller needs no lag window) and L-P0-I3-O2 (guard reads inside a write
  transaction cannot go stale; no `SELECT ... FOR UPDATE` is needed). `seq` is `MAX(seq)+1` under the lock, so it stays gap-free like
  SQLite's; an identity column would burn values on rollback. Writers queue; one that waits more than 10 s fails with a lock timeout.
  Evidence: `test_postgres_ledger.py` (dropping the lock fails five tests); `docs/tickets/P0-I5/README-A.md` D1 to D3. Status: active

- **L-P0-I5-A2** · 2026-10-09 · tags: tooling, ledger
  The Postgres adapter registers driver loaders so `tl_core` sees SQLite-shaped values: JSON as canonical compact text, `timestamptz` as
  `iso_utc` strings, booleans as 0/1, integer sums as ints. Consequence: do not use `sqlalchemy.inspect(conn).get_columns` (SQLAlchemy's
  reflection expects parsed JSON and crashes on a column with a non-default collation); read column names with
  `promoted.table_columns(conn, table)`. `events.payload` stays TEXT because JSONB re-renders numbers and would break re-hashing.
  Evidence: `postgres/engine.py`; the crash appeared in `test_postgres_collation.py`. Status: active

- **L-P0-I5-A3** · 2026-10-09 · tags: schema, tests
  Text sorts by the server locale on Postgres (`en_US.utf8` in the default image, `C.UTF-8` in this container, so a local run hides it)
  and bytewise on SQLite. The generator pins Postgres `TEXT` columns to `COLLATE "C"`; `test_postgres_collation.py` creates an ICU-locale
  database to prove it. Also: LinkML `float` maps to `DOUBLE PRECISION` (Postgres `REAL` is 4 bytes). A dialect property that depends on
  the server's configuration needs a test that creates the unfriendly configuration.
  Evidence: `ddl_types.collated`, `tests/schema/test_generated_ddl_parity.py` precision test fails on `REAL`. Status: active

- **L-P0-I5-A4** · 2026-10-09 · tags: tests
  Hand-written SQL in tests must run on both databases: a boolean column takes `TRUE`/`FALSE` or a bound Python bool (never `0`/`1`),
  a timestamp column takes a full ISO string (never `'x'`), binds are `text(...)` with `:name` (`exec_driver_sql` with `?` fails on
  Postgres), and there is no `sqlite_master`. Of about 80 Postgres failures in the first parity run, all but three were these.
  Evidence: reference conversion in the P0-I5 WS-A refs worktree; tickets T01 to T09 recipe item 4. Status: active

- **L-P0-I5-A5** · 2026-10-09 · tags: tests, tooling
  Parity fixtures: `new_db` is a function-scoped factory; a module-scoped fixture cannot depend on the adapter parameter, so shared
  databases become per-test, and a Hypothesis test calls `new_db()` once per example and adds `HealthCheck.function_scoped_fixture`.
  A killed pytest run leaves its `tl_pytest_<hex>` database behind (the runbook has the cleanup); a `timeout`-killed run did exactly that.
  Evidence: `conftest.py`; `docs/runbooks/postgres-local-setup.md`. Status: active

- **L-P0-I5-A6** · 2026-10-09 · tags: process
  Triage by reference conversion paid off: converting every test module with a script in a scratch worktree and running it on Postgres
  showed in about an hour that production code needed three fixes and the tests needed only mechanical changes, which made the
  tickets small and their acceptance counts exact. The same worktree is the takeover path; keep it until the tickets merge.
  Evidence: `/home/user/wt/p0-i5a-refs`; README-A "Order of work". Status: active

- **L-P0-I5-A7** · 2026-10-09 · tags: process, env
  Check a dependency's licence before adding it. psycopg 3 is LGPL-3.0; a copyleft dependency is a human gate (`04-gates.md` §2) that
  the orchestrator's delegation does not cover, and "pre-approved" in a fanout plan named a driver, not a licence. The Postgres driver is
  `pg8000` (BSD-3-Clause; deps scramp MIT-0, asn1crypto MIT, python-dateutil Apache-2.0/BSD). A new dependency line in a ticket or plan
  names the package and its licence.
  Evidence: orchestrator ruling on P0-I5 WS-A; `packages/tl-adapters/pyproject.toml`. Status: active

- **L-P0-I5-A8** · 2026-10-09 · tags: tooling, ledger
  pg8000 differences that the adapter hides: it ignores libpq `options` (the schema goes in as the startup parameter `search_path`);
  it raises `IntegrityError` only for SQLSTATE 23505, so `engine.py` re-raises every class-23 error as `IntegrityError` (the append-only
  trigger, NOT NULL); it has no blocking wait for `LISTEN`, so `NotifyListener` runs `SELECT 1` every 50 ms and drains
  `conn.notifications`; result coercions are `register_in_adapter(oid, fn)` with fn taking the text value. The loader behaviour that
  `tl_core` relies on (canonical JSON text, ISO UTC timestamps, 0/1 booleans, int sums) is the same under both drivers.
  Evidence: `postgres/engine.py`, `postgres/notify.py`; 150 adapter tests pass on both adapters. Status: active
- **L-P0-I3-7** · 2026-10-09 · tags: tui, tooling
  Textual `OptionList` prompts and `DataTable` cells that are plain `str` are parsed as Rich markup, so `[x]` vanished from a
  row (`▶ [x] KEY` rendered as `▶  KEY`). Wrap row text in `rich.text.Text(...)`. `query_one("#id", Select[str])` raises
  `TypeError` at run time (subscripted generic): query `Select` and annotate the variable `Select[str]`. A screen method named
  `action_toggle` overrides `DOMNode.action_toggle` and fails pyright; use `action_toggle_select`. Textual's own command palette
  owns Ctrl+P: set `ENABLE_COMMAND_PALETTE = False` on the app before binding it.
  Evidence: `widgets/link_picker.py`, `app.py`, first pilot runs of `test_link_picker`. Status: active

- **L-P0-I3-8** · 2026-10-09 · tags: tui
  App-level `Binding`s (`l`, `w`, `t`, `R`) do not fire while an `Input` has focus (it consumes printable keys), but they do fire
  under a `ModalScreen` whose focus is elsewhere, so every new app action starts with `if self._modal_open(): return`.
  `app.post_message(RecordChanged)` is delivered to the app only, never to a child `RecordView`: after a modal command call
  `view.reload()` (`TlApp._changed`).
  Evidence: `tests/test_palette.py::test_the_l_w_t_keys_are_typed_into_the_palette_not_run`, workflow-menu refresh test. Status: active

- **L-P0-I3-9** · 2026-10-09 · tags: tui, process
  Textual delivers `Select.Changed` asynchronously, after a programmatic `select.value = ...` has returned, so a reentrancy flag
  (`_setting = True ... False`) never covers the event: the picker's own change was read as the user's and froze the relation. Remember
  the value the code assigned and compare `event.value` with it. A review that probes with a second record type found it; the
  provided test only used one type and could not see it.
  Evidence: T12 escalation; `tests/test_link_picker.py::test_the_relation_follows_the_highlighted_record_until_the_user_changes_it`. Status: active

- **L-P0-I3-10** · 2026-10-09 · tags: core, services
  Handlers never commit and read the projections of the caller's own transaction, so a new command that needs several writes to be
  atomic is a composition: call the existing handlers in order inside the one unit of work, chain `expected_version` from each result,
  share one `correlation_id`, and let the caller's rollback undo everything when a part raises. No new write path was needed for
  `EditRecord`. A part that changes nothing raises `NoChangesError` before it appends, so it can be skipped safely.
  Evidence: `services/edit.py`, `tests/services/test_edit_record.py` (rollback and stale-version cases). Status: active

- **L-P0-I3-11** · 2026-10-09 · tags: process, tickets
  A ticket that tells the implementer to implement a questionable behaviour "as written" and to raise it as an open question works: T13b's
  spec ended the tray on the first successful link and hid the refusals of the rest; the implementer kept the spec, reported the
  question, and the supervisor decided with the orchestrator. Two Haiku tickets that run in one batch cannot depend on each other's code
  (T02b `trace` needed T14a): leave the dependent piece out of the ticket and add it after the merge.
  Evidence: `docs/reports/P0-I3/P0-I3-T13b.md`, decisions D26 and D27. Status: active
- **L-P0-I5-O1** · 2026-10-09 · tags: dependencies, gates
  Check the licence of every new dependency and its transitive tree before adding it. psycopg 3 is LGPL-3.0, and
  linkml's hard `jsonschema[format]` pulls rfc3987 (GPL-3.0+). Both are copyleft, which is a human gate. Use pg8000 for
  Postgres, and keep the root `override-dependencies` that swaps in `jsonschema[format-nongpl]`. Name the licence in
  the relay NOTE and in APPROVALS.md. Policy and allow-list: ADR-0006.
  Evidence: orchestrator licence scan during P0-I5. Status: active

- **L-P0-I4-C1** · 2026-10-09 · tags: api, tests
  FastAPI 0.143 keeps included routers lazy: `app.routes` holds `_IncludedRouter` objects, not `APIRoute`s. To visit every
  operation (for example to prove each route calls the authorise hook) iterate `app.openapi()["paths"]`. Dependencies with `yield`
  exit after the response is built, so a command route opens its unit of work inside the handler, never in a `yield` dependency.
  Evidence: `packages/tl-api/tests/test_auth.py::test_every_route_calls_the_hook`; `routes/files.py`. Status: active

- **L-P0-I4-C2** · 2026-10-09 · tags: api, tests
  Starlette's `TestClient` (an httpx2 client) and httpx's ASGI transport return only when the whole response is complete, so an SSE
  stream never reaches the test. Run the app under uvicorn on `127.0.0.1:0` in a daemon thread (`Harness.live()`), read it with an
  `httpx2.Client.stream(...)` and a short `Timeout`, and stop it with `server.should_exit`. Give the app a lifespan so the change-feed
  poller runs there; a `TestClient` used without `with` runs no lifespan.
  Evidence: `packages/tl-api/tests/harness.py`, `test_stream.py` (10 tests, stable over repeated runs). Status: active

- **L-P0-I4-C3** · 2026-10-09 · tags: api, tooling
  A module that builds FastAPI endpoints in a loop must not use `from __future__ import annotations`: FastAPI evaluates the string
  annotations in the module's globals, so `Annotated[str, Depends(guard(action))]` fails with `NameError` when `action` is a closure
  variable. `tl_api/commands.py` omits the import; body models are set through `endpoint.__annotations__["body"] = model`. A body
  model built at run time also needs `# pyright: ignore[reportInvalidTypeForm]` where it is used as an annotation.
  Evidence: `packages/tl-api/src/tl_api/commands.py`, `routes/files.py`. Status: active

- **L-P0-I4-C4** · 2026-10-09 · tags: env, mcp, api
  This environment resolves `mcp` 2.x and `httpx2`: `FastMCP` is now `mcp.server.mcpserver.MCPServer`, `mcp.Client(server)` talks to
  a server in memory, and there is no `httpx` module (use `httpx2`; Starlette's `TestClient` already does). `fastapi.sse` exists but
  the API hand-rolls its SSE framing (`tl_api/feed.py`) so the wire format is fixed by our tests, not a library default.
  Evidence: `uv run python -c "import httpx"` fails; `.venv/.../mcp/server/fastmcp.py` raises ModuleNotFoundError. Status: active

- **L-P0-I4-C5** · 2026-10-09 · tags: process, env
  Licence check for a new dependency (ADR-0006): walk `Requires-Dist` from the new roots through `importlib.metadata` and print
  `License-Expression` or the classifiers for every distribution in the closure, then list `uv.lock` entries that exist only behind
  platform markers. fastapi, uvicorn, httpx2 and mcp pull MIT, BSD-3-Clause, Apache-2.0 and PSF-2.0 distributions only.
  Evidence: scratch scan of 27 distributions, no GPL, LGPL, AGPL or MPL. Status: active

- **L-P0-I4-C6** · 2026-10-09 · tags: process, api
  A route stub ticket must keep every decorator, parameter, annotation and docstring that reaches the OpenAPI document, because the
  document is committed and drift-checked. Dropping the scratch reference over the stub and running `python -m tl_api.openapi --check`
  caught a description that differed between reference and stub (it would have turned `just check` red on every ticket branch).
  Evidence: T42 `role` query description; `docs/tickets/P0-I4/T42-reference-routes.md`. Status: active

- **L-P0-I4-C7** · 2026-10-09 · tags: api, security
  FastAPI reads and decodes the request body before it runs dependencies, so a `guard` dependency alone answers an unauthenticated request
  with a broken JSON body 422, not 401 (the security review found it on 14 routes). Authenticate in an ASGI middleware that runs before the
  route, keep `guard` for the per-route `authorize` call, and serve `/openapi.json` ourselves (`openapi_url=None` plus a guarded route
  with `include_in_schema=False`) so no default route sits outside the token. A streaming response releases its resources in the response
  object (`SlotResponse.__call__`), not in the generator: a generator the server never starts never runs its `finally`.
  Evidence: `test_authentication_comes_before_the_body_is_read`, `test_the_slot_is_released_even_when_the_response_never_starts`; each fails when its fix is removed. Status: active

- **L-P0-I4-C8** · 2026-10-09 · tags: process, tests
  Making a stub ticket from a finished reference is mechanical: copy the reference outside the repo, replace every function body with
  `raise NotImplementedError("STUB (<ticket>)")` using `ast` line numbers (`/home/user/wt/p0-i4c-refs/stubify.py`), let `ruff check --fix`
  drop the imports the stub no longer uses, then diff the import lines of stub and reference: that diff is the "imports to add" list the
  ticket must carry (without it an implementer meets `F401`/`F821` and guesses). Run the OpenAPI check before committing the stubs: the
  `EventPage` docstring I added while moving it changed the committed document and I had committed it red once.
  Evidence: S9/S10 commits; ticket texts T43, T46-T48. Status: active

- **L-P0-I4-C9** · 2026-10-09 · tags: api, tests
  A catch-all `@app.exception_handler(Exception)` is run by Starlette's `ServerErrorMiddleware`, which sends the handler's response and
  then re-raises: uvicorn logs a traceback and closes the keep-alive connection, so the next pooled client request fails with a raw
  `ReadError` (4 of 10 calls in the review's repro). Register one handler per mapped class (`app.add_exception_handler(cls, ...)` for every
  row of `ERROR_TABLE`, plus pydantic's `ValidationError`) and keep the `Exception` handler for real 500s only. A single request over
  `TestClient` never shows it; the regression test sends 20 sequential errors over one pooled connection to a live server.
  Evidence: `test_mapped_errors_leave_the_connection_usable` (fails before the fix). Status: active

- **L-P0-I4-C10** · 2026-10-09 · tags: process
  A stub script that replaces every function body also stubs the helpers a ticket calls "given" (T43's `dump`), and the ticket then
  contradicts its own stub; the implementer rightly implemented it and reported a deviation. Keep given helpers out of the stubbing
  (list them to the script) or say "implement" in the ticket. Also: a review fix that changes a base class the open tickets rely on (here
  `ApiClientBase._send` raising `ApiUnavailableError`) must stay compatible with their provided tests, because a changed provided file
  makes the reviewer's `diff` fail: the new error subclasses `httpx2.TransportError` for that reason.
  Evidence: `docs/reports/P0-I4/P0-I4-T43.md` deviation; `ApiUnavailableError` in `client/base.py`. Status: active
- **L-P0-I5-O2** · 2026-10-09 · tags: environment, lake
  DuckDB cannot `INSTALL` extensions here because extensions.duckdb.org is refused. Install the PyPI packages
  `duckdb-extensions` and `duckdb-extension-ducklake`, with `duckdb` pinned to the same version (1.5.5), and call
  `duckdb_extensions.import_extension('ducklake')` before `LOAD ducklake`. Parquet and JSON are built in. pgBackRest is
  installable with apt. GitHub release downloads work. Details: the ADR-0002 addendum.
  Evidence: orchestrator probes before P0-I7. Status: active
- **L-P0-I5-O3** · 2026-10-09 · tags: env, process
  Refines L-P0-I3-O1. Before resuming a ticket-batch workflow after a restart, read its journal. For every implementer
  with no `result` line, remove its worktree and delete its ticket branch (`git worktree remove --force`, `git branch -D`),
  so the rerun's `git worktree add -b` starts clean. Keep a worktree whose implementer finished; an interrupted review
  re-creates its own detached worktree. Resume reviewers and supervisors with SendMessage, and tell them their
  background test runs are gone.
  Evidence: second restart during P0-I4/I5; resumed three workflows and four agents. Status: active
- **L-P0-I5-O4** · 2026-10-10 · tags: process, budget
  At about 6 h into the run, with 7 supervisors and reviewers plus 3 workflows in flight, the account hit its usage
  limit. Every running subagent died with HTTP 429 ("session limit, resets <time>"). After the reset, workflows resume
  as after a restart (L-P0-I5-O3): finished calls replay from the journal. Lesson: cap concurrency at about 3 or 4
  active supervisors or workflows, and finish increments on the critical path before starting later ones.
  Evidence: P0-I4, P0-I5 and P0-I7 batches failed together at 00:10 UTC reset notice. Status: active
- **L-P0-I5-O5** · 2026-10-10 · tags: process, worktrees
  Never bulk-remove `/home/user/wt/review-*` or ticket worktrees while any ticket-batch workflow is running. Reviewers
  work in those directories, and removing one mid-review breaks that review. Clean up only the worktrees of workflows
  that have finished, by exact name, and check the running workflows' journals for `started review` lines first.
  Evidence: the orchestrator removed two in-flight P0-I4 review worktrees (T43, T46) during the P0-I5 cleanup. Status: active

- **L-P0-I5-A9** · 2026-10-10 · tags: tests, process
  Parity costs time: tests/query takes about 70 s on SQLite and about 7 minutes on both adapters under load, the Hypothesis property
  tests are about ten times slower on Postgres (each example makes a schema), and the full `just test-parity` (1214 tests) took 11 minutes on a loaded container. Give a
  CI job and any `timeout` a budget of 20 minutes, and do not wrap these runs in a 2-minute tool timeout. `just test-parity` also deselects the
  tests that never use a database fixture, so its total is lower than a `--adapters sqlite,postgres` count by design; a ticket that quotes
  both numbers says so.
  Evidence: reports P0-I5-T04, T06, T07, T08, T09; `docs/reports/P0-I5-A.md`. Status: active

- **L-P0-I5-A10** · 2026-10-10 · tags: tooling
  A docstring copied from a spec into a Python file must escape backslashes (`\\s`), or the module compiles with a `SyntaxWarning` on every
  run; a ticket that renames a test must say so in *Tests to add* when it also says "every test keeps its name"; a provided-test ticket's
  `git diff --stat` only lists new files once they are committed.
  Evidence: reports P0-I5-T13 and T09. Status: active

- **L-P0-I5-B6** · 2026-10-09 · tags: tests
  The ledger stamps `recorded_at` with the real clock, so a test that mixes a `FakeClock` (retry timers, lease expiry) with an
  expiry compared against event times breaks the day the calendar passes the fake date: `test_expired_subscriptions_stop_receiving`
  failed on 2026-10-10 because the fake "tomorrow" was already in the past of real events. Anything compared with event time uses
  the real clock; anything compared with delivery state uses the fake one.
  Evidence: `tests/webhooks/test_dispatcher.py`; failure on the first run after the date changed. Status: active

- **L-P0-I5-B7** · 2026-10-10 · tags: process, tooling
  When two increments create the same path (`tl_adapters/sqlite/factory.py` in P0-I4 workstream C and in P0-I5 workstream B), the
  orchestrator names the canonical commit and the later branch copies the file verbatim and adapts its callers, rather than merging
  two different files. After merging workstream A, `just check` failed on codegen drift because its `COLLATE "C"` change altered the
  Postgres DDL of tables that workstream B had added: run `just gen` after every merge that touches a generator.
  Evidence: `git show c073261:...factory.py`; `differs: ddl/postgres/wh_delivery.sql`. Status: active

- **L-P0-I4-D1** · 2026-10-10 · tags: tui, tooling
  `query` is a Textual DOM method, so `self.query = "..."` on a widget fails pyright and would break at run time (the L-P0-I2-B4 trap again, one more
  name: `filter_text` is the grid's). Widget `DEFAULT_CSS` loses to the base widget's pseudo-class rule: `FilterBar Input { border: none }` was ignored
  while the `Input` had focus; write `FilterBar Input, FilterBar Input:focus { ... }`.
  Evidence: `widgets/grid.py` (`filter_text`), `widgets/filter_bar.py` CSS; the first pilot run drew a tall border over the caret line. Status: active

- **L-P0-I4-D2** · 2026-10-10 · tags: process, tooling
  Never undo a mutation check with `git checkout <file>` when the file holds uncommitted work: it reverted every uncommitted edit of `app.py`, which had to be
  rewritten. Copy the file aside first (`cp f /tmp/f.bak`) or commit, then restore from the copy. Same root as L-P0-I4-B7.
  Evidence: the `own_writes` mutation run in this workstream. Status: active

- **L-P0-I4-D3** · 2026-10-10 · tags: tui, api
  `ApiClient.stream_events(reconnect=True)` swallows outages, so a TUI that wants a "server unreachable" banner must use `reconnect=False` and run its own loop
  (probe, state, backoff, resume from the last `seq`). The API has no head endpoint: `tl_tui.remote.find_head` bisects `GET /events?limit=1`
  (about 2 log2 n requests) to start a feed at "now" with no gap. A listener attached after the first failed call (the grid loads before the app attaches)
  must be told the current state at once, or the banner never shows.
  Evidence: `tests/test_remote_feed.py` (restart, unreachable at start), `test_live_remote_app.py`; mutations of `after=` and of `find_head` fail them. Status: active

- **L-P0-I4-D4** · 2026-10-10 · tags: tui, tests
  Threaded refreshes need three tests that a happy-path run does not give: the UI answers a key while the worker sleeps (`test_the_ui_stays_responsive...`), a result
  that arrives after the rows were replaced is dropped (generation guard; the mutation that removes it fails two tests), and a burst of N events costs a few reads,
  not N. A mark timer can fire a hair before its deadline, so it re-arms for what is left. A "changed by someone else" mark must not depend on what an earlier
  read showed: an outage refresh and a replayed event can both read the same version.
  Evidence: `tests/test_live_app.py`, `grid.py` `_expire_marks`. Status: active

- **L-P0-I4-D5** · 2026-10-10 · tags: tui, api, tests
  Review of the live path found three ordering faults that every happy-path test passes: the feed took its cursor after the grid's first read (an event in the gap
  was lost), a command's SSE event can beat its HTTP response (so the user's own save looked foreign), and a replaced ledger leaves a cursor ahead of the head.
  Take the cursor before the first read, hold events on an in-flight stream until the response is noted (with a cap), and compare the head with the cursor after a
  drop. Each has a test that forces the order (a hook after the first load, a gated fake, a scripted API) and fails when the fix is removed. Also: a refresh applied
  during shutdown posts messages to a screen that is gone, so handlers that query the DOM must tolerate it.
  Evidence: `tests/test_live_handoff.py`, `test_live_app.py`; `app.py` `on_record_highlighted` (a 1-in-6 flake in the full-file run). Status: active

- **L-P0-I4-D6** · 2026-10-10 · tags: tests, tui
  An intermittent test failure is two readers of one fact racing, not noise: the outage test asserted "row is marked" at the first moment the row existed, but the row
  can arrive through the read after "connection restored" and the mark through the replayed event a few milliseconds later. Fix the assertion to wait for the end state
  (the claim is that both orders end marked), prove it 20 of 20 and 30 of 30 in a loop, and write down which two events race. A failing test on the base also blocks every
  ticket's whole-suite acceptance command (T60 was reported blocked by it).
  Evidence: `test_live_remote_app.py::test_remote_the_banner_shows_during_an_outage_and_the_feed_resumes` failed 7 of 20 before, 0 of 50 after. Status: active
