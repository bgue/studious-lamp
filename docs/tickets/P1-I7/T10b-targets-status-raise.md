# P1-I7-T10b — Dispatch targets: /status and /raise record

Status: merged
Tier: haiku
Labels: core
Depends on: S1 and S2 (in the tree): `tl_core/threads/{contract,resolve,planner,engine}.py`, `targets/__init__.py`, the workflow engine, and the fixture `tests/threads/thread_world.py` (`run_target`, `planning_world` with its one workflow `t.thread`, `make_record`)
Branch: `p1/i7b-t10b-targets-status-raise`

## Goal
Two more verbs become commands. `/status <state> [reason]` builds a `TransitionWorkflow` on the thread's record, and `/raise record <title> [#KEY ...]` builds a `CreateRecord` plus one `raised_against` `AddLink` for each target. `targets/status.py` and `targets/raise_record.py` have the class, `verb`, `name`, imports and (for raise) `MAX_TITLE_CHARS`; the body of each `plan` raises `NotImplementedError`. You implement them. One provided test file must pass.

## Brief references (pasted)
> **Brief 21.5.** `/status <transition>`: workflow transition (guards and signatures apply). `/raise <type> [against] [text]`: create a deficiency, NCR, RFI, constraint or inspection request, pre-linked. "Created items carry a `dispatched from` link to the message and the thread's record" (the engine adds that link; you do not).
>
> **Grammar (parser, final).** `/status` takes the target state as one token and the words left over as the reason (`text`, `None` when none). `/raise` takes the record type alias as one token, every `#KEY` as a target (`against`, `#` removed) and the words left over as `text`; a later line of the message is the `note`.
>
> **FANOUT D10, targets.** `status`: `TransitionWorkflow` on the thread's record; guards apply when it runs (the dry run shows a failed guard); no roles are ever supplied by a target. `raise` with the alias `record`: `CreateRecord` of `core.Record` (title from the text), `raised_against` links to the `#KEY` targets. Phase 1 has no other alias (`rfi` waits for P1-I6).
>
> > **How the planner uses a target (ADR-0018, `tl_core/threads/planner.py`).** A target only *builds* commands. The planner then sets `access` from the command runner and `permitted` from the caller's `holds` (a target cannot grant itself access), refuses a command that names `actor`, `source`, `scope`, `correlation_id`, `causation_id`, `idempotency_key` or `by_module`, validates every command with its pydantic model, and dry-runs the whole plan in a unit of work that is rolled back. So a target returns `PlannedCommand(command_type=..., command={...}, summary=...)` and leaves `access`, `permitted` and `problem` at their defaults. It returns one `Problem` (not an exception) for a line it cannot plan. The exact string `"$result:<n>"` in a command is replaced by the stream id that item `n` produced.

## Interfaces (verbatim from the repo at the branch point)
`packages/tl-core/src/tl_core/threads/contract.py` (read only):
```python
class DispatchTarget(Protocol):
    """Maps one verb to existing commands for one record type or alias (FANOUT D10).

    ``name`` is the alias for ``raise`` (``rfi``, ``record``) or the action name space for
    ``dispatch`` (``*``), and the record type for the other verbs (``documents.Revision``), or
    ``*`` for the core default. The most specific name wins. A target only builds commands; the
    planner validates them with the runner's models, checks each one's access against ``holds``
    and dry-runs them in a unit of work that is rolled back.
    """

    verb: DispatchVerb
    name: str

    def plan(
        self, uow: UnitOfWork, context: DispatchContext, parsed: ParsedDispatch
    ) -> list[PlannedCommand] | Problem: ...
```

`packages/tl-core/src/tl_core/threads/contract.py` (read only):
```python
class DispatchContext(BaseModel):
    """What a dispatch target is told: the thread's record and who is dispatching."""

    record: RecordRef
    record_status: str | None = None
    scope: str
    actor: str
    #: ISO date and instant of the server, for ``/due`` and ``/remind``.
    today: str
    now: str
```

`packages/tl-core/src/tl_core/threads/contract.py` (read only):
```python
class RaiseArgs(_Args):
    verb: Literal["raise"] = "raise"
    record_type: str
    against: list[str] = Field(default_factory=list[str], max_length=MAX_DISPATCH_KEYS)
    text: str | None = None

class StatusArgs(_Args):
    verb: Literal["status"] = "status"
    target: str
    text: str | None = None
```

`packages/tl-core/src/tl_core/integration/contract.py` (read only):
```python
class PlannedCommand(BaseModel):
    """One command that automation or a dispatch would run, as a preview shows it.

    ``command`` holds the fields of the command model except ``actor`` (which the runner sets).
    ``access`` is what the command needs (``None``: nothing declares it, so it is refused);
    ``permitted`` says whether the actor that would run it holds that access. ``problem`` is set
    when the command would be refused (validation, access, a missing record, a stale state).
    """

    command_type: str
    command: dict[str, Any] = Field(default_factory=dict[str, Any])
    access: Access | None = None
    permitted: bool = False
    summary: str = Field(default="", max_length=MAX_SUMMARY_CHARS)
    problem: Problem | None = None

class Problem(BaseModel):
    """A refusal or a failure: a short fixed code and words for a person (no paths, no traces)."""

    code: str = Field(pattern=r"^[a-z][a-z0-9_]{0,63}$")
    message: str = Field(max_length=MAX_MESSAGE_CHARS)
```

`packages/tl-core/src/tl_core/workflow/definition.py` (read only):
```python
class StateDef(_Model):
    name: str = Field(min_length=1)
    label: str | None = None


class TransitionDef(_Model):
    name: str = Field(min_length=1)
    from_states: list[str] = Field(alias="from")
    to: str = Field(min_length=1)
    label: str | None = None
    guards: list[Guard] = []

    def transition(self, name: str) -> TransitionDef | None:
        """The transition with this name, or ``None``."""
        return next((t for t in self.transitions if t.name == name), None)

    def transitions_from(self, state: str) -> list[TransitionDef]:
        """Transitions that can start in ``state``, in declaration order."""
        return [t for t in self.transitions if state in t.from_states]
```

`packages/tl-core/src/tl_core/workflow/provider.py` (read only):
```python
def get_workflows() -> WorkflowRegistry: ...

# WorkflowRegistry.find(record_type: str, scope: str) -> WorkflowDefinition | None
```

`packages/tl-core/src/tl_core/threads/resolve.py` (read only):
```python
def resolve_keys(
    uow: UnitOfWork, scope: str, keys: list[str]
    ...
```

`packages/tl-core/src/tl_core/threads/targets/__init__.py` (read only):
```python
def first_problem(problems: Iterable[Problem]) -> Problem:
    """One problem standing for several: the first code, every message."""
    items = list(problems)
    message = "; ".join(p.message for p in items)[:480]
    return Problem(code=items[0].code, message=message)
```

## Context (read these, nothing else)
- `packages/tl-core/src/tl_core/threads/targets/status.py (the file you edit)`
- `packages/tl-core/src/tl_core/threads/targets/raise_record.py (the file you edit)`
- `packages/tl-core/src/tl_core/threads/targets/notify.py (a complete target, the same shape)`
- `packages/tl-core/src/tl_core/threads/resolve.py`
- `tests/threads/thread_world.py (the fixture the test uses, with its workflow `FLOW`)`
- `docs/tickets/P1-I7/provided/t10b-test_targets_status_raise.py.txt (the test)`
may explore: (none)

Learnings that apply (pasted from `docs/memory/LEARNINGS.md` and the build's conventions):
- Environment: run everything from the repository root. A new worktree needs `uv sync --all-packages` once before `uv run` can import the workspace packages (L-P0-I6A-1). `uv` prints "UV_NATIVE_TLS is deprecated"; ignore it. Do not pipe `just check` into `tail`.
- ruff limits lines to 100 columns, docstrings and comments included (L-P0-I1-6). Run `uv run ruff format` before committing. pyright is `strict` for `tl-core`, and `just check` runs it on the whole tree.
- The provided test lives under `docs/tickets/P1-I7/provided/` as `.py.txt`; copy it into the tree byte for byte (the target name is in *Steps*). Do not edit the copy: it is already `ruff format` and pyright clean.
- Commit your report at `docs/reports/P1-I7/P1-I7-T10b.md` (it is inside your Allowed paths). Say "commit your report" in your final message (L-P0-I2-B7).
- A failing test that is not in your Allowed paths is not yours to fix: report it under *Blocked*.
- No new dependencies. When you implement the stub, remove the `STUB` paragraph from the module docstring, every `STEPS` comment, the `# ruff: noqa: F401` line and the `# pyright: reportUnusedImport=false, ...` line (L-P1-I3-3).
- Never change `schema/**` or anything under `generated/`. Never edit a file outside *Allowed paths*.
- Do not run `just test`, `just test-parity` or `just test-tui` (they take an hour); run the scoped commands in *Acceptance*. Other tests of `tests/threads/` exercise the same code (`test_planner.py`, `test_dispatch.py`); they are red until every ticket of the batch is merged and are not part of your acceptance.
- Tests that open a database use the `db` fixture of `tests/threads/conftest.py`, so they run once per adapter named by `--adapters` (default sqlite). `tests/threads/thread_world.py` holds the helpers; it is in the tree and read only (L-P1-I7B-1).

## Allowed paths
- `packages/tl-core/src/tl_core/threads/targets/status.py (edit)`
- `packages/tl-core/src/tl_core/threads/targets/raise_record.py (edit)`
- `tests/threads/test_targets_status_raise.py (create; byte-identical copy of the provided test)`
- `docs/reports/P1-I7/P1-I7-T10b.md (create)`

## Lines you must not change
- The signature, decorator and docstring of every function and class in the stub file: you replace only the bodies that have a `STEPS` comment.
- The provided test: the copy in `tests/threads/` stays byte-identical to `docs/tickets/P1-I7/provided/t10b-test_targets_status_raise.py.txt`.
- Everything under `tests/threads/` other than your copy, and `packages/tl-core/src/tl_core/threads/` other than the files in *Allowed paths* (the planner, the engine, `resolve.py`, `targets/__init__.py`).
- `MAX_TITLE_CHARS` in `raise_record.py`.

## Steps
- `packages/tl-core/src/tl_core/threads/targets/status.py` (edit)
- `packages/tl-core/src/tl_core/threads/targets/raise_record.py` (edit)
- `tests/threads/test_targets_status_raise.py` (create)
- `docs/reports/P1-I7/P1-I7-T10b.md` (create)

1. `uv sync --all-packages`.
2. Copy `docs/tickets/P1-I7/provided/t10b-test_targets_status_raise.py.txt` to `tests/threads/test_targets_status_raise.py`.
3. Implement the two `plan` bodies by their STEPS comments; remove each STUB paragraph, the STEPS comments and the two lint-silencing lines.
4. Run the acceptance commands.

## Acceptance
```
just check
uv run pytest tests/threads/test_targets_status_raise.py -q
```
Expected: `just check` clean; 11 pass.

## Tests to add
None beyond the provided file.

## Report requirements
Standard report (`docs/templates/haiku-report.md`). Put `Deviations` first (or "none") and list every file you changed.

## Escalation triggers
- Stop and report *Blocked* if a STEPS line and the provided test disagree, if the test needs a change in `thread_world.py`, the workflow engine or any file outside *Allowed paths*, or if you think a target should pass workflow roles (it must not: ADR-0018 item 12).

## Blocked
(implementer writes here)

## Decision
(supervisor or orchestrator writes here)
