# ADR-0002 — Build environment constraints (no Docker, native Postgres, no MinIO egress)

Status: accepted
Date: 2026-10-09
Deciders: repository owner (observed in the cloud build container)
Brief sections: §14, §24.1, §29.4

## Context
The cloud container used for agent runs has: Python 3.12 and 3.13, `uv`, `just` (via `uv tool install rust-just`),
`node` 22, `cargo`, `apt-get` (works), the Docker CLI but **no Docker daemon**, PostgreSQL 16 installable and runnable
natively (`pg_ctlcluster 16 main start`, user `postgres`/`postgres`, db `tl_test`), and an egress proxy that
**refuses `dl.min.io`** (and likely other binary download hosts). PyPI is reachable through `uv`.

## Decision
1. **No increment may require Docker.** `just dev up` starts what it can natively (Postgres cluster if installed) and
   prints what it skipped. `dev/docker-compose.yml` stays for developers with Docker.
2. **Object store adapter has two backends:** `fs` (content-addressed files under `dev/data/objects/`, default in dev
   and in every test) and `s3` (boto3, for MinIO/S3). `s3` is tested against the `moto` server fixture from PyPI; no
   ticket may assume a live MinIO. Presigned URLs in `fs` mode are `file://` paths plus a signed token.
3. **Postgres parity runs against the native cluster.** Connection string via `TL_PG_URL`, default
   `postgresql://postgres:postgres@localhost:5432/tl_test`. CI uses a service container; the dev container uses apt.
4. **Backup tooling is pluggable.** Litestream and pgBackRest are configured but not required locally: the dev
   backup path is the SQLite online-backup API plus the ledger archive (§24.3), which is the database-independent
   restore path anyway and is what the restore drill exercises.
5. **Binaries that need egress** (MinIO, Litestream, xeokit-convert via npm, IfcOpenShell wheels) are tried once by
   the supervisor; on failure the ticket is re-scoped to the mock or `fs` path and the failure is noted in the report.
   Never retry downloads in a loop.

## Consequences
- Phase 0 I4 WS-B tickets: `fs` backend first, `s3` backend second with `moto`; compose file is documentation only.
- Phase 0 I7 WS-A: restore drill uses the ledger archive and SQLite backup; pgBackRest config is written, not run.
- Phase 3 M12: IFC processing uses the `ifcopenshell` wheel from PyPI if it installs; XKT conversion is a job stub
  with a recorded `desktop_only` fallback until a Node build is confirmed.
- Supervisors add `requires: [postgres]` or `requires: [s3]` markers to tests so they skip cleanly when absent.

## Alternatives considered
| Option | Why not |
|---|---|
| Block until Docker is available | Stalls every increment from I4 on |
| Skip object storage until prod | Files are first-class (§20); the `fs` backend keeps the contract exercised |

## Addendum, 2026-10-09: probes for P0-I7 (orchestrator)
| Need | Probe result | Use |
|---|---|---|
| DuckLake extension | `INSTALL ducklake` fails because extensions.duckdb.org is refused by the proxy. The PyPI packages `duckdb-extensions` and `duckdb-extension-ducklake` (both MIT) install. With them, `duckdb_extensions.import_extension('ducklake')` and `LOAD ducklake` work, and so do ATTACH and CREATE TABLE. | Pin `duckdb==1.5.5`: the extension wheel's version must equal duckdb's. Never call `INSTALL` from code; use `import_extension`. |
| Parquet, JSON in DuckDB | Built into the duckdb wheel, already loaded. | No install needed. |
| pgBackRest | `apt-get install pgbackrest` resolves (2.50, Ubuntu noble; MIT). | P0-I7 may run a real local backup and restore drill against the native cluster, instead of writing config only. |
| Litestream | Not packaged by apt or PyPI. The GitHub release tarball download returns 200 (Apache-2.0). | The supervisor may fetch the pinned release once, per the download rule above. The fallback is the SQLite online backup API. |
