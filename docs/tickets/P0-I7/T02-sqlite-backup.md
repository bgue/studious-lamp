# P0-I7-T02 — `tl backup sqlite`: online snapshot with SQLite's backup API

Status: ready
Tier: haiku
Labels: adapter, cli
Depends on: —
Branch: `p0/i7a-t02-sqlite-backup`

## Goal
`tl backup sqlite --to FILE` writes a consistent, standalone snapshot of the dev ledger while it is in use, and prints one summary line. The service function
`tl_adapters.sqlite.backup.backup_database` does the work; the command only parses options, calls it, and prints. Stubs exist for both (`sqlite/backup.py`, `tl_cli/backup.py`,
registered in `main.py`). Two provided test files (6 + 5 tests) must pass.

## Brief references (pasted)
> **24.3 Backup, Database layer, dev:** Litestream continuous replication to MinIO/S3; **SQLite online backup API for snapshots**. Targets: RPO <= 5 min for the database.
> **ADR-0002:** the dev backup path is the SQLite online-backup API plus the ledger archive (24.3), which is the database-independent restore path anyway.
> **Build spec:** the CLI contains no business logic. A subcommand parses options, makes one call, prints.

### Specification (the provided tests check it)
`backup_database(source, dest) -> BackupResult`, all in `packages/tl-adapters/src/tl_adapters/sqlite/backup.py` (dialect-specific SQL is allowed only under `tl_adapters`):
1. `source` must be an existing file, else `BackupError(f"source database not found: {src}")`. Never create it (open it read-only with
   `sqlite3.connect(f"file:{source}?mode=ro", uri=True)`).
2. `dest` must not exist, else `BackupError(f"destination exists: {dst}")`. Create its parent directories. Never replace an existing file.
3. Write into a temp file in the destination directory (`tempfile.mkstemp(dir=dst.parent, prefix=f".{dst.name}.tmp-")`, close the descriptor), copy with
   `reader.backup(writer)` (the `sqlite3.Connection.backup` method, default arguments: one consistent snapshot while writers carry on), then on the **writer**:
   `PRAGMA integrity_check` must return `ok` (else `BackupError("the snapshot failed SQLite's integrity check")`), then `PRAGMA journal_mode=DELETE` (call `.fetchone()` on it) so the
   snapshot is one file with no `-wal` or `-shm` sidecar.
4. `head_seq` is `SELECT COALESCE(MAX(seq), 0) FROM events` on the snapshot, or 0 when there is no `events` table (look in `sqlite_master`).
5. Close both connections; compute the SHA-256 of the file and its size; `os.fsync` it; `os.chmod(tmp, 0o444)`; publish with `os.link(tmp, dst)` (turn `FileExistsError` into the same
   "destination exists" `BackupError`) and always unlink the temp file in a `finally`. Any `sqlite3.Error` becomes `BackupError(f"could not snapshot {src}: {error}")`. Nothing may be
   left at `dest` or as a temp file after a failure.
6. Return `BackupResult(source, dest, bytes, sha256, head_seq, seconds)` where `seconds` is `time.perf_counter()` elapsed over the whole call.

`tl backup sqlite --to PATH` (`tl_cli/backup.py`): the source is the root `--db` (`ctx.obj`, a `Path`). On success print exactly one line with `typer.echo`:
`backed up {head_seq} events from {source} to {dest} ({bytes} bytes, sha256 {sha256})`. On `BackupError` call `_fail(str(exc))` (it prints `error: <message>` to stderr and exits 1).

Learnings that apply:
- Provided tests live under `docs/tickets/P0-I7/provided/*.py.txt`; copy them into the test tree as named in *Acceptance* and do not edit them.
- Keep the stub's names, signatures and option declarations. Remove the `STUB (P0-I7-T02)` paragraph from both module docstrings when you are done.
- `CliRunner.invoke` catches exceptions and returns them on the result, so a CLI test must assert the exit code and `result.exception` (the provided tests do).
- ruff limits lines to 100 columns; run `uv run ruff format` before committing. `uv` prints "UV_NATIVE_TLS is deprecated"; ignore it. Do not pipe `just check` into `tail`.
- `tl_adapters` is pyright strict: annotate everything; `sqlite3` rows are untyped, so wrap values in `int(...)` / `str(...)` where needed.

## Interfaces (verbatim from the repo at the branch point)
```python
# packages/tl-adapters/src/tl_adapters/sqlite/backup.py (the stub you fill in)
class BackupError(Exception):
    """A snapshot could not be taken; nothing was left at the destination."""

@dataclass(frozen=True)
class BackupResult:
    source: Path
    dest: Path
    bytes: int  # size of the snapshot file
    sha256: str  # hex SHA-256 of the snapshot file
    head_seq: int  # highest events.seq in the snapshot (0 when the events table is empty or absent)
    seconds: float  # wall time of the whole call

def backup_database(source: str | Path, dest: str | Path) -> BackupResult: ...
```
```python
# packages/tl-cli/src/tl_cli/backup.py (the stub you fill in; `_fail` exists)
@app.command("sqlite")
def sqlite_backup(ctx: typer.Context, to: Annotated[Path, typer.Option("--to", help="...")]) -> None: ...
```

## Context (read these, nothing else)
- `packages/tl-adapters/src/tl_adapters/sqlite/backup.py`
- `packages/tl-cli/src/tl_cli/backup.py`
- `docs/tickets/P0-I7/provided/test_sqlite_backup.py.txt`
- `docs/tickets/P0-I7/provided/test_cli_backup.py.txt`
may explore: (none)

## Allowed paths
- `packages/tl-adapters/src/tl_adapters/sqlite/backup.py` (edit)
- `packages/tl-cli/src/tl_cli/backup.py` (edit)
- `packages/tl-adapters/tests/test_sqlite_backup.py` (create: the provided file, unedited)
- `packages/tl-cli/tests/test_cli_backup.py` (create: the provided file, unedited)
- `docs/reports/P0-I7/P0-I7-T02.md` (create: your report; commit it)

## Acceptance
```
cp docs/tickets/P0-I7/provided/test_sqlite_backup.py.txt packages/tl-adapters/tests/test_sqlite_backup.py
cp docs/tickets/P0-I7/provided/test_cli_backup.py.txt packages/tl-cli/tests/test_cli_backup.py
uv run pytest packages/tl-adapters/tests/test_sqlite_backup.py packages/tl-cli/tests/test_cli_backup.py -q
just check
diff docs/tickets/P0-I7/provided/test_sqlite_backup.py.txt packages/tl-adapters/tests/test_sqlite_backup.py
diff docs/tickets/P0-I7/provided/test_cli_backup.py.txt packages/tl-cli/tests/test_cli_backup.py
```
Expected: 12 passed; `just check` clean; both `diff` commands print nothing.

## Tests to add
None beyond the provided files.

## Report requirements
Standard report (`docs/templates/haiku-report.md`), saved at `docs/reports/P0-I7/P0-I7-T02.md` and committed.

## Escalation triggers
- Stop and report *Blocked* if a provided test seems to contradict the specification above.

## Blocked
(implementer writes here)

## Decision
(supervisor or orchestrator writes here)
