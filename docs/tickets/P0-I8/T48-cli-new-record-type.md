# P0-I8-T48 — `tl new record-type <module>.<Class>`

Status: ready
Tier: haiku
Labels: cli, tests, docs
Depends on: P0-I8-S42 (merged into the base of this branch)
Branch: `p0/i8c-t48-cli-new-record-type`

## Goal
`uv run tl new record-type inspection.WeldInspection` adds a record type to an existing module: a LinkML schema stub, a create handler, a test file and a spec page. The output passes ruff and its own tests, for any module and class name within the limits. The test file `packages/tl-cli/tests/test_cli_new_record_type.py` is provided; make it pass.

## Brief references (pasted)
> **Brief 25.2 Scaffolding CLI:** `tl new record-type <module>.<Class>` ... "Each produces a schema stub, handlers, tests, and docs placeholders."
> **Brief 25.1:** adding a record type is mainly a schema and workflow change; the current-state table `cur_<module>_<class>` is generated from the LinkML class (`tl:current_state: true`), never written by hand (root `AGENTS.md`, rule 4).
> **Naming (build spec 03 section 5):** record type `<module>.<Class>`; event type `<Class>.<PastTenseVerb>`; command `<Verb><Class>`.

The command line, the name parsing (`parse_record_type`), `require_module` and the writing of files are already built (ticket S42). You write the planner `plan_record_type` and four templates.

## Interfaces (verbatim from repo at the branch point)
```python
# packages/tl-cli/src/tl_cli/scaffold/names.py
@dataclass(frozen=True)
class ModuleName:
    name: str  # inspection
    # properties: package (tl_mod_inspection), distribution (tl-mod-inspection), directory (packages/tl-mod-inspection)

@dataclass(frozen=True)
class RecordTypeName:
    """``<module>.<Class>``, for example ``inspection.WeldInspection``."""
    module: ModuleName
    cls: str  # WeldInspection
    # properties: snake (weld_inspection), qualified (inspection.WeldInspection), table (cur_inspection_weld_inspection)
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
# packages/tl-cli/src/tl_cli/scaffold/record_type.py  (the stub you replace)
def plan_record_type(record_type: RecordTypeName) -> Plan:
    raise NotImplementedError("tl new record-type is built by ticket P0-I8-T48")
```
The pattern to follow is `plan_module` in `packages/tl-cli/src/tl_cli/scaffold/module.py`.

## Context (read these, nothing else)
- `packages/tl-cli/src/tl_cli/scaffold/module.py` (the pattern)
- `packages/tl-cli/tests/test_cli_new_record_type.py` (the provided test)
- `packages/tl-cli/tests/expected/record_type/weld_inspection.yaml`
- `packages/tl-cli/tests/expected/record_type/handler.py.txt`
- `packages/tl-cli/tests/expected/record_type/test.py.txt`
- `packages/tl-cli/tests/expected/record_type/spec.md`
may explore: (none)

## Allowed paths
- `packages/tl-cli/src/tl_cli/scaffold/record_type.py` (replace the stub)
- `packages/tl-cli/src/tl_cli/scaffold/templates/record_type/schema.yaml.tmpl` (create)
- `packages/tl-cli/src/tl_cli/scaffold/templates/record_type/handler.py.tmpl` (create)
- `packages/tl-cli/src/tl_cli/scaffold/templates/record_type/test.py.tmpl` (create)
- `packages/tl-cli/src/tl_cli/scaffold/templates/record_type/spec.md.tmpl` (create)

## Steps
1. The four expected files are what the planner must produce for `inspection.WeldInspection`, byte for byte. Make each template from its expected file by replacing the example's names with placeholders, longest first so one replacement never breaks another:
   | In the expected file | In the template |
   |---|---|
   | `inspection.WeldInspection` | `${qualified}` |
   | `tl_mod_inspection` | `${package}` |
   | `WeldInspection` | `${cls}` |
   | `weld_inspection` | `${snake}` |
   | `inspection` | `${module}` |
   Mapping of expected file to template: `weld_inspection.yaml` to `schema.yaml.tmpl`, `handler.py.txt` to `handler.py.tmpl`, `test.py.txt` to `test.py.tmpl`, `spec.md` to `spec.md.tmpl`. Do not change anything else in the text: the layout of the Python files (one argument per line, trailing commas, an exploded `SCHEMA = ROOT.joinpath(...)`) is deliberate, so that `ruff format` leaves the output unchanged for every name up to the limits (module 20 characters, class 30).
2. `plan_record_type(record_type)` returns a `Plan` with these four files, in this order, rendered with the values `module`, `package`, `cls`, `snake`, `qualified`:
   - `schema/modules/<module>/<snake>.yaml`
   - `packages/tl-mod-<module>/src/tl_mod_<module>/handlers/<snake>.py` (use `module.directory` and `module.package` from `ModuleName`)
   - `packages/tl-mod-<module>/tests/test_<snake>.py`
   - `docs/modules/<module>/<snake>.md`
3. Set `plan.next_steps` to exactly these three lines, with the names filled in (the CLI prints each as `next: <line>`):
   - ``add `- <snake>` to the imports of schema/modules/<module>/module.yaml``
   - `replace the example field in schema/modules/<module>/<snake>.yaml`
   - `just check && just test`
4. Run the acceptance commands. If a test fails because the template differs from the expected file, fix the template, not the expected file.

## Acceptance
```
just check
uv run pytest packages/tl-cli/tests/test_cli_new_record_type.py -q
uv run pytest packages/tl-cli -q
```
Expected: all pass. The record-type test file takes about 40 s (it runs ruff and the generated tests in temporary trees).

## Tests to add
None: the provided file covers the behaviour (exact output, next steps, ruff and the generated tests for four different names including the longest allowed, missing module, no overwrite, dry run, bad names). Do not edit it.

## Report requirements
Standard report. Paste the output of the three acceptance commands.

## Escalation triggers
- Stop and report *Blocked* if a provided expected file does not match the layout the table above produces (for example a name that appears inside another word), if `ruff` rejects a rendered file for a name within the limits, or if the provided test needs a change.

## Blocked
(implementer writes here)

## Decision
(supervisor or orchestrator writes here)
