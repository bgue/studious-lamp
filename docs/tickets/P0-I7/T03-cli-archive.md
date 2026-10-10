# P0-I7-T03 — `tl archive keygen|seal|verify`

Status: ready
Tier: haiku
Labels: cli
Depends on: P0-I7-S10 (`tl_core.archive`), P0-I7-T01 (`FsArchiveStore`), both merged into the base of this branch
Branch: `p0/i7a-t03-cli-archive`

## Goal
Three commands drive the ledger archive from the command line: create the signing key, seal new events into segments, and verify the archive (optionally against a database), printing the
first divergence. The group, its option aliases, `_fail`, `_target` and `_signer` exist in `packages/tl-cli/src/tl_cli/archive.py` and are registered in `main.py`; the three command bodies
raise `NotImplementedError`. A provided test file (12 tests) must pass. The commands contain no archive rules: they parse options, call `tl_core.archive` and `tl_adapters`, and print.

## Brief references (pasted)
> **24.3 Ledger archive:** sealed segments, NDJSON + Parquet, with a signed hash manifest continuing the hash chain, written to an independent location. A database-independent restore path.
> **24.5 Tampering suspicion:** hash-chain verification tool over the database and the archive. Reports the first divergence.
> **Fanout D2:** signing uses Ed25519; the dev key lives in `dev/data/` (git-ignored); production key custody is a later decision, not built here.

### Specification (the provided test checks it; all output via `typer.echo`, errors via `_fail`, which prints `error: <message>` to stderr and exits 1)
- `keygen` (`--key PATH`, `--force`): `signer = write_keypair(key, overwrite=force)`. A `FileExistsError` goes to `_fail(str(exc))`. On success print two lines:
  `wrote private key {key} (key id {signer.key_id})` and `wrote public key {public_key_path(key)}`.
- `seal` (`--archive DIR`, `--key PATH`, `--db TARGET`, `--max-events N`): `target = _target(ctx, db)` first, then `signer = _signer(key)`, then `store = FsArchiveStore(archive)`,
  `engine = make_engine(target)`. Loop: `with read_tx(engine) as conn: manifest = seal_segment(conn, store, signer, max_events=max_events)`; stop when it returns `None`. For each manifest print
  `sealed segment {segment_name(first_seq, last_seq)} ({event_count} events, seq {first_seq}..{last_seq})`. Turn `ArchiveError` into `_fail(str(exc))`; always `engine.dispose()` in a `finally`.
  After the loop, `summary = summarize_archive(store)` and print `sealed {n} segments; archive is at seq {summary.last_seq}` (always the word "segments"), or, when `n == 0`,
  `nothing new to seal; archive is at seq {summary.last_seq}`.
- `verify` (`--archive DIR`, `--public-key FILE`, `--db TARGET`, `--deep`, `--all`): fail with `no archive at {archive}` unless `archive.is_dir()` (do this before building a store: `FsArchiveStore` creates
  its directory). The public key path is `--public-key` or, when absent, `public_key_path(DEFAULT_KEY_PATH)`; `load_public_key` raising `FileNotFoundError` or `ValueError` goes to
  `_fail(f"cannot read the public key {path}: {exc}")`. If `--db` is a SQLite path (not `is_postgres`) that is not a file, `_fail(f"no ledger at {db}")`. Then call `verify_archive(store, public_key=..., deep=deep,
  stop_at_first=not all_issues)`, adding `conn=` from `with read_tx(make_engine(db)) as conn` when `--db` is given (dispose the engine). Turn `ArchiveError` into `_fail(str(exc))`.
  For each issue print `divergence: {kind} segment={segment or '-'} seq={seq or '-'}: {detail}` (use `-` only when `seq` is `None`; a seq of 0 does not occur) and exit with `raise typer.Exit(code=1)`; print
  nothing else on failure. With no issue: `summary = summarize_archive(store)`; print `verified {segments} segments, seq 1..{last_seq} ({events} events)`, or `verified 0 segments (the archive is empty)` when
  `segments == 0`; and when `--db` was given a second line `database {display_target(db)} agrees up to seq {last_seq}`.

Learnings that apply:
- Provided tests live under `docs/tickets/P0-I7/provided/*.py.txt`; copy the file into the test tree as named in *Acceptance* and do not edit it.
- Keep the stub's option declarations, helper names and command signatures. Remove the `STUB (P0-I7-T03)` sentence from the module docstring. Add back the imports you use.
- pyright flags a variable that is only assigned inside an `if`/`try` branch as possibly unbound; assign it in every path (for example `summary = summarize_archive(store) if not issues else None`).
- `CliRunner.invoke` catches exceptions and returns them on the result, so tests assert `exit_code` and `result.exception`; a clean `typer.Exit` shows up as `SystemExit`.
- ruff limits lines to 100 columns; run `uv run ruff format` before committing. `uv` prints "UV_NATIVE_TLS is deprecated"; ignore it. Do not pipe `just check` into `tail`.

## Interfaces (verbatim from the repo at the branch point)
```python
# tl_core.archive (importable from `tl_core.archive`)
def seal_segment(conn: Connection, store: ArchiveStore, signer: Signer, *, max_events: int = 10_000,
                 clock=...) -> SegmentManifest | None
def verify_archive(store: ArchiveStore, *, public_key: bytes, conn: Connection | None = None,
                   deep: bool = False, stop_at_first: bool = True) -> list[VerifyIssue]
def summarize_archive(store: ArchiveStore) -> ArchiveSummary   # .segments .events .last_seq .unsealed
def write_keypair(path: Path, *, overwrite: bool = False) -> Ed25519Signer   # .key_id; raises FileExistsError
def load_signer(path: Path) -> Ed25519Signer
def load_public_key(path: Path) -> bytes          # FileNotFoundError / ValueError
def public_key_path(private_path: Path) -> Path   # the .pub beside a private key
DEFAULT_KEY_PATH: Path
class ArchiveError(Exception): ...
class SegmentManifest(BaseModel):   # fields used here
    first_seq: int; last_seq: int; event_count: int
class VerifyIssue(BaseModel):
    kind: str; segment: str | None; seq: int | None; detail: str
# tl_core.archive.segments
def segment_name(first_seq: int, last_seq: int) -> str     # "000000000001-000000000004"
# tl_adapters
class FsArchiveStore:  # tl_adapters.archivestore ; FsArchiveStore(root) creates root
def make_engine(target) -> Engine; def read_tx(engine) -> ContextManager[Connection]   # tl_adapters.db
def is_postgres(target) -> bool; def display_target(target) -> str                    # tl_adapters.db
```
```python
# packages/tl-cli/src/tl_cli/archive.py: helpers that exist in the stub (keep them)
def _fail(message: str) -> NoReturn
def _target(ctx: typer.Context, db: str | None) -> DbTarget   # --db or the root --db; fails "no ledger at ..." for a missing SQLite file
def _signer(key: Path) -> Signer                              # load_signer; fails "no signing key at ...: run `tl archive keygen`"
```

## Context (read these, nothing else)
- `packages/tl-cli/src/tl_cli/archive.py`
- `docs/tickets/P0-I7/provided/test_cli_archive.py.txt`
may explore: (none)

## Allowed paths
- `packages/tl-cli/src/tl_cli/archive.py` (edit)
- `packages/tl-cli/tests/test_cli_archive.py` (create: the provided file, unedited)
- `docs/reports/P0-I7/P0-I7-T03.md` (create: your report; commit it)

## Acceptance
```
cp docs/tickets/P0-I7/provided/test_cli_archive.py.txt packages/tl-cli/tests/test_cli_archive.py
uv run pytest packages/tl-cli/tests/test_cli_archive.py -q
just check
diff docs/tickets/P0-I7/provided/test_cli_archive.py.txt packages/tl-cli/tests/test_cli_archive.py
```
Expected: 12 passed; `just check` clean; `diff` prints nothing.

## Tests to add
None beyond the provided file.

## Report requirements
Standard report (`docs/templates/haiku-report.md`), saved at `docs/reports/P0-I7/P0-I7-T03.md` and committed.

## Escalation triggers
- Stop and report *Blocked* if a provided test seems to contradict the specification above, or an interface above differs from the repo.

## Blocked
(implementer writes here)

## Decision
(supervisor or orchestrator writes here)
