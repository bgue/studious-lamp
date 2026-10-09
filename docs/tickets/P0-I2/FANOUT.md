# Fanout plan — P0-I2 Layered psets, schema registry v0, effective schema, TUI shell

Status: active
Orchestrator session: 2026-10-09
Brief sections: §6.3, §6.4, §10.1–§10.4, §10.6 sketches 1/2/11, §27.1–§27.5, §5.4

## Objective
A company standard pset with enforcement and a project extension (the §6.3 `valve_data` example) compile into a
hashed effective schema; `Pset.ValuesSet` is validated, conformance-evaluated, and projected; a Textual shell with a
grid and a record view (Details, Psets, History tabs) edits those values in embedded mode.

## Exit criteria
- [ ] `tl schema hash P123` prints a stable content hash; changing a fixture package changes it.
- [ ] `tl pset set` / TUI save of `valve_data.size_in` and `valve_data.x.fat_witness_by` emits `Pset.ValuesSet` carrying `effective_schema_hash`.
- [ ] A missing advisory property shows `warning`; a missing required-in-state property shows `nonconformant`; every row of the §6.3 "projects can / cannot" table has a test.
- [ ] TUI snapshot tests for shell, grid, record view, psets tab, narrow mode.
- [ ] `just demo P0-I2` runs the demo in the plan.

## Workstreams

| WS | Name | Supervisor branch / worktree | Provides | Consumes |
|---|---|---|---|---|
| A | Schema: packages, effective schema, psets, conformance | `p0/i2a` · `/home/user/wt/p0-i2a` | `tl_schema.forms` models, `tl_core.services.psets`, `SetPsetValues`, conformance | P0-I1 ledger/UoW/projector |
| B | TUI shell, grid, record view, forms | `p0/i2b` · `/home/user/wt/p0-i2b` | `tl_tui` app, `ClientInterface` embedded impl | WS-A contracts below |

Integration branch: `p0/i2` (created by the orchestrator from the trunk). Both workstream branches start from `p0/i2`
after the contracts commit.

## Shared contracts (committed on `p0/i2` before fanout, by the orchestrator via WS-A's first act)

```python
# packages/tl-schema/src/tl_schema/forms.py
from typing import Literal
from pydantic import BaseModel

Layer = Literal["core", "standard", "custom", "project", "enrichment", "source"]
Enforcement = Literal["advisory", "required", "locked"]
FieldKind = Literal["string", "text", "int", "decimal", "bool", "date", "datetime", "enum", "quantity", "ref", "json"]

class EnumValue(BaseModel):
    code: str
    label: str
    crosswalk: str | None = None      # company code a project value maps to

class FieldMeta(BaseModel):
    path: str                          # "title" | "psets.valve_data.size_in" | "psets.valve_data.x.fat_witness_by" | "psets.prj.shutdown_tie_in.window"
    label: str
    description: str
    kind: FieldKind
    unit: str | None = None            # UCUM code
    enum_values: list[EnumValue] | None = None
    required_in_states: list[str] = []
    enforcement: Enforcement | None = None
    layer: Layer
    readonly: bool = False             # True for enrichment/source layers and locked-for-project metadata
    group: str                         # pset name, or "details" for core fields
    order: int

class PsetGroupMeta(BaseModel):
    name: str                          # "valve_data", "prj.shutdown_tie_in"
    label: str
    package: str                       # "co.acme.engineering"
    version: str                       # "3.2.0"
    enforcement: Enforcement | None
    layer: Layer
    fields: list[FieldMeta]

class FormMetadata(BaseModel):
    record_type: str
    effective_schema_hash: str
    core_fields: list[FieldMeta]
    psets: list[PsetGroupMeta]

ConformanceStatus = Literal["ok", "warning", "nonconformant", "waived"]

class ConformanceIssue(BaseModel):
    path: str
    level: Literal["warning", "nonconformant"]
    rule: str                          # "required_in_state" | "value_list" | "range" | "pattern" | "locked" | "type"
    message: str

class ConformanceReport(BaseModel):
    status: ConformanceStatus
    issues: list[ConformanceIssue]
    effective_schema_hash: str
```

```python
# packages/tl-core/src/tl_core/services/psets.py  (signatures; WS-A implements)
class SetPsetValues(Command):           # Command from tl_core.services.commands
    stream_id: str
    expected_version: int
    pset: str                           # "valve_data" | "prj.shutdown_tie_in"
    layer: Literal["standard", "custom", "project"]   # enrichment/source are not writable by users
    values: dict[str, Any]              # keys relative to the pset; custom-section keys prefixed "x."

def handle_set_pset_values(uow: UnitOfWork, cmd: SetPsetValues) -> CommandResult: ...
def form_metadata(uow: UnitOfWork, scope: str, record_type: str) -> FormMetadata: ...
def conformance(uow: UnitOfWork, record_id: str) -> ConformanceReport: ...
```

```python
# packages/tl-tui/src/tl_tui/client.py  (WS-B owns; embedded impl calls tl_core services only)
class ClientInterface(Protocol):
    def list_records(self, scope: str, *, record_type: str | None = None, status: str | None = None,
                     include_voided: bool = False, limit: int = 500, offset: int = 0) -> list[dict[str, Any]]: ...
    def get_record(self, scope: str, key: str) -> dict[str, Any] | None: ...
    def get_record_by_id(self, record_id: str) -> dict[str, Any] | None: ...
    def history(self, record_id: str) -> list[Event]: ...
    def create_record(self, cmd: CreateRecord) -> CommandResult: ...
    def update_record(self, cmd: UpdateRecord) -> CommandResult: ...
    def set_pset_values(self, cmd: SetPsetValues) -> CommandResult: ...
    def form_metadata(self, scope: str, record_type: str) -> FormMetadata: ...
    def conformance(self, record_id: str) -> ConformanceReport: ...
```
WS-B codes against these with an in-memory fake until WS-A merges; the fake lives in `packages/tl-tui/tests/fakes.py`.

## Merge order and conflict owner
1. Contracts commit on `p0/i2`.
2. WS-A → `p0/i2` (when WS-A reports DONE).
3. WS-B merges `p0/i2` into `p0/i2b`, swaps the fake for the embedded client in its demo, then → `p0/i2`.
Conflicts: WS-B's supervisor, merge commits only. Demo and increment report: WS-B's supervisor, at the end.

## Human gates
| Gate | Approver | Where recorded |
|---|---|---|
| `schema/core/psets.yaml` and `schema/fixtures/*` | Orchestrator under KICKOFF delegation (in scope of §6.3) | docs/reports/APPROVALS.md |

## Risks and escalation triggers
- linkml SchemaView merge of packages may not express `x.` custom sections cleanly → WS-A may compile custom sections to a sibling class (`ValveData_P123_x`) per §27.3; record as deviation, not an escalation.
- Textual snapshot tests can be flaky across terminal sizes → fix size in tests (120×40 and 80×24).
