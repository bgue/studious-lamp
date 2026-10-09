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
