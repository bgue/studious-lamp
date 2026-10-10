# P0-I7-T04 — `tl restore --from-archive DIR --db TARGET`

Status: ready
Tier: haiku
Labels: cli
Depends on: P0-I7-S11 (`restore_from_archive`), P0-I7-T01 (`FsArchiveStore`), both merged into the base of this branch
Branch: `p0/i7a-t04-cli-restore`

## Goal
`tl restore` rebuilds an empty SQLite file or an empty Postgres schema from a ledger archive alone and prints what it did. The command skeleton, `_fail`, the option declarations and its registration
in `main.py` (`tl restore`, a top-level command) exist in `packages/tl-cli/src/tl_cli/restore.py`; the body raises `NotImplementedError`. A provided test file (7 tests) must pass. The command contains
no restore logic: it parses options, makes one call into `tl_adapters.restore`, and prints.

## Brief references (pasted)
> **24.4 Restore, Rebuild-from-archive (last resort):** fresh database, replay the ledger archive, rebuild projections. Proves the system can survive total database loss.
> **Fanout D1:** restore inserts events verbatim through a per-dialect admin function (`restore_events`), not `Ledger.append`; it refuses a non-empty `events` table.
> **Operational note:** promoted pset columns come from the schema packages in force at restore time (`TL_SCHEMA_DIR`); restore with the same schema directory the ledger used.

### Specification (the provided test checks it)
Body of `restore(from_archive, db, public_key)`, in this order:
1. `from_archive` must be a directory, else `_fail(f"no archive at {from_archive}")`.
2. The public key path is `--public-key` or, when absent, `public_key_path(DEFAULT_KEY_PATH)`. `load_public_key` raising `FileNotFoundError` or `ValueError` goes to
   `_fail(f"cannot read the public key {path}: {exc}")`.
3. If `db` is not a Postgres URL (`not is_postgres(db)`), create its parent directory: `Path(db).parent.mkdir(parents=True, exist_ok=True)`. (Do this only after steps 1 and 2 pass, so a refused call creates nothing.)
4. `result = restore_from_archive(FsArchiveStore(from_archive), db, public_key=public)`.
   - `RestoreError`: if `exc.issue` is not `None`, first print (stdout) `divergence: {kind} segment={segment or '-'} seq={seq or '-'}: {detail}` (`-` only when `seq` is `None`), then `_fail(str(exc))`.
   - any other `ArchiveError`: `_fail(str(exc))`.
5. On success print two lines: `restored {events} events from {segments} segments into {display_target(db)} (last seq {last_seq})` and
   `verify {verify_seconds:.2f}s, insert {insert_seconds:.2f}s, rebuild {rebuild_seconds:.2f}s, total {total_seconds:.2f}s`.
`display_target` hides a Postgres password; never print the raw `db` string.

Learnings that apply:
- Provided tests live under `docs/tickets/P0-I7/provided/*.py.txt`; copy the file into the test tree as named in *Acceptance* and do not edit it.
- Keep the stub's option declarations and signature. Remove the `STUB (P0-I7-T04)` sentence from the module docstring. Add back the imports you use.
- `CliRunner.invoke` catches exceptions and returns them on the result, so tests assert `exit_code` and `result.exception`; a clean `typer.Exit` shows up as `SystemExit`.
- The Postgres test needs the native cluster (`pg_isready -h localhost`); `just test` skips it when unreachable. To run it: `uv run pytest packages/tl-cli/tests/test_cli_restore.py -q` with `TL_PG_URL` set (the session hook sets it).
- ruff limits lines to 100 columns; run `uv run ruff format` before committing. `uv` prints "UV_NATIVE_TLS is deprecated"; ignore it. Do not pipe `just check` into `tail`.

## Interfaces (verbatim from the repo at the branch point)
```python
# tl_adapters.restore
def restore_from_archive(store: ArchiveStore, target: DbTarget, *, public_key: bytes,
                         registry=None, schema_provider=None) -> RestoreResult
@dataclass(frozen=True)
class RestoreResult:
    events: int; segments: int; last_seq: int
    verify_seconds: float; insert_seconds: float; rebuild_seconds: float; total_seconds: float
# tl_core.archive
class ArchiveError(Exception): ...
class RestoreError(ArchiveError):
    issue: VerifyIssue | None          # the first divergence, when verification caused the refusal
class VerifyIssue(BaseModel):
    kind: str; segment: str | None; seq: int | None; detail: str
def load_public_key(path: Path) -> bytes     # FileNotFoundError / ValueError
def public_key_path(private_path: Path) -> Path
DEFAULT_KEY_PATH: Path
# tl_adapters
class FsArchiveStore:  # tl_adapters.archivestore ; FsArchiveStore(root)
def is_postgres(target) -> bool; def display_target(target) -> str       # tl_adapters.db
```
```python
# packages/tl-cli/src/tl_cli/restore.py (the stub you fill in; `_fail` exists)
def restore(from_archive: Annotated[Path, typer.Option("--from-archive", ...)],
            db: Annotated[str, typer.Option("--db", ...)],
            public_key: Annotated[Path | None, typer.Option("--public-key", ...)] = None) -> None: ...
```

## Context (read these, nothing else)
- `packages/tl-cli/src/tl_cli/restore.py`
- `docs/tickets/P0-I7/provided/test_cli_restore.py.txt`
may explore: (none)

## Allowed paths
- `packages/tl-cli/src/tl_cli/restore.py` (edit)
- `packages/tl-cli/tests/test_cli_restore.py` (create: the provided file, unedited)
- `docs/reports/P0-I7/P0-I7-T04.md` (create: your report; commit it)

## Acceptance
```
cp docs/tickets/P0-I7/provided/test_cli_restore.py.txt packages/tl-cli/tests/test_cli_restore.py
uv run pytest packages/tl-cli/tests/test_cli_restore.py -q
just check
diff docs/tickets/P0-I7/provided/test_cli_restore.py.txt packages/tl-cli/tests/test_cli_restore.py
```
Expected: 7 passed (the Postgres test included when the cluster is up); `just check` clean; `diff` prints nothing.


## Tests to add
None beyond the provided file.

## Report requirements
Standard report (`docs/templates/haiku-report.md`), saved at `docs/reports/P0-I7/P0-I7-T04.md` and committed.

## Escalation triggers
- Stop and report *Blocked* if a provided test seems to contradict the specification above, or an interface above differs from the repo.

## Blocked
(implementer writes here)

## Decision
(supervisor or orchestrator writes here)
