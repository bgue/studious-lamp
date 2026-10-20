# P1-I6-T05b — The module's `/raise rfi` target for record threads

Status: ready
Tier: haiku
Labels: module, tests
Depends on: — (the target class, `targets()`, the entry point and the core `resolve_keys` are in the tree at the branch point)
Branch: `p1/i6-t05b-rfi-thread-target`

## Goal
`tl_mod_correspondence/dispatch.py` holds `RaiseRfiTarget` (the module's `/raise rfi`, which replaces the core placeholder), `targets()` (the entry point `throughline.dispatch_targets`) and one function that raises `NotImplementedError`: `plan_raise_rfi`. You implement it by its STEPS comment. It turns the parsed command line `/raise rfi [#KEY ...] <title>` into one `RaiseTechnical` planned command. One provided test file must pass.

## Brief references (pasted)
> **§18.14 record threads.** A line that starts with `/` in a record's thread is a command. `/raise <type> <title>` makes a record pre-linked to the thread (the engine adds the `dispatched_from` link). The target only *builds* commands: the planner (core) validates them with the command table, checks the person's access and dry-runs them.
>
> **ADR-0016 (confidentiality).** A key the person dispatching may not read is answered word for word as a key no record has (`unknown_key`). `resolve_keys(uow, scope, keys, actor=...)` already does this; use it with `actor=context.actor` and never read a record yourself.
>
> **What the core placeholder does** (for comparison, `tl_core/threads/targets/raise_record.py`): refuses an empty title (`missing_argument`, message `/raise record needs a title`), a title over 200 characters (`too_long`), resolves the `#KEY`s, and returns `first_problem(problems)` for any key problem.

## Interfaces (verbatim from repo at the branch point)
```python
# tl_core.integration.contract
class PlannedCommand(BaseModel):
    command_type: str
    command: dict[str, Any] = {}
    summary: str = ""        # at most 300 characters
class Problem(BaseModel):
    code: str                # [a-z][a-z0-9_]*
    message: str             # at most 500 characters

# tl_core.threads.contract
class RaiseArgs:             # parsed.args of /raise
    record_type: str
    against: list[str]       # the #KEYs
    text: str | None         # the title (first line, keys removed)
    note: str | None         # the lines after the first, or None
class DispatchContext:
    scope: str
    actor: str

# tl_core.threads.resolve
def resolve_keys(uow, scope, keys, *, actor=None) -> tuple[list[RecordRef], list[Problem]]
# tl_core.threads.targets
def first_problem(problems) -> Problem
# tl_mod_correspondence.limits
MAX_TEXT = 500
```

## Context (read these, nothing else)
- `packages/tl-modules/correspondence/src/tl_mod_correspondence/dispatch.py`
- `packages/tl-modules/correspondence/tests/test_dispatch.py` (you create it from the provided file, see below)
- `packages/tl-core/src/tl_core/threads/targets/raise_record.py` (the core target to mirror)
may explore: (none)

## Allowed paths
- `packages/tl-modules/correspondence/src/tl_mod_correspondence/dispatch.py` (edit `plan_raise_rfi` only)
- `packages/tl-modules/correspondence/tests/test_dispatch.py` (create: copy `docs/tickets/P1-I6/provided/t05b-test_dispatch.py.txt`, content unchanged)

## Steps
See the STEPS comment in `plan_raise_rfi`. Copy the provided test first and run it to see it fail.

## Acceptance
```
just check
uv run pytest packages/tl-modules/correspondence/tests/test_dispatch.py -q --adapters sqlite,postgres
```
Expected: all pass; `just check` exits 0.

## Tests to add
None beyond the provided file (it is the test).

## Report requirements
Standard report (`docs/templates/haiku-report.md`).

## Escalation triggers
- Stop and report *Blocked* if `resolve_keys` or `first_problem` is not importable as above, or the provided test needs a change to pass.

## Blocked
(implementer writes here)

## Decision
(supervisor or orchestrator writes here)
