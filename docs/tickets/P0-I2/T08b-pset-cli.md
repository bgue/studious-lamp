# P0-I2-T08b — `tl pset set|get`

Status: ready
Tier: haiku
Labels: cli
Depends on: P0-I2-T06, P0-I2-T08 (merged into the base of this branch)
Branch: `p0/i2a-t08b-pset-cli`

## Goal
`tl pset set` writes pset values to a record through `handle_set_pset_values`; `tl pset get` shows a record's psets, stored schema hash and live
conformance. The group, its options and `parse_assignment` already exist in `tl_cli/pset.py` and are registered in `main.py`; the two command bodies
raise `NotImplementedError`. After this ticket they work and a provided test file passes (18 tests).

## Brief references (pasted)
> **6.3** Values are stored as events (`Pset.ValuesSet`) recording the effective schema hash they were validated against, and projected into current-state tables. A pset value on a record is addressed by layer-aware paths: `psets.valve_data.size_in`, `psets.valve_data.x.fat_witness_by`, `psets.prj.shutdown_tie_in.window`.
> **27.5** Every current-state row carries `conformance` (`ok`, `warning`, `nonconformant`, `waived`) evaluated against the project's current effective schema, alongside the `effective_schema_hash` it was written under.
> Build spec 03 section 7 / AGENTS: the CLI contains no business logic. A subcommand parses options, makes one call, prints.

### Specification (the provided test checks it)
`--project ID` means scope `project:<ID>`; every command's `source` is `cli`; the database is `ctx.obj` (set by the root `--db` / `TL_DB`).

- `tl pset set --project ID KEY PSET ASSIGNMENT... [--layer standard|custom|project] [--actor A]`
  1. `values = dict(parse_assignment(a) for a in assignments)` (already written: `NAME=VALUE`, the value is JSON when it parses, so `4` is an int, `true` a bool, `null` unsets a value, anything else a string; a malformed assignment already exits 1).
  2. Inside `with _service_errors(), open_uow(db) as uow:` (one write unit of work): `current = get_record(uow, scope, key)`; if `None` call `_fail(f"no record with key {key!r} in project {project!r}")`. Then `handle_set_pset_values(uow, SetPsetValues(actor=actor, source="cli", scope=scope, stream_id=current["id"], expected_version=current["version"], pset=pset, layer=layer, values=values))`.
     A `--layer` value outside `standard|custom|project` must exit 1 with an `error:` line: pydantic rejects it inside `SetPsetValues(...)`, and `_service_errors` already turns that `ValidationError` into the error line. (`layer` is typed `str` in the signature; pass it through with `# pyright: ignore[reportArgumentType]` or `cast(Layer, layer)`.)
  3. Print three lines: `set <stream_id>`, `version <result.version>`, `conformance <result.events[0].payload['conformance']>`.
- `tl pset get --project ID KEY [PSET]`
  1. `with open_uow(db, readonly=True) as uow:` `row = get_record(uow, scope, key)`; `None` calls `_fail(...)` as above; `report = conformance(uow, row["id"])`.
  2. Print, in this order: `key: <row['key']>`, `version: <row['version']>`, `effective_schema_hash: <row['effective_schema_hash'] or '-'>`, `conformance: <report.status>`, then one line per issue `issue <level> <rule> <path> <message>`, then `psets: <canonical JSON>` of `row["psets"]` (the whole object) or, when `PSET` is given, of just that pset's section: use the existing helper `_section(row["psets"], pset)` (it returns `{}` for a missing section). Use `canonical_json` from `tl_core.ledger`.

Learnings that apply:
- Provided tests live under `docs/tickets/P0-I2/provided/*.py.txt` and are copied into the test tree by you. Do not edit the copied test.
- Typer commands with several `Argument`s: the order in the signature is the order on the command line (`KEY PSET ASSIGNMENT...`). `ruff` enforces 100 columns and import order (`uv run ruff check --fix` then `uv run ruff format`).
- `uv` prints "UV_NATIVE_TLS is deprecated" on every call; ignore it. If imports fail in a fresh worktree run `uv sync --all-packages`. Do not pipe `just check` into `tail`.

## Interfaces (verbatim from the repo at the branch point)
```python
# packages/tl-cli/src/tl_cli/pset.py (existing; replace the two `raise NotImplementedError  # P0-I2-T08b` lines, add imports)
def _fail(message: str) -> NoReturn; def _service_errors() -> context manager; def parse_assignment(text: str) -> tuple[str, Any]
def _section(psets: dict[str, Any], pset: str) -> Any
@app.command("set") def set_values(ctx, project, key, pset, assignments, layer="standard", actor=_DEFAULT_ACTOR) -> None
@app.command("get") def get_values(ctx, project, key, pset=None) -> None
```
```python
# imports to add
from pathlib import Path
from tl_adapters.sqlite.uow import open_uow
from tl_core.ledger import canonical_json
from tl_core.services.psets import SetPsetValues, conformance, handle_set_pset_values
from tl_core.services.queries import get_record      # (uow, scope, key) -> dict | None; keys: id, key, version, psets (dict), effective_schema_hash, conformance
# CommandResult: .stream_id, .version, .events (list[Event]; events[0].payload["conformance"])
# ConformanceReport: .status, .issues (each .level, .rule, .path, .message)
```

## Context (read these, nothing else)
- `AGENTS.md`
- `packages/tl-cli/src/tl_cli/pset.py`
- `packages/tl-cli/src/tl_cli/record.py` (the style of an existing group)
- `docs/tickets/P0-I2/provided/test_cli_pset.py.txt`
may explore: (none)

## Allowed paths
- `packages/tl-cli/src/tl_cli/pset.py` (edit: implement the two commands)
- `packages/tl-cli/tests/test_cli_pset.py` (create: `cp` of the provided file, byte for byte)

## Steps
1. `cp docs/tickets/P0-I2/provided/test_cli_pset.py.txt packages/tl-cli/tests/test_cli_pset.py`
2. Implement `set_values` and `get_values`.
3. Run the acceptance commands.

## Acceptance
```
uv run pytest packages/tl-cli/tests/test_cli_pset.py -q
just check
just test
diff docs/tickets/P0-I2/provided/test_cli_pset.py.txt packages/tl-cli/tests/test_cli_pset.py
```
Expected: 18 tests pass, `just check` and `just test` exit 0, `diff` prints nothing.

## Tests to add
None beyond the provided file.

## Report requirements
Standard report plus the decisive lines of the four acceptance commands.

## Escalation triggers
- Stop and report *Blocked* if a provided test contradicts the specification.
- Stop rather than change `main.py`, the services, or `record.py`.

## Blocked
(implementer writes here)

## Decision
(supervisor or orchestrator writes here)
