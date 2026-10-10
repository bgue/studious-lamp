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
