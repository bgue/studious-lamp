# P0-I8-T24 — TUI grid columns for an extension type

Status: ready
Tier: haiku
Labels: tui
Depends on: S33 (`ClientInterface.list_types/get_type`, the fake's type support), merged on `p0/i8b`
Branch: `p0/i8b-t24-tui-grid-columns`

## Goal
When the TUI is opened on an extension type (`tl tui --type co.acme.LiftPlan`), the grid shows the columns the type's `form.yaml` names (`grid.columns`) instead of the core
record columns. This ticket is the pure part: a module that turns a type's form into `GridColumn`s and finds the form of the newest active version of a type. The supervisor wires it
into the app afterwards.

## Brief references (pasted)
> §31.3 extension types get ... generic TUI grid and forms (from LinkML + `form.yaml`).
> `form.yaml` `grid.columns` lists slot names. A grid cell shows a pset value, so a slot has a column only when it is stored as a pset value: every slot of a managed type, and the
> index fields (`tl:index`) of an object-backed type. A slot that lives only in the stored body (`path` starts with `body.`) has no column.

## Interfaces (verbatim from the repo at the branch point)
```python
# tl_core/extypes/forms.py
class TypeFormField(BaseModel):
    name: str; path: str  # "psets.<pset>.<name>" or "body.<name>"
    label: str; kind: str; multivalued: bool = False   # kind: string, text, int, decimal, bool, date, datetime, enum, ref
class TypeForm(BaseModel):
    type_ref: str; type_name: str; grid_columns: list[str]   # slot names, in order
    def fields(self) -> list[TypeFormField]: ...
    def field(self, name: str) -> TypeFormField | None: ...
# tl_core/extypes/service.py
class TypeSummary(BaseModel): type_ref: str; type_name: str; version: str; status: str   # "active" | "deprecated" | "quarantined"
# tl_tui/client.py (ClientInterface)
def list_types(self, status: TypeStatus | None = None) -> list[TypeSummary]: ...
def get_type(self, type_ref: str) -> TypeDetail: ...     # TypeDetail.form: TypeForm | None
# tl_tui/widgets/grid.py
@dataclass(frozen=True)
class GridColumn: key: str; label: str; width: int; align: "left" | "right" = "left"
```
The stub `packages/tl-tui/src/tl_tui/extension_columns.py` has the constants, `_version_key`, `columns_for_type` (finished) and four stubs with comments that say what to do. Replace each
`raise NotImplementedError("STUB (P0-I8-T24)")`. Do not change a signature.

## Context (read these, nothing else)
- `packages/tl-tui/src/tl_tui/extension_columns.py` (the stub)
- `docs/tickets/P0-I8/provided/b-test_extension_columns.py.txt` (the test to make pass)
- `packages/tl-tui/tests/fakes_types.py` (read only: the fake the test uses)
may explore: (none)

## Allowed paths
- `packages/tl-tui/src/tl_tui/extension_columns.py` (replace the stub bodies)
- `packages/tl-tui/tests/test_extension_columns.py` (create: copy of the provided file, unchanged)
- `docs/reports/P0-I8/P0-I8-T24.md` (create: your report; commit it)

## Steps
1. `uv sync --all-packages`. Run every command from the repository root.
2. `cp docs/tickets/P0-I8/provided/b-test_extension_columns.py.txt packages/tl-tui/tests/test_extension_columns.py`. Do not edit it.
3. Fill in `column_for`, `columns_for_form`, `newest_active`, `form_for_type`. Delete the stub's first line (`# ruff: noqa: F401 ...`) once ruff has no unused import left.

## Acceptance
```
just check
uv run pytest packages/tl-tui/tests/test_extension_columns.py -q
uv run pytest packages/tl-tui -q
```
Expected: `just check` clean; 9 passed in `test_extension_columns.py`; the rest of `packages/tl-tui` still passes (about 5 minutes).

## Tests to add
- `packages/tl-tui/tests/test_extension_columns.py`: the provided file (index-field columns of an object-backed type, alignment and widths, body-only and unknown names left out, a managed
  type, core and unknown types, a deprecated type, the newest active version, a client that refuses, `form_for_type`).

## Report requirements
Standard report. Paste the output of the three acceptance commands.

## Rules to remember (from the project's learnings)
- Ruff's line limit is 100 columns, including docstrings and comments. Write files with the Write or Edit tool, not shell heredocs. Never use `pkill -f`.
- Never name a module `types.py`. Run Python from the repository root.
- Commit as `P0-I8-T24: <summary>` with the report in the same commit.

## Escalation triggers
- Stop and report *Blocked* if a comment and the provided test disagree, if a function listed under Interfaces is missing or has another signature, or if you would have to touch a
  file outside *Allowed paths*.

## Blocked
(implementer writes here)

## Decision
(supervisor or orchestrator writes here)
