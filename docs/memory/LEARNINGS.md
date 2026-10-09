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
