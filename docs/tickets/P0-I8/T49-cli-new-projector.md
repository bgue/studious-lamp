# P0-I8-T49 — `tl new projector <module>.<name>`

Status: ready
Tier: haiku
Labels: cli, tests, docs
Depends on: P0-I8-S42 (merged into the base of this branch)
Branch: `p0/i8c-t49-cli-new-projector`

## Goal
`uv run tl new projector inspection.weld_counts --event Weld.Created` adds a projector for a derived table to an existing module: the projector class, a test file (it counts its events and a rebuild gives the same rows) and a doc page. The output passes ruff and its own tests for any name within the limits. The test file `packages/tl-cli/tests/test_cli_new_projector.py` is provided; make it pass.

## Brief references (pasted)
> **Brief 25.2 Scaffolding CLI:** "Each produces a schema stub, handlers, tests, and docs placeholders."
> **Brief 25.4 (projection determinism):** property-based tests: replay(events) twice gives identical projections; projections after shadow rebuild equal live ones.
> **Root `AGENTS.md`, rule 4:** current-state DDL is generated; no hand-written `cur_*`, `hist_*` or `v_*` objects. So this scaffolder makes a *derived* table named `proj_<module>_<name>` (like the counters and the webhook state tables), and a record type's own `cur_<module>_<class>` table comes from its schema through `just gen`.
> **Projector contract (build spec 03 section 7):** `name`, `handles` (a set of event types), `ddl(dialect)` (idempotent CREATE statements), `apply(conn, event)` (inside the appending transaction; deterministic: no clock, no generated ids), `reset(conn)`.

The command line, the name parsing (`parse_projector`, `check_event_type`), `require_module` and the writing of files are already built (ticket S42). You write the planner `plan_projector` and three templates.

## Interfaces (verbatim from repo at the branch point)
```python
# packages/tl-cli/src/tl_cli/scaffold/names.py
@dataclass(frozen=True)
class ModuleName:
    name: str  # inspection
    # properties: package (tl_mod_inspection), distribution (tl-mod-inspection), directory (packages/tl-mod-inspection)

@dataclass(frozen=True)
class ProjectorName:
    """``<module>.<name>``, for example ``inspection.weld_counts``."""
    module: ModuleName
    name: str  # weld_counts
    # properties: cls (WeldCountsProjector), table (proj_inspection_weld_counts)
```
```python
# packages/tl-cli/src/tl_cli/scaffold/engine.py
@dataclass
class Plan:
    files: list[PlannedFile]
    next_steps: list[str]
    def add(self, path: str, content: str) -> None: ...       # path: posix, relative to the repository root

def render(template: str, **values: str) -> str: ...
    # templates/<template> filled with string.Template.substitute: ${name} placeholders;
    # a missing value raises KeyError, a stray "$" raises ValueError
```
```python
# packages/tl-cli/src/tl_cli/scaffold/projector.py  (the stub you replace)
def plan_projector(projector: ProjectorName, events: Sequence[str]) -> Plan:
    raise NotImplementedError("tl new projector is built by ticket P0-I8-T49")
```
The pattern to follow is `plan_module` in `packages/tl-cli/src/tl_cli/scaffold/module.py`. `events` are validated event types (`Weld.Created`); the command passes `["Record.Created"]` when no `--event` is given.

## Context (read these, nothing else)
- `packages/tl-cli/src/tl_cli/scaffold/module.py` (the pattern)
- `packages/tl-cli/tests/test_cli_new_projector.py` (the provided test)
- `packages/tl-cli/tests/expected/projector/projector.py.txt`
- `packages/tl-cli/tests/expected/projector/test.py.txt`
- `packages/tl-cli/tests/expected/projector/spec.md`
may explore: (none)

## Allowed paths
- `packages/tl-cli/src/tl_cli/scaffold/projector.py` (replace the stub)
- `packages/tl-cli/src/tl_cli/scaffold/templates/projector/projector.py.tmpl` (create)
- `packages/tl-cli/src/tl_cli/scaffold/templates/projector/test.py.tmpl` (create)
- `packages/tl-cli/src/tl_cli/scaffold/templates/projector/spec.md.tmpl` (create)

## Steps
1. The three expected files are what the planner must produce for `inspection.weld_counts` with the event `Weld.Created`, byte for byte. Make each template from its expected file by replacing the example's names with placeholders, longest first:
   | In the expected file | In the template |
   |---|---|
   | `tl_mod_inspection` | `${package}` |
   | `WeldCountsProjector` | `${cls}` |
   | `proj_inspection_weld_counts` | `${table}` |
   | `inspection_weld_counts` | `${module}_${name}` |
   | `weld_counts` | `${name}` |
   | `inspection` | `${module}` |
   | the text `"Weld.Created"` inside `frozenset({...})` in the projector | `${events_literal}` (the whole content between the braces) |
   | `Weld.Created` as the event the tests append (`"Weld.Created"` in `test.py.txt`) | `${first_event}` (keep the quotes around it) |
   | the table row `\| Weld.Created \|` in `spec.md` | `${event_rows}` |
   Mapping: `projector.py.txt` to `projector.py.tmpl`, `test.py.txt` to `test.py.tmpl`, `spec.md` to `spec.md.tmpl`. Change nothing else: the exploded `from ... import (...)` with a trailing comma in the test is deliberate, so that `ruff format` leaves the output unchanged for every name up to the limits (module 20 characters, projector name 40).
2. `plan_projector(projector, events)`:
   - `handled = sorted(set(events))`;
   - values: `module`, `package`, `name`, `cls`, `table`, `events_literal` = the handled types as `"A.B", "C.D"` (double quotes, comma and space), `first_event` = `handled[0]`, `event_rows` = one line `| <event> |` per handled type joined by newlines;
   - files, in this order: `packages/tl-mod-<module>/src/tl_mod_<module>/projectors/<name>.py`, `packages/tl-mod-<module>/tests/test_projector_<name>.py`, `docs/modules/<module>/projector-<name>.md` (use `module.directory` and `module.package`).
3. `plan.next_steps` is exactly: `register <cls> in the registry your application builds`, then `just check && just test`.
4. Run the acceptance commands. If a test fails because the template differs from the expected file, fix the template, not the expected file.

## Acceptance
```
just check
uv run pytest packages/tl-cli/tests/test_cli_new_projector.py -q
uv run pytest packages/tl-cli -q
```
Expected: all pass. The projector test file takes about 40 s.

## Tests to add
None: the provided file covers the behaviour. Do not edit it.

## Report requirements
Standard report. Paste the output of the three acceptance commands.

## Escalation triggers
- Stop and report *Blocked* if the table above does not reproduce an expected file, if `ruff` rejects a rendered file for a name within the limits, or if the provided test needs a change.

## Blocked
(implementer writes here)

## Decision
(supervisor or orchestrator writes here)
