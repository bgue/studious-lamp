# P1-I7-T10a — Dispatch targets: /link and /dispatch

Status: ready
Tier: haiku
Labels: core
Depends on: S1 and S2 (in the tree): `tl_core/threads/{contract,resolve,planner,engine}.py`, `targets/__init__.py` and the fixture `tests/threads/thread_world.py` (`run_target`, `planning_world`, `make_record`)
Branch: `p1/i7b-t10a-targets-link-action`

## Goal
Two verbs of a record thread become commands. `/link #KEY ... [as relation]` builds one `AddLink` from the thread's record to each key, and `/dispatch <action> name=value ... text` builds one `InvokeAction` on the thread's record. `targets/link.py` and `targets/dispatch_action.py` have the class, `verb`, `name` and imports; the body of each `plan` raises `NotImplementedError`. You implement them. One provided test file must pass.

## Brief references (pasted)
> **Brief 21.5, dispatch commands.** `/link <keys> [relation]` adds links. `/dispatch <request-type> [args]` creates a requisition or work order, or invokes a registered Action. "Each command is a ledgered command: permissions and validation apply. Side-effecting commands show a preview to confirm. Created items carry a `dispatched from` link to the message and the thread's record."
>
> **Grammar (parser, final).** `/link` takes every token before `as` as a key (`#` removed) and, after `as`, exactly one relation. `/dispatch` takes the request type or action name, then every unquoted `name=value` token as a parameter, and the words left over as `text` (`None` when none). A later line of the message is the `note`.
>
> **FANOUT D10, targets.** `link`: `AddLink` from the thread's record to each key (relation from `as`, else the vocabulary default). `dispatch`: `InvokeAction` (action = request type, target = the thread's record, parameters). Keys are looked up in the record's scope, then in `company`; a key that is not there is a problem, not an exception.
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
class DispatchArgs(_Args):
    verb: Literal["dispatch"] = "dispatch"
    request_type: str
    parameters: dict[str, str] = Field(default_factory=dict[str, str])
    text: str | None = None

class LinkArgs(_Args):
    verb: Literal["link"] = "link"
    keys: list[str] = Field(min_length=1, max_length=MAX_DISPATCH_KEYS)
    relation: str | None = None
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

`packages/tl-core/src/tl_core/integration/contract.py (InvokeAction, WS-A's model; the planner validates your command with it)` (read only):
```python
class InvokeAction(Command):
    action: str = Field(pattern=r"^[a-z][a-z0-9_-]{0,62}$")
    targets: list[str] = Field(default_factory=list[str], max_length=ACTION_MAX_TARGETS)
    parameters: dict[str, Any] = Field(default_factory=dict[str, Any])
```

## Context (read these, nothing else)
- `packages/tl-core/src/tl_core/threads/targets/link.py (the file you edit)`
- `packages/tl-core/src/tl_core/threads/targets/dispatch_action.py (the file you edit)`
- `packages/tl-core/src/tl_core/threads/targets/notify.py (a complete target, the same shape)`
- `packages/tl-core/src/tl_core/threads/resolve.py`
- `tests/threads/thread_world.py (the fixture the test uses)`
- `docs/tickets/P1-I7/provided/t10a-test_targets_link_action.py.txt (the test)`
may explore: (none)

Learnings that apply (pasted from `docs/memory/LEARNINGS.md` and the build's conventions):
- Environment: run everything from the repository root. A new worktree needs `uv sync --all-packages` once before `uv run` can import the workspace packages (L-P0-I6A-1). `uv` prints "UV_NATIVE_TLS is deprecated"; ignore it. Do not pipe `just check` into `tail`.
- ruff limits lines to 100 columns, docstrings and comments included (L-P0-I1-6). Run `uv run ruff format` before committing. pyright is `strict` for `tl-core`, and `just check` runs it on the whole tree.
- The provided test lives under `docs/tickets/P1-I7/provided/` as `.py.txt`; copy it into the tree byte for byte (the target name is in *Steps*). Do not edit the copy: it is already `ruff format` and pyright clean.
- Commit your report at `docs/reports/P1-I7/P1-I7-T10a.md` (it is inside your Allowed paths). Say "commit your report" in your final message (L-P0-I2-B7).
- A failing test that is not in your Allowed paths is not yours to fix: report it under *Blocked*.
- No new dependencies. When you implement the stub, remove the `STUB` paragraph from the module docstring, every `STEPS` comment, the `# ruff: noqa: F401` line and the `# pyright: reportUnusedImport=false, ...` line (L-P1-I3-3).
- Never change `schema/**` or anything under `generated/`. Never edit a file outside *Allowed paths*.
- Do not run `just test`, `just test-parity` or `just test-tui` (they take an hour); run the scoped commands in *Acceptance*. Other tests of `tests/threads/` exercise the same code (`test_planner.py`, `test_dispatch.py`); they are red until every ticket of the batch is merged and are not part of your acceptance.
- Tests that open a database use the `db` fixture of `tests/threads/conftest.py`, so they run once per adapter named by `--adapters` (default sqlite). `tests/threads/thread_world.py` holds the helpers; it is in the tree and read only (L-P1-I7B-1).

## Allowed paths
- `packages/tl-core/src/tl_core/threads/targets/link.py (edit)`
- `packages/tl-core/src/tl_core/threads/targets/dispatch_action.py (edit)`
- `tests/threads/test_targets_link_action.py (create; byte-identical copy of the provided test)`
- `docs/reports/P1-I7/P1-I7-T10a.md (create)`

## Lines you must not change
- The signature, decorator and docstring of every function and class in the stub file: you replace only the bodies that have a `STEPS` comment.
- The provided test: the copy in `tests/threads/` stays byte-identical to `docs/tickets/P1-I7/provided/t10a-test_targets_link_action.py.txt`.
- Everything under `tests/threads/` other than your copy, and `packages/tl-core/src/tl_core/threads/` other than the files in *Allowed paths* (the planner, the engine, `resolve.py`, `targets/__init__.py`).
- `InvokeAction` is WS-A's model and may not be in the tree yet: your command is a plain dict, and the test only checks the dict. Do not import it.

## Steps
- `packages/tl-core/src/tl_core/threads/targets/link.py` (edit)
- `packages/tl-core/src/tl_core/threads/targets/dispatch_action.py` (edit)
- `tests/threads/test_targets_link_action.py` (create)
- `docs/reports/P1-I7/P1-I7-T10a.md` (create)

1. `uv sync --all-packages`.
2. Copy `docs/tickets/P1-I7/provided/t10a-test_targets_link_action.py.txt` to `tests/threads/test_targets_link_action.py`.
3. Implement the two `plan` bodies by their STEPS comments; remove each STUB paragraph, the STEPS comments and the two lint-silencing lines.
4. Run the acceptance commands.

## Acceptance
```
just check
uv run pytest tests/threads/test_targets_link_action.py -q
```
Expected: `just check` clean; 8 pass.

## Tests to add
None beyond the provided file.

## Report requirements
Standard report (`docs/templates/haiku-report.md`). Put `Deviations` first (or "none") and list every file you changed.

## Escalation triggers
- Stop and report *Blocked* if a STEPS line and the provided test disagree, if the test needs a change in `resolve.py`, `thread_world.py` or any file outside *Allowed paths*, or if `InvokeAction` has to be imported.

## Blocked
(implementer writes here)

## Decision
(supervisor or orchestrator writes here)
