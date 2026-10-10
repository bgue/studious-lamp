# Runbook — local Postgres for the parity suite

Purpose: start the native PostgreSQL 16 cluster, run the parity suite against it, point a ledger at a Postgres schema, and clean up databases left by a killed test run. Brief: §14. Build constraints: `docs/adr/0002-build-environment-constraints.md`.

## When to use
- Trigger: `just test-parity` fails because Postgres is unreachable (it fails rather than skips, by design).
- Trigger: you need a ledger on Postgres from code or a worker, not SQLite.
- Trigger: a killed test run (SIGKILL, power loss) left `tl_pytest_*` databases on the server.

## Before you start
- Access needed: the `postgres` role (password `postgres`) on `localhost:5432`, database `tl_test`; `sudo` to start the cluster. ADR-0002 names the native cluster `16 main`; no Docker daemon is needed.
- Python dependencies: `uv sync --all-packages`. The driver is `pg8000` (pure Python, BSD-3-Clause); nothing else to install.
- Safe to run during business hours: yes for starting the cluster and running the suite. The leftover-database cleanup in Roll back is not: run it only when no test run is in progress.

## Steps
1. Start the cluster and check that it accepts connections:
   ```
   sudo pg_ctlcluster 16 main start
   pg_isready -h localhost
   ```
   Expected: `localhost:5432 - accepting connections`.
   If the cluster is already running, `pg_ctlcluster` prints `Cluster is already running.` and exits with status 2; this is harmless, and `pg_isready` is the check that matters.
   If Postgres is down, `just dev up` does the same start.

2. Set the connection URL. The SessionStart hook exports it; in a shell where it is not set, run:
   ```
   export TL_PG_URL=postgresql://postgres:postgres@localhost:5432/tl_test
   ```
   This is also the default in ADR-0002.

3. Create the database if it is missing:
   ```
   cd /tmp && sudo -u postgres psql -c "CREATE DATABASE tl_test"
   ```
   Expected: `CREATE DATABASE`. If it already exists, psql prints `ERROR:  database "tl_test" already exists` and exits with status 1; nothing else changes.

4. Run the parity suite:
   ```
   just test-parity
   ```
   `just test-parity` sets `TL_REQUIRE_POSTGRES=1`, so an unreachable server is a failure, never a skip. `just test` runs SQLite only; Postgres-only tests in it skip when the server is unreachable.

5. Run one module:
   ```
   just test-parity tests/services/test_record_commands.py
   ```

6. Use a ledger on Postgres from code. The target is a `postgresql://` URL, and these take it the same way they take a SQLite path:
   - `tl_adapters.db.open_uow(url)`
   - `create_schema(url)`
   - `rebuild_projections(url)`

   To keep several ledgers in one database, scope the URL to a schema: call `tl_adapters.postgres.admin.create_schema_namespace(url, "tl_demo")`, then use `schema_url(url, "tl_demo")` as the ledger URL.

   Long-running workers use `tl_adapters.postgres.factory.PostgresUowFactory(url)`: `factory()` for a write unit of work, `factory(readonly=True)` for a snapshot read, and `dispose()` at exit.

7. Change-feed wake-ups (optional). `NotifyListener(url, wake_event)` from `tl_adapters.postgres.notify` sets `wake_event` after each commit. Pass the same event to the poller as `ChangePoller(..., wake=event)`. Delivery stays correct without it; it only makes it prompt.

## Verify
- `pg_isready -h localhost` prints `localhost:5432 - accepting connections`.
- `just test-parity packages/tl-adapters/tests/test_postgres_factory.py` passes with no skips.
- Each test session creates a throw-away database named `tl_pytest_<8 hex creation time>_<6 hex>` on the server `TL_PG_URL` names. Each test gets its own schema `tl_t_<16 hex>` inside it. If the role cannot create databases, the schemas are created in the database the URL names. Concurrent sessions never share a database or the ledger lock.
- Write behaviour: every write transaction first takes one advisory lock, so writers queue (as SQLite's write lock does). A writer that waits more than 10 seconds raises `tl_core.services.errors.LockTimeoutError` (on SQLite too, after its busy timeout). Readers never wait. `seq` has no gaps.
- Text columns are byte-ordered (`COLLATE "C"`), so sorting matches SQLite whatever the server locale.

## Roll back
- Nothing to undo for the setup itself: the cluster keeps running, and `TL_PG_URL` only lasts for the shell it was exported in.
- Each test session drops its own `tl_pytest_*` database at session end, at interpreter exit, and on SIGTERM. Only a SIGKILL or a power loss leaves one behind.
- After a SIGKILL or power loss, the next session sweeps leftover databases automatically once they are older than 3 hours and have no open connection (`tl_adapters.postgres.admin.sweep_stale_databases`). Nothing needs doing unless you want the space back sooner.
- To clean up by hand, run these only when no test run is in progress, because the pattern also matches other people's live sessions. List the leftover databases:
  ```
  psql "postgresql://postgres:postgres@localhost:5432/postgres" -Atc "SELECT datname FROM pg_database WHERE datname LIKE 'tl\_pytest\_%'"
  ```
  Then drop each one, replacing `<suffix>` with the part of its name after `tl_pytest_`:
  ```
  psql "postgresql://postgres:postgres@localhost:5432/postgres" -c 'DROP DATABASE "tl_pytest_<suffix>" WITH (FORCE)'
  ```

## Related
- `docs/adr/0002-build-environment-constraints.md` (native Postgres 16 in the build container; `docker-compose.yml` is documentation only).
- `packages/tl-adapters/README.md` (Postgres adapter, `rebuild_projections`).
- `docs/runbooks/rebuild-projections.md` (rebuilding current-state tables, SQLite ledger).
- `dev/docker-compose.yml` (the `postgres` service, for machines with Docker). It publishes host port 5432, the same port as the native cluster of ADR-0002: run one or the other, or change the left-hand port in the compose file and `TL_PG_URL` together.
- Brief §14.
