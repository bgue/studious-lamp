# P1-I0-T39 — Runbooks that say the ledger is a SQLite file

Status: ready
Tier: haiku
Labels: docs
Depends on: P1-I0-T31 to T38 merged on `p1/i0b` (the commands now take either database)
Branch: `p1/i0b-t39-runbooks-postgres`

## Goal
Five runbooks name the ledger as a SQLite file although every command they use now accepts a `postgresql://` URL as well. After this ticket each says so in the place a reader looks (the *Access needed* line, the lock sentence, the *Related* list) and links the new runbook `docs/runbooks/run-on-postgres.md`. No command, behaviour or number changes: only the sentences below.

## Brief references (pasted)
> Fanout P1-I0 exit criterion, Postgres: "`tl serve`, `tl tui`, `tl webhook`, `tl lake`, `tl file` and the embedded feed accept a `postgresql://` URL wherever they accept a SQLite path, through one backend factory."
>
> Facts you may state (all verified; copy them, do not add others): `TL_DB` (or the root `--db`) takes a SQLite file path or a `postgresql://` URL. On Postgres a writer waits for the ledger advisory lock for up to 10 seconds and then gets `LockTimeoutError`, where SQLite waits for its 5 second busy timeout. A projection rebuild on Postgres is statement-bound, about 160 events a second. The password in a URL is shown as `***` in every message.

## Interfaces
none (documentation only).

## Context (read these, nothing else)
- `docs/runbooks/run-on-postgres.md` (the new runbook; read only)
- `docs/runbooks/rebuild-projections.md`
- `docs/runbooks/webhook-operations.md`
- `docs/runbooks/lake-sync.md`
- `docs/runbooks/object-store-reconciliation.md`
- `docs/runbooks/postgres-local-setup.md`
may explore: (none)

## Allowed paths
- `docs/runbooks/rebuild-projections.md`
- `docs/runbooks/webhook-operations.md`
- `docs/runbooks/lake-sync.md`
- `docs/runbooks/object-store-reconciliation.md`
- `docs/runbooks/postgres-local-setup.md`
- `docs/reports/P1-I0/P1-I0-T39.md` (create: your report; commit it)

## Steps
Make exactly these edits. Use the Edit tool. Keep every other line as it is.

1. `rebuild-projections.md`
   - In *Before you start*, replace the whole line `- Access needed: read and write access to the SQLite ledger file (`TL_DB`, default `./dev/data/tl.db`).` with:
     `- Access needed: read and write access to the ledger: the SQLite file or the `postgresql://` URL in `TL_DB` (default `./dev/data/tl.db`; for Postgres see `docs/runbooks/run-on-postgres.md`).`
   - In the next bullet (`- Safe to run during business hours: ...`), keep the text and append at its end: ` On Postgres the rebuild takes the ledger advisory lock in the same way: a writer waits up to 10 s and then gets `LockTimeoutError`, and the rebuild itself is statement-bound (about 160 events a second), so give a large ledger hours, not minutes.`
   - In *Related*, add as the last bullet: `- `docs/runbooks/run-on-postgres.md` (the same commands on a Postgres ledger).`
2. `webhook-operations.md`: in *Before you start*, in the line starting `- Access needed: the ledger (`TL_DB`)`, replace `the ledger (`TL_DB`)` with `the ledger (`TL_DB`: a SQLite file or a `postgresql://` URL; see `docs/runbooks/run-on-postgres.md`)`.
3. `lake-sync.md`: in *Before you start*, in the line starting `- Access needed: read access to the ledger file`, replace `read access to the ledger file (`TL_DB`, default `./dev/data/tl.db`)` with `read access to the ledger (`TL_DB`: the SQLite file, default `./dev/data/tl.db`, or a `postgresql://` URL; a sync reads one consistent snapshot of either)`.
   - In *Related*, add as the last bullet the same link line as for `rebuild-projections.md`.
4. `object-store-reconciliation.md`: in *Before you start*, in the line starting `- Access needed: read access to the ledger (`TL_DB`)`, replace `(`TL_DB`)` with `(`TL_DB`: a SQLite file or a `postgresql://` URL)`.
   - In *Related*, add as the last bullet the same link line as for `rebuild-projections.md`.
5. `postgres-local-setup.md`
   - In *Steps*, after step 7 (the one that begins `7. Change-feed wake-ups (optional).`) add a new step:
     `8. Run the services on it. Export the URL as `TL_DB` and every `tl` command, `tl serve` and `tl tui` use the Postgres ledger: `docs/runbooks/run-on-postgres.md`.`
   - In *Related*, change `(rebuilding current-state tables, SQLite ledger).` to `(rebuilding current-state tables).` and add as the last bullet: `- `docs/runbooks/run-on-postgres.md` (the API, the TUI and the `tl` commands on a Postgres ledger).`
6. Write your report.

## Change log
- Supervisor ruling after the first run (BLOCKED at 5fc5f82): the Acceptance `grep` expects `run-on-postgres` in all five files, but steps 3 and 4 added no link. Both now also add the *Related* bullet. The lake-sync sentence "a sync reads one consistent snapshot of either" was checked on SQLite: `tl_lake.source.read_snapshot` uses the adapter's deferred read transaction, which in WAL mode fixes its snapshot at the first read, and `packages/tl-adapters/tests/test_backend.py::test_the_read_connection_is_one_snapshot` shows a commit made during the transaction stays invisible on SQLite as on Postgres. The sentence is true and stays.

## Acceptance
```
just check
grep -n "run-on-postgres" docs/runbooks/rebuild-projections.md docs/runbooks/webhook-operations.md docs/runbooks/lake-sync.md docs/runbooks/object-store-reconciliation.md docs/runbooks/postgres-local-setup.md
git diff --stat
```
Expected: `just check` clean; `grep` prints at least one line for each of the five files (two for `rebuild-projections.md` and `postgres-local-setup.md`); `git diff --stat` lists only the five runbooks and your report.

## Tests to add
none.

## Report requirements
Standard report. Under *Changed files* give one line per runbook. Paste the three acceptance outputs.

## Rules to remember (from the project's learnings)
- Write and edit files with the Edit or Write tool, not shell heredocs. Never use `pkill -f`.
- No model names in committed files. Dates are ISO. Commit as `P1-I0-T39: <summary>` with your report in the same commit.
- Run `uv sync --all-packages` once in a new worktree before `just check`.

## Escalation triggers
- Stop and report *Blocked* if a line to replace is not where this ticket says it is (a runbook was edited since), or if you think a fact above is wrong.

## Blocked
(implementer writes here)

## Decision
(supervisor or orchestrator writes here)
