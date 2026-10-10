# P0-I5-T12 — Runbook: local Postgres for the parity suite, and the compose service

Status: merged
Tier: haiku
Labels: docs
Depends on: —
Branch: `p0/i5a-t12-postgres-runbook`

## Goal
A developer or agent can start Postgres, run the parity suite, point a ledger at a Postgres schema, and clean up after a killed test run, by following
one runbook. `dev/docker-compose.yml` also documents a Postgres service for machines that have Docker (documentation only, ADR-0002).

## Brief references (pasted)
> **ADR-0002.** The build container has no Docker daemon; PostgreSQL 16 runs natively (`sudo pg_ctlcluster 16 main start`, user `postgres` /
> password `postgres`, database `tl_test`). Connection string via `TL_PG_URL`, default `postgresql://postgres:postgres@localhost:5432/tl_test`.
> `docker-compose.yml` stays as documentation for developers with Docker.

### Facts the runbook must state (all verified by the supervisor; copy the commands as written)
- Start and check the cluster: `sudo pg_ctlcluster 16 main start` then `pg_isready -h localhost` (prints `localhost:5432 - accepting connections`).
  `just dev up` does the same when Postgres is down.
- The URL: `export TL_PG_URL=postgresql://postgres:postgres@localhost:5432/tl_test` (the SessionStart hook exports it).
- Create the database if it is missing: `cd /tmp && sudo -u postgres psql -c "CREATE DATABASE tl_test"`.
- Run the parity suite: `just test-parity`. One module: `just test-parity tests/services/test_record_commands.py`.
  The suite fails (does not skip) when Postgres is unreachable, because `just test-parity` sets `TL_REQUIRE_POSTGRES=1`. `just test` runs SQLite only;
  Postgres-only tests in it skip when the server is unreachable.
- How the tests isolate themselves: each pytest session creates a throw-away database named `tl_pytest_<8 hex creation time>_<6 hex>` on the server
  `TL_PG_URL` names and drops it when the session ends, at interpreter exit, and on SIGTERM; each test gets its own schema `tl_t_<16 hex>` inside it.
  If the role cannot create databases, schemas are created in the database the URL names. Concurrent sessions never share a database or the ledger lock.
- After a SIGKILL (or a power loss) the database is left behind. The next session sweeps it automatically once it is older than 3 hours and has no open
  connection (`tl_adapters.postgres.admin.sweep_stale_databases`). To clean up by hand, only when no test run is in progress, because the pattern also matches
  other people's live sessions:
  ```
  psql "postgresql://postgres:postgres@localhost:5432/postgres" -Atc "SELECT datname FROM pg_database WHERE datname LIKE 'tl\_pytest\_%'"
  psql "postgresql://postgres:postgres@localhost:5432/postgres" -c 'DROP DATABASE "tl_pytest_<suffix>" WITH (FORCE)'
  ```
- The Postgres driver is `pg8000` (pure Python, BSD-3-Clause); there is nothing to install besides `uv sync --all-packages`. A write that waits more than 10 seconds
  for the ledger lock raises `tl_core.services.errors.LockTimeoutError` (on SQLite too, after its busy timeout).
- Using the adapter from code: the target is a `postgresql://` URL; `tl_adapters.db.open_uow(url)`, `create_schema(url)` and `rebuild_projections(url)`
  work the same as with a SQLite path. To keep several ledgers in one database, scope the URL to a schema:
  `tl_adapters.postgres.admin.create_schema_namespace(url, "tl_demo")` then `schema_url(url, "tl_demo")`.
- Long-running workers: `tl_adapters.postgres.factory.PostgresUowFactory(url)` (`factory()` write, `factory(readonly=True)` snapshot, `dispose()` at exit).
- Change-feed wake-ups: `NotifyListener(url, wake_event)` from `tl_adapters.postgres.notify` sets the event after each commit; pass the same
  event to `ChangePoller(..., wake=event)`. Delivery stays correct without it; it only makes it prompt.
- How writes behave (for the "Verify" section): every write transaction first takes one advisory lock, so writers queue (like SQLite's write lock);
  a writer that waits more than 10 seconds fails with a lock-timeout error. Readers never wait. `seq` has no gaps.
- Text columns are byte-ordered (`COLLATE "C"`) so sorting matches SQLite whatever the server locale.

## Interfaces (verbatim from the repo at the branch point)
```yaml
# dev/docker-compose.yml (current content; add the postgres service, keep minio untouched)
services:
  minio:
    image: minio/minio:RELEASE.2025-04-22T22-12-26Z
    ...
volumes:
  minio-data:
```
```yaml
# the service to add (under `services:`), and the volume (under `volumes:`)
  postgres:
    image: postgres:16
    environment:
      POSTGRES_PASSWORD: postgres
      POSTGRES_DB: tl_test
    ports:
      - "5432:5432"
    volumes:
      - postgres-data:/var/lib/postgresql/data
  # volumes:
  postgres-data:
```

## Context (read these, nothing else)
- `AGENTS.md`
- `docs/templates/runbook.md`
- `docs/runbooks/rebuild-projections.md` (style reference)
- `dev/docker-compose.yml`
may explore: (none)

## Allowed paths
- `docs/runbooks/postgres-local-setup.md` (create)
- `dev/docker-compose.yml` (edit)
- `docs/reports/P0-I5/P0-I5-T12.md` (create: your report; commit it)

## Steps
1. Write the runbook from `docs/templates/runbook.md`: Purpose, When to use, Before you start, Steps (numbered: start, set URL, run parity, one module,
   code usage, wake-ups), Verify, Roll back (cleanup of leftover databases, including after a SIGKILL), Related (`docs/adr/0002-build-environment-constraints.md`,
   `packages/tl-adapters/README.md`, `docs/runbooks/rebuild-projections.md`). Name the brief section as `§14`. Delete the template's guidance lines.
2. Add the compose service and volume.
3. Run every command you wrote that is safe to run (`pg_isready`, `just test-parity packages/tl-adapters/tests/test_postgres_factory.py`) and paste the output in the report.

## Acceptance
```
just check
uv run python -c "import yaml; d=yaml.safe_load(open('dev/docker-compose.yml')); print(sorted(d['services']), sorted(d['volumes']))"
grep -c "TL_PG_URL" docs/runbooks/postgres-local-setup.md
just test-parity packages/tl-adapters/tests/test_postgres_factory.py
```
Expected: `just check` clean; the second command prints `['minio', 'postgres'] ['minio-data', 'postgres-data']`; the grep count is at least 2; the last command passes with
no skips.

## Tests to add
None (documentation).

## Report requirements
Standard report plus the command outputs above. State in the report which facts from this ticket you could not verify.

## Escalation triggers
- A command in the *Facts* list fails when you run it: write *Blocked* with the output; do not rewrite the fact.
- Anything that would need an edit outside *Allowed paths*.

## Blocked
(implementer writes here)

## Decision
(supervisor or orchestrator writes here)
