# P0-I7-T20 — `tl lake` commands

Status: ready
Tier: haiku
Labels: cli
Depends on: P0-I7-S1, S2, S3 (the `tl_lake` service functions, merged into the base of this branch)
Branch: `p0/i7b-t20-lake-cli`

## Goal
`tl lake sync|rebuild|status|tables|query` work from the command line. The group, the `--lake-dir` option, the helpers (`_fail`, `_config`, `_ledger_snapshot`,
`_lake_errors`) and the registration in `main.py` exist; the five commands in `packages/tl-cli/src/tl_cli/lake.py` raise `NotImplementedError`. A provided
test file (14 tests) must pass.

## Brief references (pasted)
> **28.3 Sync and consistency:** `tl lake sync` runs incrementally. It reads events after the last synced `seq`, updates silver, and commits as one DuckLake snapshot. Every lake snapshot records the ledger `seq` range it covers. Reports built on the lake state "data as of seq 48,211,933" and are reproducible with DuckLake time travel. Full rebuild = replay the ledger into a new lake.
> **28.4 Uses:** agents get a read-only `lake_query` MCP tool (SQL with row limits, allowed catalogs only, logged).
> **Build spec:** the CLI contains no business logic. A subcommand parses options, makes one call, prints.

### Specification (the provided test checks it)
The database is `ctx.obj` (root `--db` / `TL_DB`). The lake directory is in `ctx.meta["lake_config"]`; use `_config(ctx)`. Wrap each command body in
`with _lake_errors():`, which turns a guard refusal into `error: refused: <why>` and any other lake error into `error: <message>`, both exit 1. Print with `typer.echo`.

- `sync`: `with _lake_errors(), _ledger_snapshot(ctx) as conn: result = sync_lake(_config(ctx), conn)`. If `result.up_to_date` print
  `lake is up to date as of seq <result.last_seq>`. Otherwise print two lines: `synced seq <first_seq>..<last_seq> (<events> events) in snapshot <snapshot_id>` and
  `silver rows: ` followed by `<table> <count>` for each item of `result.silver_rows`, in its own order, joined by `, `.
  (`rebuild` prints exactly the same two lines.)
- `rebuild`: without `--yes`, `_fail("rebuild deletes the lake's catalog and data files; pass --yes to continue")`. With it, the same as `sync` but call
  `sync_lake(_config(ctx), conn, rebuild=True)`.
- `status`: `status = lake_status(_config(ctx))`. If `not status.initialised` print ``lake not initialised: run `tl lake sync` `` (with the backticks, no trailing
  space). A lake that exists but was never synced (`status.snapshot_id is None`) prints the same line. Otherwise print
  `as of seq <as_of_seq> (snapshot <snapshot_id>, synced <synced_at>)` using `synced_at.isoformat(sep=" ", timespec="seconds")`, then `syncs <syncs>`, then one line
  `<table> <rows>` per entry of `status.tables` sorted by table name.
- `tables`: `for name, columns in describe_lake(_config(ctx)).items()` sorted by name: print `name`, then `  <column> <TYPE>` (two spaces) for each column in order.
- `query`: `result = LakeQueryService(_config(ctx)).query(sql, limit=limit, caller="cli")` (the constant `_CALLER` holds the string). With `--json` print
  `json.dumps({"columns": result.columns, "rows": result.rows, "truncated": result.truncated, "limit": result.limit, "as_of_seq": result.as_of_seq,
  "snapshot_id": result.snapshot_id})` and nothing else. Otherwise print the header `" | ".join(columns)`, one line per row with the values joined by ` | ` (`None` is
  printed as `NULL`, everything else with `str`), then, only when `result.truncated`, `truncated at <limit> rows`, then `result.as_of_line()`.
- A query that is refused prints nothing on stdout (the provided test checks `stdout == ""`), so build all output before printing.

Learnings that apply:
- Provided tests live under `docs/tickets/P0-I7/provided/*.py.txt` and are copied into the test tree by you. Do not edit the copy.
- Keep the stub's function signatures and option declarations. Remove the `STUB (P0-I7-T20)` paragraph from the module docstring when you are done.
- ruff limits lines to 100 columns; run `uv run ruff format` before committing. `uv` prints "UV_NATIVE_TLS is deprecated"; ignore it. Do not pipe `just check` into `tail`.
- Add back the imports you use (`json`, `sync_lake`, `lake_status`, `describe_lake`, `LakeQueryService`); the stub imports only what it uses.
- Each lake operation opens a DuckDB catalog and takes about half a second; the provided tests take a minute or two in total. That is normal.

## Interfaces (verbatim from the repo at the branch point)
```python
# packages/tl-lake/src/tl_lake/__init__.py (all importable from `tl_lake`)
def sync_lake(config: LakeConfig, ledger: Connection, *, rebuild: bool = False, ...) -> SyncResult
@dataclass(frozen=True)
class SyncResult:
    snapshot_id: int | None      # None: the lake was already up to date
    first_seq: int | None
    last_seq: int
    events: int
    silver_rows: Mapping[str, int]   # lake table -> rows written
    @property
    def up_to_date(self) -> bool
def lake_status(config: LakeConfig) -> LakeStatus
@dataclass(frozen=True)
class LakeStatus:
    initialised: bool
    as_of_seq: int = 0
    snapshot_id: int | None = None
    synced_at: datetime | None = None
    syncs: int = 0
    tables: dict[str, int] = {}      # table -> row count (the _tl_sync watermark table is not listed)
def describe_lake(config: LakeConfig) -> dict[str, list[tuple[str, str]]]   # table -> [(column, type)]
class LakeQueryService:
    def __init__(self, config: LakeConfig, ...) -> None
    def query(self, sql: str, *, limit: int | None = None, caller: str = "unknown") -> LakeQueryResult
@dataclass(frozen=True)
class LakeQueryResult:
    columns: list[str]; rows: list[list[Any]]   # JSON-safe values
    truncated: bool; limit: int; as_of_seq: int; snapshot_id: int | None; elapsed_ms: float
    def as_of_line(self) -> str                 # "as of seq 12 (snapshot 3)"
# errors: GuardError (a refusal), LakeError (everything else, incl. QueryError, LakeNotInitialisedError)
```

## Context (read these, nothing else)
- `AGENTS.md`
- `packages/tl-cli/src/tl_cli/lake.py`
- `packages/tl-cli/src/tl_cli/link.py` (the same shape of group, finished)
- `docs/tickets/P0-I7/provided/test_cli_lake.py.txt`
may explore: (none)

## Allowed paths
- `packages/tl-cli/src/tl_cli/lake.py` (edit)
- `packages/tl-cli/tests/test_cli_lake.py` (create: byte-for-byte copy of the provided file)
- `packages/tl-cli/README.md` (edit: add the five `tl lake` rows to *Public interface*, one line each, in the same style)
- `docs/reports/P0-I7/P0-I7-T20.md` (create: your report; commit it)

## Steps
1. `cp docs/tickets/P0-I7/provided/test_cli_lake.py.txt packages/tl-cli/tests/test_cli_lake.py`
2. Implement the five commands; delete the STUB paragraph.
3. Add the README rows. Run the acceptance commands, write the report, commit everything.

## Acceptance
```
uv run pytest packages/tl-cli/tests/test_cli_lake.py -q
just check
just test
diff docs/tickets/P0-I7/provided/test_cli_lake.py.txt packages/tl-cli/tests/test_cli_lake.py
```
Expected: 14 tests pass, `just check` and `just test` exit 0, `diff` prints nothing.

## Tests to add
None beyond the provided file.

## Report requirements
Standard report plus the decisive lines of the four acceptance commands. Commit the report file.

## Escalation triggers
- Stop and report *Blocked* if a provided test contradicts the specification.
- Stop rather than change `main.py`, `tl_lake`, or any other file.

## Blocked
(implementer writes here)

## Decision
(supervisor or orchestrator writes here)
