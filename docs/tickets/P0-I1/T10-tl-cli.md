# P0-I1-T10 — `tl` CLI

Status: draft (ready when T09 merges)
Tier: haiku
Labels: cli
Depends on: P0-I1-T09
Branch: `p0/i1-t10-tl-cli`

## Goal
A `tl` command (typer) that opens the dev ledger and calls service functions: `tl init`, `tl record create|show|void`,
`tl events tail`, `tl projections rebuild`. No business logic in the CLI; every subcommand is a thin call plus formatting.

## Brief references (pasted)
> Local developer bootstrap: `tl dev up` starts MinIO, creates the SQLite ledger … (§29.4) — `dev up` is a later ticket; `tl init` here only creates the ledger file and schema.
> Keep all business logic out of the TUI; TUI screens consume the same query/command contracts the web client will. (§16) — the same rule applies to the CLI.

## Interfaces (verbatim)
```python
# tl_core/services/commands.py (merged in T09)
class CreateRecord(Command): record_type: str; title: str; description: str | None = None; key: str | None = None; psets: dict[str, Any] = {}
class UpdateRecord(Command): stream_id: str; expected_version: int; changes: dict[str, Any]
class VoidRecord(Command): stream_id: str; expected_version: int; reason: str
def handle_create_record(uow, cmd) -> CommandResult
def handle_update_record(uow, cmd) -> CommandResult
def handle_void_record(uow, cmd) -> CommandResult
# tl_core/services/queries.py (merged in T11)
def get_record(uow, scope: str, key: str) -> dict | None
def list_records(uow, scope: str, *, status: str | None = None, include_voided: bool = False) -> list[dict]
# tl_adapters/sqlite/uow.py (merged in T07)
def open_uow(path: str) -> UnitOfWork          # context manager
def create_schema(path: str) -> None           # events table + all registered projector DDL
def rebuild_projections(path: str, *, types: list[str] | None = None) -> None
```
Common options: `--db PATH` (default `./dev/data/tl.db`, env `TL_DB`), `--project ID` (scope `project:<ID>`), `--actor` (default `user:dev`).
Source for every command is `cli`.

## Context (read these, nothing else)
- `AGENTS.md`
- `packages/tl-core/src/tl_core/services/commands.py`
- `packages/tl-core/src/tl_core/services/queries.py`
- `packages/tl-adapters/src/tl_adapters/sqlite/uow.py`
- `packages/tl-cli/src/tl_cli/__init__.py`

## Allowed paths
- `packages/tl-cli/src/tl_cli/main.py`, `record.py`, `events.py`, `projections.py` (create)
- `packages/tl-cli/pyproject.toml` (add `[project.scripts] tl = "tl_cli.main:app"`; dependency `rich` for tables)
- `packages/tl-cli/tests/test_cli_e2e.py` (create)

## Acceptance
```
just check
uv run pytest packages/tl-cli/tests/test_cli_e2e.py -q
uv run tl --help
```
Expected: e2e test passes; `--help` lists the five subcommand groups.

## Tests to add
- `test_cli_e2e.py` using `typer.testing.CliRunner` and a temp `--db`:
  - `init` creates the file and `events` table.
  - `record create --project P123 --key DEMO-0001 --title "First"` prints the stream id and version 1.
  - `record show --project P123 DEMO-0001` prints title, status, version.
  - `events tail --project P123 -n 1` prints one `Record.Created` line with a 64-hex hash.
  - `record void --project P123 DEMO-0001 --reason test` then `record show` prints `voided: true`.
  - `projections rebuild` exits 0 and `record show` output is unchanged.

## Report requirements
Standard report plus the `tl --help` output.

## Escalation triggers
- Stop if any of the interface signatures above differ from the repo; do not adapt them.
- Stop rather than implement numbering: `--key` is required in this increment.

## Blocked

## Decision
