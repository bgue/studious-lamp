# P0-I1-T10 — `tl` CLI

Status: draft (ready when T11 merges)
Tier: haiku
Labels: cli
Depends on: P0-I1-T09, P0-I1-T11
Branch: `p0/i1-t10-tl-cli`

## Goal
A `tl` command (typer) that opens the dev ledger and calls the service functions: `tl init`, `tl record create|show|void`,
`tl events tail`, `tl projections rebuild`. No business logic in the CLI: every subcommand parses options, makes one call, and prints.

## Brief references (pasted)
> Local developer bootstrap: `tl dev up` starts MinIO, creates the SQLite ledger ... (§29.4) — `dev up` is a later ticket; `tl init` here only creates the ledger file and schema.
> Keep all business logic out of the TUI; TUI screens consume the same query/command contracts the web client will. (§16) — the same rule applies to the CLI.

Learnings that apply:
- `uv` prints a harmless "UV_NATIVE_TLS is deprecated" warning on every call.
- `just check` runs pyright (standard mode for `tl_cli` and tests) over everything; `tl_cli` has no strict mode but keep annotations complete.
- Piping `just check` into `tail` hides its exit code; check `$?` or redirect to a file.
- `--key` is required: numbering does not exist yet. Do not implement it.

## Interfaces (verbatim, all merged)
```python
# tl_adapters/sqlite/uow.py
def open_uow(path, *, readonly: bool = False, registry=None, bus=None) -> ContextManager[SqliteUnitOfWork]   # one transaction; commit on normal exit
def create_schema(path, *, registry=None) -> None        # events table + every default projector's tables; idempotent
def rebuild_projections(path, *, types: Sequence[str] | None = None, registry=None, on_progress=None) -> int   # returns events replayed; types = projector names
# SqliteUnitOfWork.ledger.read_after(seq: int, *, scope: str | None = None, limit: int = 1000) -> list[Event]
# Event fields used: seq, recorded_at, event_type, stream_id, stream_version, hash (64 hex)

# tl_core/services/commands.py
class CreateRecord(Command): record_type: str; title: str; description: str | None = None; key: str | None = None; psets: dict[str, Any] = {}
class VoidRecord(Command): stream_id: str; expected_version: int; reason: str
#   Command fields: actor: str, source: str, scope: str ("project:<ID>"), correlation_id=None, causation_id=None, idempotency_key=None
class CommandResult(BaseModel): stream_id: str; key: str | None; version: int; events: list[Event]
# tl_core/services/records.py
def handle_create_record(uow, cmd: CreateRecord) -> CommandResult
def handle_void_record(uow, cmd: VoidRecord) -> CommandResult
# tl_core/services/errors.py: ServiceError (base) with subclasses KeyRequiredError, DuplicateKeyError, UnsupportedRecordTypeError,
#   RecordNotFoundError, RecordVoidedError, AlreadyVoidedError, NoChangesError, UnsupportedFieldError
# tl_core/ledger: ConcurrencyError
# tl_core/services/queries.py
def get_record(uow, scope: str, key: str) -> dict[str, Any] | None
#   keys: id, key, type, scope, title, description, status, psets (dict), voided (bool), version, last_seq, effective_schema_hash, conformance, created_at, updated_at
```

### Command line (exact)
Global option on the root app callback: `--db PATH` (env `TL_DB`, default `./dev/data/tl.db`). Per-command options below.
`--project ID` means scope `project:<ID>`; `--actor` defaults to `user:dev`; every command's `source` is `cli`.

| Command | Behaviour and output |
|---|---|
| `tl init` | Create the database's parent directory, then `create_schema(db)`. Print `initialised <db path>`. |
| `tl record create --project ID --key KEY --title TITLE [--description D] [--type core.Record] [--actor A]` | `with open_uow(db) as uow: handle_create_record(...)`. Print three lines: `created <stream_id>`, `key <key>`, `version <n>`. |
| `tl record show --project ID KEY` | `open_uow(db, readonly=True)`, `get_record`. Not found: error. Print one `name: value` line each for `id, key, type, scope, title, description, status, version, voided, conformance, created_at, updated_at`, then `psets: <canonical JSON>`; `voided` prints `true`/`false`; a None value prints `-`. |
| `tl record void --project ID KEY --reason R [--actor A]` | In one write unit of work: `get_record` (not found: error), then `handle_void_record` with the record's `id` and `version` as `expected_version`. Print `voided <stream_id>` and `version <n>`. |
| `tl events tail --project ID [-n N]` | Read the scope's events with `uow.ledger.read_after(seq, scope=..., limit=500)` in pages until empty, keep the last N (default 10), and print one line each: `<seq> <recorded_at isoformat> <event_type> <stream_id> v<stream_version> <hash>`. |
| `tl projections rebuild [--only NAME ...]` | `rebuild_projections(db, types=only or None)`. Print `replayed <n> events`. |

Errors: catch `ServiceError` and `ConcurrencyError` (and "record not found" for `show`/`void`) at the command level, print `error: <message>` to stderr, and exit with code 1. Do not catch anything else.

## Context (read these, nothing else)
- `AGENTS.md`
- `packages/tl-core/src/tl_core/services/commands.py`
- `packages/tl-core/src/tl_core/services/queries.py`
- `packages/tl-adapters/src/tl_adapters/sqlite/uow.py`
- `packages/tl-cli/src/tl_cli/__init__.py`
- `packages/tl-cli/pyproject.toml`

## Allowed paths
- `packages/tl-cli/src/tl_cli/main.py` (create: the typer `app`, the root callback with `--db`, `init`, and the `projections` group)
- `packages/tl-cli/src/tl_cli/record.py` (create: the `record` group)
- `packages/tl-cli/src/tl_cli/events.py` (create: the `events` group)
- `packages/tl-cli/pyproject.toml` (add only `[project.scripts]` with `tl = "tl_cli.main:app"`; no dependency changes)
- `packages/tl-cli/tests/test_cli_e2e.py` (create)

## Acceptance
```
just check
uv run pytest packages/tl-cli/tests/test_cli_e2e.py -q
uv run tl --help
```
Expected: the test passes; `--help` lists `init`, `record`, `events`, `projections`.

## Tests to add
`packages/tl-cli/tests/test_cli_e2e.py` using `typer.testing.CliRunner` and a temp database passed as `env={"TL_DB": str(tmp_path / "tl.db")}`:
- `init` creates the file (exit 0, output contains `initialised`) and a second `init` also exits 0.
- `record create --project P123 --key DEMO-0001 --title "First"` exits 0, prints `created `, `key DEMO-0001`, `version 1`.
- `record show --project P123 DEMO-0001` prints `title: First`, `version: 1`, `voided: false`, `status: -`.
- `events tail --project P123 -n 1` prints exactly one line containing `Record.Created` and a 64-hex hash (regex `\b[0-9a-f]{64}\b`).
- `record void --project P123 DEMO-0001 --reason test` exits 0, then `record show` prints `voided: true` and `version: 2`.
- `projections rebuild` exits 0 with `replayed 2 events`, and the `record show` output is identical before and after.
- Failures exit 1 with `error:` on stderr: creating `DEMO-0001` twice, `show` of an unknown key, `void` of an unknown key, and `void` twice.
- `create` without `--key` fails with a nonzero exit (typer's missing-option error).

## Report requirements
Standard report plus the `uv run tl --help` output and the demo sequence output.

## Escalation triggers
- Stop if any interface signature above differs from the repo; do not adapt it.
- Stop rather than implement numbering: `--key` is required in this increment.

## Blocked

## Decision
