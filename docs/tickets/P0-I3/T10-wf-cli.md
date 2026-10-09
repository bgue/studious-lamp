# P0-I3-T10 — `tl wf show` and `tl wf transition`

Status: ready
Tier: haiku
Labels: cli
Depends on: P0-I3-T09 (merged into the base of this branch)
Branch: `p0/i3-t10-wf-cli`

## Goal
`tl wf show` prints a record's workflow state and, for each transition that starts there, whether its guards pass; `tl wf transition` runs one.
The group, its helpers (`_fail`, `_guard_line`, `_service_errors`), its options and its registration in `main.py` exist; the two command bodies in
`tl_cli/wf.py` raise `NotImplementedError`. A provided test file (12 tests) must pass.

## Brief references (pasted)
> **8 Workflow engine:** Declarative state machines per record type (states, transitions, guards, required psets, required links, approvers, signatures, notifications).
> **Build spec:** the CLI contains no business logic. A subcommand parses options, makes one call, prints.
> Roles are a stub: `--role R` (repeatable) lists the roles the caller claims; nothing verifies them until auth exists.

### Specification (the provided test checks it)
`--project ID` means scope `project:<ID>`; the database is `ctx.obj` (set by the root `--db` / `TL_DB`); every command's `source` is `cli`.
- `tl wf show --project ID KEY [--role R]...`: inside `with _service_errors(), open_uow(db, readonly=True) as uow:` find the record with `get_record(uow, scope, key)` (None: `_fail(f"no record with key {key!r} in project {project!r}")`), then `found = workflow_status(uow, row["id"], roles=tuple(role or ()))`. Print, in this order, one line each: `key: <found.key>`, `workflow: <found.workflow> v<found.workflow_version>`, `state: <found.state>`, `entered_at: <found.entered_at>`, `version: <found.version>`. Then for each `option` in `found.options`: `option <option.transition> -> <option.to_state> allowed` (or `blocked` when `option.allowed` is false), followed by `_guard_line(result)` for each `result` in `option.guards`.
- `tl wf transition --project ID KEY NAME [--role R]... [--reason TEXT] [--actor A]`: inside `with _service_errors(), open_uow(db) as uow:` find the record the same way, then `handle_transition_workflow(uow, TransitionWorkflow(actor=actor, source="cli", scope=scope, stream_id=current["id"], expected_version=current["version"], transition=name, actor_roles=list(role or ()), reason=reason))`. After the block print three lines: `transitioned <key> <payload['from_state']> -> <payload['to_state']>`, `version <result.version>`, `conformance <payload['conformance']>`, where `payload = result.events[0].payload`.
- A blocked transition needs no code from you: `_service_errors` already prints `error: ...` and the guard lines on stderr and exits 1. Do not change the helpers.

Learnings that apply:
- Provided tests live under `docs/tickets/P0-I3/provided/*.py.txt` and are copied into the test tree by you. Do not edit the copy.
- The two functions already have their final signatures (options and arguments in the order above); keep them.
- The stub had its unused imports removed; add back what you use (`Path`, `open_uow`, `get_record`, `workflow_status`, `TransitionWorkflow`, `handle_transition_workflow`, `typer.Option`).
- ruff limits lines to 100 columns; run `uv run ruff format` before committing. `uv` prints "UV_NATIVE_TLS is deprecated"; ignore it. Do not pipe `just check` into `tail`.
- Remove the `STUB (P0-I3-T10)` paragraph from the module docstring when you are done.

## Interfaces (verbatim from the repo at the branch point)
```python
# packages/tl-cli/src/tl_cli/wf.py (existing stub): app = typer.Typer(...); _DEFAULT_ACTOR = "user:dev"
def _fail(message: str) -> NoReturn            # prints "error: ..." to stderr, exits 1
def _guard_line(result: GuardResult) -> str    # "  guard <kind> ok|FAILED <message>"
def _service_errors() -> context manager       # GuardFailedError -> error line + guard lines on stderr, exit 1; other service errors -> error line, exit 1
@app.command("show") def show(...) -> None; @app.command("transition") def transition(...) -> None     # bodies are the ticket
```
```python
# existing, import and use
from tl_adapters.sqlite.uow import open_uow                 # open_uow(path, readonly=False) -> context manager yielding a unit of work
from tl_core.services.queries import get_record             # (uow, scope, key) -> dict | None; keys id, key, version
from tl_core.services.workflow import TransitionWorkflow, handle_transition_workflow, workflow_status
# workflow_status(uow, record_id, *, roles: tuple[str, ...] = ()) -> WorkflowStatus
#   .key .workflow .workflow_version .state .entered_at .version .options: list[TransitionOption]
#   TransitionOption: .transition .to_state .allowed .guards: list[GuardResult]
# TransitionWorkflow(Command): stream_id, expected_version, transition, actor_roles: list[str] = [], reason: str | None = None
# handle_transition_workflow(uow, cmd) -> CommandResult (.version, .events[0].payload with from_state, to_state, conformance)
```

## Context (read these, nothing else)
- `AGENTS.md`
- `packages/tl-cli/src/tl_cli/wf.py`
- `packages/tl-cli/src/tl_cli/pset.py` (style of a group with `set` and `get`)
- `docs/tickets/P0-I3/provided/test_cli_wf.py.txt`
may explore: (none)

## Allowed paths
- `packages/tl-cli/src/tl_cli/wf.py` (edit)
- `packages/tl-cli/tests/test_cli_wf.py` (create: byte-for-byte copy of the provided file)
- `docs/reports/P0-I3/P0-I3-T10.md` (create: your report; commit it)

## Steps
1. `cp docs/tickets/P0-I3/provided/test_cli_wf.py.txt packages/tl-cli/tests/test_cli_wf.py`
2. Implement `show` and `transition`; delete the STUB paragraph.
3. Run the acceptance commands, write the report, commit both.

## Acceptance
```
uv run pytest packages/tl-cli/tests/test_cli_wf.py -q
just check
just test
diff docs/tickets/P0-I3/provided/test_cli_wf.py.txt packages/tl-cli/tests/test_cli_wf.py
```
Expected: 12 tests pass, `just check` and `just test` exit 0, `diff` prints nothing.

## Tests to add
None beyond the provided file.

## Report requirements
Standard report plus the decisive lines of the four acceptance commands. Commit the report file.

## Escalation triggers
- Stop and report *Blocked* if a provided test contradicts the specification.
- Stop rather than change `main.py`, the services or any other file.

## Blocked
(implementer writes here)

## Decision
(supervisor or orchestrator writes here)
