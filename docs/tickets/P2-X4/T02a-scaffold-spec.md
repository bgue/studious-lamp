# P2-X4-T02a — `tl new module` emits a spec, the commands hook and the entry point

Status: ready
Tier: haiku
review: full
Labels: cli, tests
Depends on: S1 merged (C1). Disjoint from S4 (tl-cli only).
Branch: `p2/x4-t02a-scaffold-spec`
Worktree: `/home/user/wt/x4/t02a`

## Goal
`tl new module <name>` today writes a package with no `ModuleSpec` and no entry point. After this ticket it also writes `module.py` (a `spec()` that names the module and the
`commands` hook), an empty `commands.py`, and the `throughline.modules` entry point in the module's `pyproject.toml`. A module author adds a command row to `commands.py` and
nothing in `tl-api`, `tl-mcp` or `tl-cli`. The example read route, tool and CLI group are T02b (they need files this ticket does not write). The example COMMAND is not scaffolded:
a command is an access-worded handler (core table); the fixture module `ext_demo` (T03) carries the worked example (decision D7).

## Provided test (red until done)
`docs/tickets/P2-X4/provided/test_new_module_spec.py`: copy byte-identical to `packages/tl-cli/tests/test_new_module_spec.py`. It scaffolds `inspection`, imports the generated
`tl_mod_inspection.module`, and checks the spec name, the `commands` ref, an empty resolved hook, and the entry point lines in the generated `pyproject.toml`.

## Interfaces (verbatim)
```python
# packages/tl-cli/src/tl_cli/scaffold/module.py (abridged): plan.add(path, render("module/<file>.tmpl", **values)); values = name, package, distribution
# packages/tl-core/src/tl_core/modules.py: ModuleSpec(name, record_types, projectors, ..., commands: str | None = None)  # ref "<pkg>.<module>:<Name>", inside the module's own package
```
New template `module/module_spec.py.tmpl` (write exactly; `${name}` and `${package}` are `string.Template` fields):
```python
"""What the ${name} module gives the platform (`tl_core.modules`; ADR-0029).

The entry point `throughline.modules` / `${name}` in this package's `pyproject.toml` names `spec`.
The platform calls it once per process. A hook is a dotted reference inside this package.
"""

from __future__ import annotations

from tl_core.modules import ModuleSpec

from ${package} import MODULE


def spec() -> ModuleSpec:
    return ModuleSpec(
        name=MODULE,
        record_types=frozenset(),  # `tl new record-type ${name}.<Class>` adds one; list it here
        projectors=list,  # a callable returning fresh projector instances (`tl new projector`)
        commands="${package}.commands:COMMANDS",
    )
```
New template `module/commands_hook.py.tmpl`:
```python
"""Commands this module offers to the API, the CLI and agents (`ModuleCommand` rows; ADR-0029).

A row is `ModuleCommand(module=MODULE, model=<Command class>, handler=<handler>, access=<word>)`.
Every command name must be unique across installed modules. Add `meta={"delegation": "excluded:reserved"}`
unless the design says otherwise: a missing mark means excluded.
"""

from __future__ import annotations

from tl_core.modules import ModuleCommand

COMMANDS: tuple[ModuleCommand, ...] = ()
```
`pyproject.toml.tmpl` gains, before `[build-system]`:
```
[project.entry-points."throughline.modules"]
${name} = "${package}.module:spec"
```
Generated `tests/test_module.py` (template `test_module.py.tmpl`) gains a third test: `${package}.module.spec().name == "${name}"`; the generated package then reports `3 passed`.

## Context (read these, nothing else)
- `packages/tl-cli/src/tl_cli/scaffold/module.py`
- `packages/tl-cli/src/tl_cli/scaffold/templates/module/pyproject.toml.tmpl`
- `packages/tl-cli/src/tl_cli/scaffold/templates/module/test_module.py.tmpl`
- `packages/tl-cli/tests/test_cli_new_module.py`
- `docs/tickets/P2-X4/provided/test_new_module_spec.py`
- `docs/templates/haiku-report.md`

## Allowed paths
- `packages/tl-cli/src/tl_cli/scaffold/module.py`
- `packages/tl-cli/src/tl_cli/scaffold/templates/module/module_spec.py.tmpl` (create)
- `packages/tl-cli/src/tl_cli/scaffold/templates/module/commands_hook.py.tmpl` (create)
- `packages/tl-cli/src/tl_cli/scaffold/templates/module/pyproject.toml.tmpl`
- `packages/tl-cli/src/tl_cli/scaffold/templates/module/test_module.py.tmpl`
- `packages/tl-cli/tests/test_new_module_spec.py` (create; the provided copy)
- `docs/reports/P2-X4/T02a.md` (create)
Consequential pins (list them in the report; no assertion weakened): `packages/tl-cli/tests/test_cli_new_module.py` (`EXPECTED` gains `.../module.py` and `.../commands.py`; "2 passed" becomes "3 passed"
in both places), `packages/tl-cli/tests/test_cli_new_record_type.py` or `test_cli_new_projector.py` only if a file list there breaks for the same reason.

## Acceptance
```
just check
just gate packages/tl-cli/tests/test_new_module_spec.py packages/tl-cli/tests/test_cli_new_module.py packages/tl-cli/tests/test_scaffold_engine.py packages/tl-cli/tests/test_cli_new_record_type.py packages/tl-cli/tests/test_cli_new_projector.py packages/tl-cli/tests/test_module_cli_groups.py
```
Expected: all pass; the generated files pass ruff (the existing test runs it). Name files, never the directory.

## Report requirements
Standard report; first line deviations or none; list the consequential pins; `cmp` result of the provided test.

## Escalation triggers
- The generated module fails ruff or its own tests after two attempts.
- `tl new module` output must change in a way the provided test does not cover.
- Any edit to `tl_core`, `tl_api`, `tl_mcp` or a module package seems needed.

## Blocked
(implementer writes here)

## Decision
(supervisor or orchestrator writes here)
