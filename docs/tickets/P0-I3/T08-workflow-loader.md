# P0-I3-T08 — Workflow definition loader and registry

Status: ready
Tier: haiku
Labels: core
Depends on: — (models and stub are on the base branch)
Branch: `p0/i3-t08-workflow-loader`

## Goal
`tl_core.workflow.loader` reads declarative workflow definitions (YAML) into the pydantic models of `tl_core.workflow.definition`, checks
their meaning (`semantic_problems`), and offers a `WorkflowRegistry` that finds the definition for a record type and scope. The models, the
sample `schema/fixtures/workflows/core-review.yaml` and all signatures exist; every function body marked `raise NotImplementedError` is
the work. A provided test file (43 tests) must pass.

## Brief references (pasted)
> **8 Workflow engine:** Declarative state machines per record type (states, transitions, guards, required psets, required links, approvers, signatures, notifications). Versioned; company defaults with project overrides.

### Specification (the provided test checks it)
- `parse_workflow(text, source=)`:
  1. `yaml.safe_load`; a `yaml.YAMLError` raises `WorkflowError(f"{source}: invalid YAML: {exc}")`.
  2. A document that is not a `dict` raises `WorkflowError(f"{source}: a workflow file must be a YAML mapping, not {type(data).__name__}")`.
  3. `WorkflowDefinition.model_validate(data)`; a `ValidationError` raises one `WorkflowError` whose message is one line per pydantic error, `f"{source}: {'.'.join(str(p) for p in error['loc'])}: {error['msg']}"`, joined by newlines.
  4. `semantic_problems(definition)`; if any, raise `WorkflowError` with one line per problem, `f"{source}: {problem}"`, joined by newlines.
- `load_workflow(path)`: read UTF-8 text; `OSError`/`UnicodeDecodeError` raise `WorkflowError(f"{path.name}: cannot read file: {exc}")`; otherwise `parse_workflow(text, source=path.name)`.
- `semantic_problems(definition)` returns strings in this order; each check appends in the order shown (exact wording is tested):
  1. For each state name that repeats (second and later occurrence): `duplicate state 'A'`.
  2. `initial_state 'Z' is not a state` when the initial state is not among the state names.
  3. `invalid scope 'x'` when `scope` does not fully match `company|project:[A-Za-z0-9_.-]+`.
  4. For each transition, in order: `duplicate transition 'go'` if its name was seen before; `transition 'go' has no from states` if `from_states` is empty; for each from state not a state, `transition 'go' starts in unknown state 'Q'`; then, if `to` is not a state, `transition 'go' ends in unknown state 'R'`; then for each `RequiredPsetsGuard` in its guards with neither `psets` nor `values`, `transition 'go': a required_psets guard needs psets or values`.
  5. Only when the initial state is a state: breadth-first from the initial state along transitions (a transition leads from each of its `from_states` that is reached to `to`; ignore targets that are not states); then for each state name in declaration order (skip repeated names) that was not reached: `state 'C' is unreachable from the initial state`.
- `WorkflowRegistry`:
  - `add(d)`: raise `WorkflowError(f"workflow {d.id} version {d.version} scope {d.scope} is already registered")` if a definition with the same `(id, version, scope)` exists; else append.
  - `all()`: a new list in registration order.
  - `find(record_type, scope)`: candidates have `record_type` equal and `scope` equal to the given scope or `"company"`. None: return `None`. Else the candidate with the greatest `(d.scope == scope, d.version)`.
  - `get(workflow_id, version)`: definitions with that id and version; none: `None`; else the company-scope one if present, otherwise the first.
- `load_workflows(directory)`: a missing directory (`not directory.is_dir()`) gives an empty registry; otherwise `load_workflow` each `*.yaml` directly inside, sorted by name (not recursive), adding to a registry. The first bad file's `WorkflowError` propagates.
- `default_workflows()`: `load_workflows(default_schema_dir() / "workflows")` with `from tl_schema.registry import default_schema_dir` (it honours `TL_SCHEMA_DIR`).

Learnings that apply:
- Provided tests live under `docs/tickets/P0-I3/provided/*.py.txt` and are copied into the test tree by you. Do not edit the copy.
- pyright is `strict` for `packages/tl-core/src`: annotate `yaml.safe_load` results as `Any`. ruff limits lines to 100 columns; run `uv run ruff format` before committing. `uv` prints "UV_NATIVE_TLS is deprecated"; ignore it. Do not pipe `just check` into `tail`.
- Remove the `STUB (P0-I3-T08)` paragraph from the module docstring when you are done.

## Interfaces (verbatim from the repo at the branch point)
```python
# packages/tl-core/src/tl_core/workflow/definition.py (existing; do not edit)
class RequiredPsetsGuard(_Model):  kind: Literal["required_psets"]; psets: list[str] = []; values: list[str] = []
class ConformanceGuard(_Model):    kind: Literal["conformance"]; max_status: Literal["ok", "warning"] = "warning"
class RequiredLinksGuard(_Model):  kind: Literal["required_links"]; links: list[ExpectedLink]
class ExpectedLinksGuard(_Model):  kind: Literal["expected_links"]
class RolesGuard(_Model):          kind: Literal["roles"]; any_of: list[str]
class StateDef(_Model):            name: str; label: str | None = None
class TransitionDef(_Model):       name: str; from_states: list[str] (alias "from"); to: str; label: str | None; guards: list[Guard]
class WorkflowDefinition(_Model):
    id: str; version: int; record_type: str; scope: str = "company"; initial_state: str
    states: list[StateDef]; transitions: list[TransitionDef] = []
    def state_names(self) -> list[str]: ...
    def transition(self, name: str) -> TransitionDef | None: ...
    def transitions_from(self, state: str) -> list[TransitionDef]: ...
```
```python
# packages/tl-core/src/tl_core/workflow/loader.py (existing stub; keep every name and signature)
class WorkflowError(ValueError): ...
def parse_workflow(text: str, *, source: str = "<string>") -> WorkflowDefinition: ...
def load_workflow(path: Path) -> WorkflowDefinition: ...
def semantic_problems(definition: WorkflowDefinition) -> list[str]: ...
class WorkflowRegistry:
    def __init__(self, definitions: Iterable[WorkflowDefinition] = ()) -> None: ...   # implemented; calls self.add
    def add(self, definition) -> None; def all(self) -> list[WorkflowDefinition]
    def find(self, record_type: str, scope: str) -> WorkflowDefinition | None
    def get(self, workflow_id: str, version: int) -> WorkflowDefinition | None
def load_workflows(directory: Path) -> WorkflowRegistry: ...
def default_workflows() -> WorkflowRegistry: ...
```

## Context (read these, nothing else)
- `AGENTS.md`
- `packages/tl-core/src/tl_core/workflow/loader.py`
- `packages/tl-core/src/tl_core/workflow/definition.py`
- `schema/fixtures/workflows/core-review.yaml`
- `docs/tickets/P0-I3/provided/test_workflow_loader.py.txt`
may explore: (none)

## Allowed paths
- `packages/tl-core/src/tl_core/workflow/loader.py` (edit)
- `packages/tl-core/tests/test_workflow_loader.py` (create: byte-for-byte copy of the provided file)
- `docs/reports/P0-I3/P0-I3-T08.md` (create: your report; commit it)

## Steps
1. `cp docs/tickets/P0-I3/provided/test_workflow_loader.py.txt packages/tl-core/tests/test_workflow_loader.py`
2. Implement the functions and the registry; delete the STUB paragraph.
3. Run the acceptance commands, write the report, commit both.

## Acceptance
```
uv run pytest packages/tl-core/tests/test_workflow_loader.py -q
just check
just test
diff docs/tickets/P0-I3/provided/test_workflow_loader.py.txt packages/tl-core/tests/test_workflow_loader.py
```
Expected: 43 tests pass, `just check` and `just test` exit 0, `diff` prints nothing.

## Tests to add
None beyond the provided file.

## Report requirements
Standard report plus the decisive lines of the four acceptance commands. Commit the report file.

## Escalation triggers
- Stop and report *Blocked* if a provided test contradicts the specification, or if `definition.py` needs a change.
- Stop rather than change any other file.

## Blocked
(implementer writes here)

## Decision
(supervisor or orchestrator writes here)
