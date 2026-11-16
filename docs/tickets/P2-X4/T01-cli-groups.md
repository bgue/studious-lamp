# P2-X4-T01 — CLI groups from the module hook

Status: ready
Tier: haiku
review: full
Labels: cli, tests
Depends on: S1 merged (C1). Disjoint from S2 and S3.
Branch: `p2/x4-t01-cli-groups`
Worktree: `/home/user/wt/x4/t01`

## Goal
`tl_cli/main.py` adds every module's CLI group from `ModuleSpec.cli_groups` in a loop instead of one hand-written `app.add_typer` line per
module. The registered top-level group names and their order do not change except where noted. A new module's group appears with no edit
to `main.py`.

## Brief references (pasted, abridged)
`ModuleSpec.cli_groups` is a sequence of refs `"tl_cli.<mod>:<attr>"` naming a `typer.Typer`. Typer apps in this repo carry no name, the
name is given at `add_typer`. Name rule (one helper, `_group_name(ref)`): attr `app` gives the module part of the ref (`tl_cli.corr:app`
is `corr`); attr `<x>_app` gives `<x>` (`tl_cli.req:wo_app` is `wo`). Anything else: raise `ValueError` naming the module only.
Refs per module (from `docs/reports/P2-X4/S1.md`): awp `awp`; correspondence `corr rfi comm`; cost `cost`; documents `doc derive
transmittal review`; engineering `tag`; legacy `load`; materials `mat`; quality `punch`; requisitions `req`, `wo`; schedule `xer`.
schemareg: none.

## Interfaces (verbatim)
```python
# packages/tl-core/src/tl_core/modules.py (p2/x4)
def resolve_hook(spec: ModuleSpec, kind: str) -> tuple[object, ...]: ...   # kind "cli_groups" gives the Typer objects, in ref order
class ModuleHookError(ModuleLoadError): ...                                 # fixed text, no ref
def load_modules() -> tuple[ModuleSpec, ...]: ...                           # module-name order
```
```python
# packages/tl-cli/src/tl_cli/main.py today (abridged): the module lines to replace, between `thread` and `constraint`/`transmittal`
app.add_typer(tag.app, name="tag")  app.add_typer(doc.app, name="doc")  app.add_typer(derive.app, name="derive")
app.add_typer(xer.app, name="xer")  app.add_typer(load.app, name="load")  app.add_typer(cost.app, name="cost")
app.add_typer(awp.app, name="awp")  app.add_typer(transmittal.app, name="transmittal")  app.add_typer(review.app, name="review")
app.add_typer(corr.app, name="corr")  app.add_typer(rfi.app, name="rfi")  app.add_typer(comm.app, name="comm")
app.add_typer(mat.app, name="mat")  app.add_typer(punch.app, name="punch")
app.add_typer(req.app, name="req")  app.add_typer(req.wo_app, name="wo")
```
(one per line in the file). Lines that stay: every `corr.app.add_typer(...)`, `doc.app.add_typer(...)`, `doc.app.command(...)`,
`tag.app.add_typer(...)`, `tag.app.command(...)`, `thread...`, `constraint`, and `app.command("evidence")(...)`: they decorate the module
apps and still need those module imports; keep exactly the imports they use, drop the imports that become unused (lint decides).

## Context (read these, nothing else)
- `packages/tl-cli/src/tl_cli/main.py`
- `packages/tl-core/src/tl_core/modules.py` (the S1 block at the end: `resolve_hook`, `ModuleHookError`)
- `packages/tl-cli/tests/test_cli_domains.py` (how a test drives `app`)
- `docs/reports/P2-X4/S1.md`
- `docs/templates/haiku-report.md`
may explore: (none)

## Allowed paths
- `packages/tl-cli/src/tl_cli/main.py`
- `packages/tl-cli/tests/test_module_cli_groups.py` (create)
- `docs/reports/P2-X4/T01.md` (create)
Everything else is read-only (`tl_cli/new*.py` and the scaffold belong to T02; `packages/tl-core/**` to S1, merged).

## Steps
1. BEFORE editing `main.py`, write the test's `OLD_GROUPS` literal: the ordered list of top-level group names of `app` taken from
   `[g.name for g in app.registered_groups]` (and the `corr`, `doc`, `tag` sub-group names, same way). Run the test file once: it passes.
2. Replace the module `add_typer` lines by one loop placed where the first of them stood:
   `for spec in load_modules(): for sub, group in zip(names, resolve_hook(spec, "cli_groups"))` with names from `_group_name` over
   `spec.cli_groups`; `app.add_typer(group, name=name)`. Resolve each spec once. Catch `ModuleHookError` per module: skip its groups
   and `typer.echo(str(exc), err=True)` only when the command line is not `--help`/completion (keep it simple: log via `logging`,
   WARNING, logger `tl_cli`). Other modules still register.
3. Keep the order of groups as close as the hook allows. Group order in `tl --help` may change; the SET of names may not; say in the
   report whether the order of `OLD_GROUPS` still holds.
4. Run the acceptance commands, paste the summaries.

## Acceptance
```
NODE_OPTIONS=--max-old-space-size=6144 just check
just gate packages/tl-cli/tests/test_module_cli_groups.py packages/tl-cli/tests/test_cli_domains.py packages/tl-cli/tests/test_cli_corr.py packages/tl-cli/tests/test_cli_awp.py packages/tl-cli/tests/test_req_read.py packages/tl-cli/tests/test_req_write.py packages/tl-cli/tests/test_cli_cost.py packages/tl-cli/tests/test_cli_new_module.py packages/tl-cli/tests/test_cli_extypes_help.py tests/services/test_module_hooks.py
```
`test_module_cli_groups.py` is created by this ticket; every other path exists on `p2/x4` (checked with `ls`). Expected: all pass. Name
files, never a directory.

## Tests to add (`packages/tl-cli/tests/test_module_cli_groups.py`)
- `OLD_GROUPS` equality: the set of top-level group names equals the literal captured before the change, and the `corr`, `doc`, `tag`
  sub-group names are unchanged.
- `_group_name`: `tl_cli.corr:app` is `corr`, `tl_cli.req:wo_app` is `wo`, `tl_cli.x:thing` raises `ValueError`.
- Every installed module's `cli_groups` resolve to `typer.Typer` objects.
- A module through `use_modules` whose hook names a missing object: its groups absent, the others present, no ref text in the message.

## Report requirements
Standard report (`docs/templates/haiku-report.md`) plus: the before/after group order in one line each; the `_group_name` rule used.

## Escalation triggers
Stop and report *Blocked* if: a group cannot be reached by the name rule; keeping the set equal needs a change outside Allowed paths; a
test outside Allowed paths pins the old group order.

## Blocked
(implementer writes here)

## Decision
(supervisor or orchestrator writes here)
