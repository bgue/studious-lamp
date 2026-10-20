# Phase 3 — shared contracts (DRAFT)

Status: **DRAFT**, 2026-10-20. The orchestrator freezes these at wave 0 of `09-phase3-plan.md`, commits the files
named here, and from then on they change only by orchestrator decision (the P1-I3 and Phase 2 practice). Style: the
Phase 2 contract (Pydantic models with bounds as module constants, a `Protocol` per plugin, LinkML for wire shapes,
pipeline-side signatures as comments). Owner questions are marked `P3-Q<n>`.

| § | Contract | Fanout that needs it frozen | File |
|---|---|---|---|
| 1 | Checklist form metadata and responses | I2 WS-A ∥ WS-B | `tl_mod_quality/checklists/types.py` |
| 2 | NDE selection rule, `RecordNDEResult`, the inbound payload | I3 WS-A ∥ WS-B; I8 simulator | `schema/modules/piping/nde.yaml`, `tl_mod_piping/nde/types.py` |
| 3 | Sync wire protocol, `PendingCommand`, outcomes, `tl:merge` | I5 WS-A ∥ WS-B | `schema/core/sync.yaml`, `tl_core/sync/types.py` |
| 4 | Viewer component interface, spatial context view, pairing | I7 WS-A ∥ WS-B | `web/src/viewer/interface.ts`, `tl_mod_models/context/types.py` |
| 5 | Readiness subjects (a change to the frozen Phase 2 contract) | I4; Phase 2 checks | `tl_core/readiness/types.py` |
| 6 | Issue engine API consumed by I2, I3 and I7 | I2, I3 WS-A, I7 WS-A | `tl_mod_quality/issues/api.py` |
| 7 | Reserved identifiers, job kinds, settings keys added by Phase 3 | all | `tl_core/services/reserved.py`, `schema/settings/platform.yaml` |
| 8 | External-party scope on the viewer | I8; every walking test | `tl_core/confidentiality.py` (ADR) |

---

## 1. Checklist form metadata and responses (I2)

```python
"""A ChecklistTemplate stores its questions as a versioned pset definition (brief M5). The runner screen
(WS-B) needs a form it can walk without knowing psets; RecordInspectionResult (WS-A) needs responses it
can validate as pset values. This file is the shape between them."""

from typing import Literal
from pydantic import BaseModel, Field

MAX_QUESTIONS = 200
MAX_CHOICES = 20
MAX_TEXT_CHARS = 1000

QuestionKind = Literal["yes_no", "yes_no_na", "number", "text", "choice", "date", "photo"]

class Question(BaseModel):
    id: str = Field(pattern=r"^q[0-9]{1,3}$")       # the pset property name
    text: str = Field(max_length=300)
    kind: QuestionKind
    required: bool = True
    unit: str | None = None                        # number only
    choices: list[str] = Field(default_factory=list, max_length=MAX_CHOICES)
    min_value: float | None = None
    max_value: float | None = None
    section: str | None = None

class ChecklistForm(BaseModel):
    template_id: str
    template_key: str                              # P123-CHK-0007
    version: int
    title: str
    questions: list[Question] = Field(max_length=MAX_QUESTIONS)

#: One response per question id; the value's Python type follows the kind (bool, bool | None,
#: float, str, str, date ISO string, file sha256). Missing required answers fail validation with
#: the question ids; unknown ids are refused.
Responses = dict[str, object]

# WS-A signatures WS-B tests against:
#   tl_mod_quality.checklists.form_for(conn, template_id) -> ChecklistForm      (viewer-filtered)
#   tl_mod_quality.checklists.validate(form, responses) -> list[str]            (problems, empty = ok)
#   RecordInspectionResult(inspection_id, result: "accept"|"reject"|"conditional", responses: Responses,
#                          witnesses: list[party_id], instruments: list[record_id])
# The TUI client method the screen calls: ClientInterface.checklist_form(template_id) -> ChecklistForm and
# ClientInterface.record_inspection_result(...) -> CommandResult. The punch walkdown screen calls only
# RaiseDeficiency(against, category, description, location, system) with the prefill kept in the screen.
```

## 2. NDE selection rule, `RecordNDEResult`, inbound payload (I3)

LinkML (`schema/modules/piping/nde.yaml`):

```yaml
classes:
  NDESelectionRule:
    is_a: RecordEnvelope
    annotations: {tl:current_state: true}
    slots: [piping_class, method, percent, lot_size, penalty_percent, penalty_count, applies_to_shop, applies_to_field]
  NDERequest:
    is_a: RecordEnvelope
    slots: [method, lot_no, weld_ids, selected_by, status]     # status: Requested → Examined → Closed
  NDEResult:
    is_a: RecordEnvelope
    slots: [request_id, weld_id, method, result, report_no, reject_reason, examined_on, examined_by_party]
enums:
  NDEMethod: {permissible_values: {RT: {}, UT: {}, PT: {}, MT: {}, PMI: {}, HT: {}}}
  NDEResultValue: {permissible_values: {accept: {}, reject: {}, retest: {}}}
```

```python
"""tl_mod_piping/nde/types.py: what the inbound mapping (WS-B) and the engine (WS-A) agree on."""

class RecordNDEResult(Command):
    """access user; listed in AUTOMATION_COMMANDS so svc:inbound-acme-nde may run it.
    Resolution: weld_key within scope, then request by (weld, method, open). A weld with no open
    request for the method is refused with NDE_NO_OPEN_REQUEST (the error queue keeps the delivery)."""
    weld_key: str                      # "ISO-1234/W-012" or "ISO-1234/W-012R1"
    method: NDEMethod
    result: NDEResultValue
    report_no: str = Field(max_length=64)
    reject_reason: str | None = Field(default=None, max_length=200)
    examined_on: date
    examined_by_party: str | None = None   # party key; the endpoint's app fixes it when absent

#: Events: NDE.Selected {rule_id, lot_no, weld_ids}, NDE.Requested {request_id}, NDE.ResultRecorded
#: {result_id, weld_id, result}, NDE.Rejected {weld_id, request_id, penalty: {count, weld_ids}} (webhook).
#: Engine signatures: tl_mod_piping.nde.select(uow, scope, piping_class, method, *, today) -> list[request_id]
#: (bounded by one lot per run; idempotent per lot), tl_mod_piping.nde.penalty(uow, rejected_weld_id).
```

Inbound payload (the contractor's JSON, mapped by JSONata in the `acme-nde` endpoint fixture):

```json
{"report": "RT-2026-0442", "weld": "ISO-1234/W-012", "method": "RT", "result": "REJECT",
 "reason": "porosity", "date": "2026-11-03", "lab": "ACME NDE"}
```

Mapping: `result` upper-cased to the enum; `lab` → `examined_by_party` through the endpoint's party; signature
HMAC-SHA256 over the raw body with the endpoint secret (`int_secret`, ADR-0017 §2); replay protection by `report`
plus `weld` in `int_replay`.

## 3. Sync wire protocol, `PendingCommand`, outcomes, `tl:merge` (I5)

LinkML `schema/core/sync.yaml` (messages are `tl:message` classes: JSON Schema is generated, no tables):

```yaml
classes:
  Handshake:      {slots: [replica_id, protocol_version, schema_hash, mirror_cursor, local_head_hash, device_time, pending_count]}
  HandshakeAck:   {slots: [server_time, skew_ms, scope, max_offline_days, oldest_pending_allowed, schema_action]}  # schema_action: ok | upcast | revalidate
  PullRequest:    {slots: [after_seq, limit]}
  PullBatch:      {slots: [events, next_seq, done]}                 # events: canonical Event rows, viewer-filtered
  FileManifest:   {slots: [sha256, size, content_type, present]}
  PushCommands:   {slots: [commands]}                               # list of PendingCommand, local order
  PendingCommand:
    slots: [command_id, replica_id, hlc, captured_at, effective_at, base_seq, base_versions, command_name, body, schema_hash, local_hash, prev_local_hash]
  Outcome:
    slots: [command_id, outcome, canonical_event_ids, final_key, conflict_id, reason_code]
  AckBatch:       {slots: [outcomes, events]}                      # events: the canonical events the merge produced
enums:
  OutcomeKind: {permissible_values: {accepted: {}, auto_merged: {}, conflict: {}, rejected: {}, quarantined: {}}}
  MergePolicy:
    permissible_values: {append_only: {}, delta: {}, add_wins: {}, scalar: {}, lww_effective: {}, upstream_wins: {}, replica_wins: {}, transition: {}, numbering: {}, natural_key: {}}
```

```python
"""tl_core/sync/types.py"""
PROTOCOL_VERSION = 1
MAX_PULL_BATCH = 1000
MAX_PUSH_COMMANDS = 500
MAX_BODY_BYTES = 64 * 1024
MAX_BASE_VERSIONS = 50          # streams one command may touch
MAX_SKEW_MS = 5 * 60 * 1000     # past this the handshake flags, not refuses
HLC = tuple[int, int, str]      # (wall ms, counter, replica_id); total order

# WS-A signatures WS-B tests against (WS-B ships a FakeSyncClient over them):
#   tl_core.sync.client.SyncClient(target: DbTarget, upstream: str, identity: ReplicaIdentity)
#       .handshake() -> HandshakeAck; .pull() -> int; .rebase_preview() -> list[PendingPreview]
#       .push_files() -> int; .push() -> list[Outcome]; .sync() -> SyncReport   (steps 1 to 7 in order)
#   tl_core.sync.merge.merge_command(uow, cmd: PendingCommand, replica: ReplicaRow) -> Outcome
#       re-executes through tl_api.commands.command_runner() as the replica owner; outcome by policy
#   tl_core.sync.policies.policy_for(record_type, slot) -> MergePolicy   (from tl:merge, default by kind)
#   tl_core.sync.conflicts.open_conflict(uow, cmd, kind, base, mine, theirs) -> conflict_id
#   ResolveConflict(conflict_id, choice: keep_mine|keep_theirs|merge_fields|merge_records, fields: dict)
# The replica side: tl_adapters.sqlite.replica (segment tables), tl_core.sync.replica_uow.ReplicaUnitOfWork
# (the ADR's UnitOfWork), tl_core.sync.hlc.
# Defaults by kind of data (brief §22.4): new records and append-only facts append_only; quantities delta;
# set-valued slots add_wins; scalars and psets scalar (conflict unless annotated); workflow transition;
# keys numbering (provisional "~" alias kept, P3-Q8); natural keys natural_key (weld_no per iso, joint_no per line).
```

`tl:merge` is declared in `schema/core/annotations.yaml` as a slot or class annotation with a `MergePolicy` value;
the generator emits `tl_schema.generated.merge_policies` (a dict) so `policy_for` reads generated data.

## 4. Viewer component interface, spatial context, pairing (I7)

```ts
// web/src/viewer/interface.ts — the only surface the workspace, the guest page and the pairing driver use.
export interface Viewpoint { camera: Camera; sections: Plane[]; visible?: string[]; hidden?: string[];
  selected?: string[]; coloured?: Record<string, string>; snapshotSha256?: string }
export interface ModelViewer {
  load(slice: { url: string; revisionId: string }): Promise<void>;
  unload(revisionId: string): void;
  highlight(ids: string[], opts?: { xrayOthers?: boolean }): void;
  flyTo(ids: string[]): void;
  isolate(ids: string[]): void; xray(ids: string[]): void; showAll(): void;
  setOverlay(colours: Record<string, string>): void;        // global id → hex
  section(plane: Plane | null): void; measure(on: boolean): void;
  applyViewpoint(vp: Viewpoint): void; captureViewpoint(): Promise<Viewpoint>;
  on(event: "select" | "hover" | "ready", cb: (ids: string[]) => void): () => void;
}
// XeokitViewer implements ModelViewer; a NullViewer (no SDK) implements it for tests and for builds without
// the licence (P3-Q9). The workspace never imports xeokit directly.
```

```python
"""tl_mod_models/context/types.py"""
MAX_CONTEXT_OBJECTS = 2000
ContextSource = Literal["direct", "mapped", "located", "inherited", "area", "none"]

class SpatialContext(BaseModel):
    record_id: str
    ctx_model_id: str | None
    ctx_revision_id: str | None
    ctx_object_count: int
    ctx_source: ContextSource
    ctx_location_label: str | None       # "Unit 12 · Level 2 · Grid C4"
    object_ids: list[str] = Field(default_factory=list, max_length=MAX_CONTEXT_OBJECTS)
    slice_id: str | None                 # the smallest eligible slice that covers the objects
    via: list[str] = Field(default_factory=list)   # record ids walked for "inherited"

# tl_mod_models.context.resolve(conn, record_id, *, viewer) -> SpatialContext   (reads only; order §23.5)
# tl_mod_models.context.recompute(uow, scope, *, reason) -> int                  (job models.context)
# tl:spatial_context_via on a class: a list of link relations or slot names walked in order, depth ≤ 3.
# Pairing: POST /pairing (code, 10 minutes, same account) → SSE /pairing/{code}/events carrying
# {"action": "highlight"|"flyTo"|"applyViewpoint", "ids": [...]} from the TUI's DriveViewer command.
```

## 5. Readiness subjects (a change to the frozen Phase 2 contract; orchestrator decision)

```python
class SubjectFacts(BaseModel):
    record_id: str; scope: str; key: str; record_type: str; status: str
    planned_start: date | None = None; planned_finish: date | None = None
    scope_ids: dict[str, list[str]] = {}         # records the subject contains or covers, by type
    pinned_document_links: list[str] = []

class IwpFacts(SubjectFacts): ...                 # the Phase 2 fields, unchanged names
class TestPackageFacts(SubjectFacts):
    lines: list[str]; welds: list[str]; joints: list[str]; gauges: list[str]; subsystem: str | None

class ReadinessCheck(Protocol):
    name: str; version: str; watches: frozenset[str]
    subjects: frozenset[str]                       # {"awp.IWP"}, {"testing.TestPackage"} or both
    def evaluate(self, conn, subject: SubjectFacts, today: date) -> CheckResult: ...
```

Job kinds stay per module (`awp.readiness`, `testing.readiness`); the registry filters checks by subject; the Phase 2
checks add `subjects = {"awp.IWP"}` (one line each); `documents_current` declares both.

## 6. Issue engine API (I1, consumed by I2 calibration impact, I3 NDE rejects, I7 raise-from-view)

```python
# tl_mod_quality/issues/api.py
def raise_issue(uow, *, kind: Literal["NCR","CAR","QSR"], title: str, against: Sequence[str],
                owner: str | None, source_record: str | None, by_module: bool = False) -> str: ...
def link_affected(uow, issue_id: str, record_ids: Sequence[str]) -> int: ...   # bounded MAX_AFFECTED
def open_issues_for(conn, record_id: str) -> list[IssueRef]: ...               # viewer-filtered
# IssueRef = (issue_id, key, kind, status, due_on)
```

## 7. Reserved identifiers, job kinds, settings keys

- Sources: `sync:`, `guest:`, `mapping:`; correlation prefixes `sync:<command_id>`, `model:<revision_id>`,
  `nde:<report_no>`; link sources `mapping`, `context` (system, `by_module`).
- Job kinds: `piping.nde_select`, `testing.readiness`, `models.ingest`, `models.convert`, `models.slice`,
  `models.context`, `sync.merge`, `quality.escalation`.
- `platform.yaml` keys (wave 0, one gated change): `quality.calibration.block_mode` (hard | soft, default hard),
  `quality.issue.response_days` (14), `quality.issue.escalation_levels`, `piping.welder.continuity_days` (180),
  `piping.nde.penalty_count` (2), `testing.certificate.signers` (1), `auth.reauth_window_minutes` (15),
  `sync.max_offline_days` (14), `numbering.offline.mode` (provisional | reserved), `models.slice.max_ifc_mb` (50),
  `models.ingest.max_ifc_mb` (2048), `models.ingest.max_objects` (500000), `guest.link.ttl_hours` (72),
  `guest.link.otp` (false).

## 8. External-party scope on the viewer (I8; ADR at wave 0)

`Viewer` gains `party: str | None` (set from the account's party binding when the role is `external`). `hidden_sql`
for such a viewer hides every record whose class is not `internal` and every record whose `party_id` column (module
records that have one) or `references` link to the party's `correspondence.Party` record, directly or through one
`belongs_to` hop, does not name the party. `hidden_event_streams`, `filter_events` and the thread visibility follow
without change because they call `hidden_sql`. The walking tests gain the reader `external (party P)` beside the five
of ADR-0016.
