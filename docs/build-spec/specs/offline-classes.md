# Spec: offline classes per record type (declaration and enforcement hooks)
Owner answers of 2026-10-30 and the wave-0 build plan are in `specs/wave0.md`; where they differ, `wave0.md` wins.

Status: draft v0.1, 2026-10-30, planner tier. Source: owner decision 2 (`module-designs/OWNER-DECISIONS-2026-10-30.md`);
`module-designs/deployment-and-merge.md` §4–§5; `phase3-contracts-draft.md` §3 (`tl:merge`, sync); brief §22.
Scope: the **declaration**, its **validation**, the **hooks** the Phase 3 sync layer will call, and **surfacing** on the
record screen. No sync engine, no replica, no local segment, no merge policy. Lines marked **(proposed)** go beyond the
decision and the designs.

## 1. What exists after this spec is built
- Every record type, and every core stream that is not a record, declares `offline: full | draft_only | none`:
  - `full`: created and edited offline, merged on sync;
  - `draft_only`: drafts offline; issue, number and sign happen on the authority;
  - `none`: online only.
- The table is generated from the schema, drift-checked, readable at run time, shown in technical mode on the record
  screen and served by one read route. One pure function says whether a node may capture a command, so Phase 3 has
  one place to call and nothing to decide again.

## 2. Where it is declared: a schema annotation (decision and why)
**Chosen: the class annotation `tl:offline`**, beside `tl:file_slots` and `tl:expects_link` in
`schema/core/annotations.yaml`, generated into `tl_schema.generated.offline_classes` like `type_labels.py`.
Why not a `ModuleSpec` field:
1. The owner asked for a property **of the data model**. An annotation travels with the schema: export and import of
   schema packages, the generated docs and catalog, and the schema hash a replica sends at handshake
   (`phase3-contracts-draft.md` §3), so two nodes that disagree on a type's class disagree on the hash.
2. It covers what a `ModuleSpec` cannot: `core.Record`, the core streams, and extension types (`type.yaml`, brief 31).
3. It sits beside `tl:merge` (Phase 3 contract: an annotation generated into `tl_schema.generated.merge_policies`), so
   the sync layer reads class and policy from the same generated data.
4. A change is a `schema/**` change: a human gate, which is right for a policy that decides what may be written offline.

One piece of knowledge is code, not data, and stays in the module **(proposed)**: which `user` commands count as
*drafting* for a `draft_only` type. Command names live in module code, so `ModuleSpec.offline_drafts:
Mapping[str, frozenset[str]]` (record type → command names) holds them, validated against the annotation.

## 3. The annotation and the generated table
- Class level: `tl:offline: full | draft_only | none` on every LinkML class that is a record type (resolved exactly as
  `tl_schema/generators/type_labels.py` does: `tl:record_types` on a module class, the subclass named after the type
  for a multi-type class such as `Standard`, and `core.Record`). Core streams that are not records carry it with
  `tl:stream_type: core.ActivityPost` (new tag, core classes only) **(proposed)**.
- Extension types declare it in `type.yaml` at class level (read by `tl_core.extypes` when it compiles the type);
  missing means `none` (fail closed) and the type's registration view says so.
- Generator `packages/tl-schema/src/tl_schema/generators/offline.py` writes `generated/offline_classes.py`:
```python
OfflineClass = Literal["full", "draft_only", "none"]
OFFLINE_CLASSES: Final[dict[str, OfflineClass]] = {"core.Record": "full", ...}   # record types, sorted
OFFLINE_STREAMS: Final[dict[str, OfflineClass]] = {"core.ActivityPost": "full", ...}   # non-record streams
```
  and `generated/docs/offline-classes.md` (type, label, class, one-line meaning). `OfflineClassError` when a record
  type has no `tl:offline`, a value is outside the vocabulary, or two classes give one type different values. Links,
  files, property sets and workflow state have no class of their own: they follow the record they belong to.

## 4. The classes of every existing record type
| Record type | Class | Drafting commands (`offline_drafts`) | Why |
|---|---|---|---|
| `core.Record` | full | — | Generic records: no gap-free numbering, no sign-off; a key from a pattern becomes provisional (P3-Q8) **(proposed)** |
| extension types | per `type.yaml`, default none | — | Declared by the type's package |
| `documents.Document` | draft_only | `RegisterDocument`, `UpdateDocument` | Controlled register; supersede and void are central |
| `documents.Revision` | draft_only | `CreateRevision`, `VoidRevision` | A draft revision is prepared anywhere; issue and supersede are central |
| `documents.Rendition` | draft_only | `AttachRendition` | Native, PDF and markup on site; the signed copy is a central act |
| `documents.Transmittal` | draft_only | `CreateTransmittal`, `VoidTransmittal` | Formal and numbered; issued on the authority |
| `documents.ReviewCycle` | none | — | Opened and closed on the authority; answers are short and sign-like (owner Q1) |
| `documents.DocumentSchema`, `DerivedDocument`, `ProcessingJob` | none | — | Configuration and derivation jobs run on the authority only |
| `correspondence.Correspondence` | draft_only | `DraftCorrespondence`, `UpdateCorrespondence`, `VoidDraft` | Design §4: formal correspondence is drafted offline and issued online |
| `correspondence.TechnicalItem` (RFI) | draft_only | `RaiseTechnical`, `UpdateTechnical` | Raise an RFI on site (Phase 5 mobile flow); submit, issue and answer online |
| `correspondence.CommercialItem` | none | — | Every command is a `controller` act and items are restricted by default |
| `quality.PunchItem` | draft_only | — | A walkdown raises items offline; clear, verify, reopen and void are central (P2-PUNCH) |
| `correspondence.CorrespondenceThread`, `ResponseClock`, `ContractClause`, `Party` | none | — | Clocks recompute on the authority; threads, clauses and parties are reference data |
| `engineering.Tag` | full | — | Field tagging; duplicates merge by natural key (`natural_key` policy, Phase 3) |
| `engineering.CodeList`, `Mnemonic`, `NumberingPattern`, `CodeValue`, `TagClass` | none | — | Registry: admin data, company scope |
| `schemareg.SchemaPackage`, `Adoption`, `Waiver` | none | — | Design §5.3: schema packages are online only |
| `cost.CostCode`, `CostSnapshot`; `schedule.Schedule`, `ScheduleSnapshot`, `ActivityRef` | none | — | Mirrors imported on the authority |
| `legacy.LoadRun` | none | — | Loads run on the authority |
| `requisitions.LaborRequisition` | draft_only | `RaiseRequisition` | Crew requests are raised on site and approved on the authority; approve, reject, schedule, assign and close are central acts |
| `requisitions.MaterialRequisition` | draft_only | `RaiseRequisition` | As labour: raised anywhere, approved on the authority (P2-I4A S1, as built) |
| `requisitions.GeneralRequisition` | draft_only | `RaiseRequisition` | As labour: raised anywhere, approved on the authority (P2-I4A S1, as built) |
| `requisitions.ScaffoldRequest` | draft_only | `RaiseRequisition` | As labour: raised anywhere, approved on the authority (P2-I4A S1, as built) |
| `requisitions.WorkOrder` | none | — | Online only: opened by an approval and moved (schedule, assign, start, complete, close) on the authority (P2-I4A S1, as built) |

| Core stream (not a record) | Class | Why |
|---|---|---|
| `core.ActivityPost` (feed posts), `core.Thread` (thread messages) | full | Design §5.3: posts and thread messages are field capture, append-only |
| `core.Proposal`, `core.Account` (incl. module role grants), `core.Setting`, `core.TypeRegistration`, integration streams (`core.IntegrationApp`, `Rule`, `InboundEndpoint`, `Enricher`, `ActionDefinition`, `ActionInvocation`, `EnrichmentValue`, `WebhookSubscription`) | none | Accounts, settings and integration configuration are online only (design §5.3); side effects run on the authority |

Phase 2 and later specs state the class of each type they add, with the reason (owner decision 2). Field capture types
named in the design (welds, boltup, inspections, punch, toolcrib, scaffold tags) are expected `full`.

## 5. What the core enforces now (Phase 2)
1. **Declaration**: the annotation documented in `annotations.yaml`; the generator refuses a missing or unknown value;
   `just check` fails on drift; `tl new record-type` scaffolds `tl:offline: none` with a comment asking for a reason.
2. **Validation at module load** (`tl_core.modules.load_modules`, `ModuleLoadError`): every record type of a module is
   in `OFFLINE_CLASSES`; `offline_drafts` keys are `draft_only` types the module owns; every drafting command is in
   `ModuleSpec.command_words` with the word `user` (roles spec §4); a `full` or `none` type has no drafting entry.
3. **The capture hook** (`packages/tl-core/src/tl_core/offline.py`), pure, no caller writes through it yet:
```python
NodeKind = Literal["authority", "site", "device"]
class OfflineDecision(BaseModel):
    allowed: bool
    reason: Literal["authority", "full", "draft", "online_only", "central_act", "not_drafting", "unknown_type"]
def offline_class(record_type: str) -> OfflineClass        # OFFLINE_CLASSES, then extension types; unknown -> "none"
def stream_class(stream_type: str) -> OfflineClass         # OFFLINE_STREAMS; unknown -> "none"
def capture_allowed(record_type: str, command: str, *, node: NodeKind) -> OfflineDecision
def require_capture_allowed(record_type: str, command: str, *, node: NodeKind) -> None   # OnlineOnlyError, 409 online_only
def node_kind() -> NodeKind                                # TL_NODE_KIND, default "authority"
def is_authority(scope: str) -> bool                       # True on an authority node; Phase 3 reads the scope's authority
```
   Rule of `capture_allowed`, in order: node `authority` → allowed (`authority`). Type unknown → refused
   (`unknown_type`). Command word `controller`, `admin` or `company` → refused (`central_act`): issue, approve, sign
   off and void are always central (design §4, signatures valid only over the merged hash). Class `none` → refused
   (`online_only`). Class `full` → allowed. Class `draft_only` → allowed only for a command in `offline_drafts` for
   that type (`draft`), else refused (`not_drafting`). Generic commands on a record (`AddLink`, `AttachFile`,
   `SetPsetValues`, `TransitionWorkflow`) follow the same rule with the record's type **(proposed)**.
4. **Node kind fails closed** **(proposed)**: `tl serve` and `tl tui` refuse to start with `TL_NODE_KIND` `site` or
   `device` (`NodeKindNotBuiltError`: "offline replicas arrive in Phase 3") so nobody runs a half-replica.
5. **Authority per scope** (owner decision 2): `is_authority(scope)` is the one question every later caller asks. Today
   every node is the authority of every scope it holds (single node), so it returns `node_kind() == "authority"`.
   Phase 3 replaces the body with a read of the scope's authority (a ledgered `Scope.AuthorityChanged`, design §5.2)
   without changing callers; a site server with no central node is then the authority of its project scope.
6. **Surfacing**: `GET /record-types` (action `record.read`) answers `[{record_type, label, module, offline,
   drafting_commands}]` for every type (no record data; on the walking test's no-record-data list).
   `ClientInterface.record_types()` (embedded, remote, fake). The record screen's Details tab shows, in
   **technical mode only**, `Offline class  Draft only: drafted offline, issued online` (tui-layout: technical tier).
   Plain mode shows nothing until a node can be a replica; then Phase 3 adds the `◌` provisional mark and the
   status-line refusal `Online only` from `OnlineOnlyError` **(proposed)**.

## 6. What the Phase 3 sync and merge layer will do (not built here)
- Replica identity, the local segment and `PendingCommand` (R-P3-1 ADR): the local unit of work calls
  `require_capture_allowed(type, command, node=node_kind())` before it records a pending command.
- `draft_only` creates get a provisional key; the final key is allocated on the authority at merge (P3-Q8).
- `tl:merge` policies per slot for every `full` type; the generator rule "a `full` type has a merge policy or a
  default by kind" is switched on then. A central act captured anyway (an old replica) is `Rejected` with
  `central_act`, never silently dropped.
- Confidentiality overrides the class: `restricted` and `privileged` records never replicate whatever their class
  (design §4); a pull is viewer-filtered.
- Authority per scope becomes data (`Scope.AuthorityChanged`), and side effects (webhooks, rules, enrichers, jobs)
  run only where `is_authority(scope)` is true.

## 7. Pieces and tickets
Wave 0 of Phase 2; S2 after `P2-RM-S2` (needs `ModuleSpec.command_words` filled). IDs `P2-OC-*`.
| ID | Kind | Review | Depends | Allowed paths | Tests added |
|---|---|---|---|---|---|
| S1 annotation, values, generator | piece (schema, human gate) | full | — | `schema/core/annotations.yaml`, `tl:offline` lines in `schema/core/*.yaml` and `schema/modules/*/*.yaml`, `packages/tl-schema/src/tl_schema/generators/offline.py`, `tl_schema/generate.py` (one call), `generated/offline_classes.py`, `generated/docs/offline-classes.md` | `packages/tl-schema/tests/test_offline_classes.py` (every record type of `TYPE_LABELS` has a class; missing and unknown values raise; multi-type class; output deterministic; the table of §4 pinned) |
| S2 core hook and module validation | piece | full | S1, `P2-RM-S2` | `packages/tl-core/src/tl_core/offline.py`, `tl_core/modules.py` (`offline_drafts` field, load checks), `tl_core/extypes/**` (read `tl:offline` from `type.yaml`), each `packages/tl-modules/*/src/*/module.py` (`offline_drafts` from §4), `packages/tl-api/src/tl_api/main.py` and `packages/tl-tui/src/tl_tui/main.py` (node-kind start-up check) | `packages/tl-core/tests/test_offline_capture.py` (every branch of the rule; authority always allowed), `tests/services/test_modules_offline.py` (load errors: undeclared type, drafting entry on a `full` type, `controller` command listed), `packages/tl-core/tests/extypes/test_extype_offline.py` |
| T1 read route and client | ticket | full | S2 | `packages/tl-api/src/tl_api/routes/reference.py`, `tl_api/client/records.py`, `packages/tl-tui/src/tl_tui/{client,embedded,remote}.py` and the fake, `docs/reference/openapi.json` (generated) | `packages/tl-api/tests/test_api_record_types.py`, `packages/tl-tui/tests/test_client_record_types.py` |
| T2 record screen row | ticket (tui) | full | T1 | `packages/tl-tui/src/tl_tui/details/technical.py`, `tl_tui/display.py` (class wording) | `packages/tl-tui/tests/test_details_offline_row.py` (technical shows the line; plain walk does not) |
| T3 scaffold | ticket | lite | S1 | `packages/tl-cli/src/tl_cli/new.py`, `tl_cli/scaffold/**` | `packages/tl-cli/tests/test_new_record_type_offline.py` |
| T4 docs | ticket | lite | S2 | `docs/modules/*/README.md` (one line per type), `docs/build-spec/module-designs/README.md` §3 row "Offline", `docs/templates/` module-design template (Offline class row) | none (docs) |

Mutation guards (S2): `central_act` before class; `authority` short-circuit; unknown type refused; `draft_only`
without listing refused.

## 8. Demo clauses (`just demo P2-OC`)
1. `uv run python -c "from tl_schema.generated.offline_classes import OFFLINE_CLASSES; print(len(OFFLINE_CLASSES))"`
   prints the count of record types; `just check` passes.
2. A module fixture that drops `tl:offline` from one class makes `just gen` fail with the class named.
3. `capture_allowed("documents.Revision", "IssueRevision", node="device")` → `central_act`; `CreateRevision` → `draft`;
   `("cost.CostCode", ..., "device")` → `online_only`; anything on `authority` → allowed.
4. `curl /record-types` lists `engineering.Tag` as `full`; the TUI record screen of a revision in technical mode shows
   the offline line, plain mode does not.
5. `TL_NODE_KIND=device tl serve` stops with the "Phase 3" message.

## 9. Risks
- **R1 wrong class shipped** (MD): a type declared `full` that needs central numbering. Mitigation: `controller`
  commands are central whatever the class; owner approves §4; each module spec justifies its rows.
- **R2 annotation and module drift** (LO): a renamed command leaves a stale drafting entry. Load-time validation.
- **R3 extension types default** (LO): `none` blocks a company's offline type until declared. Intended (fail closed).
- **R4 schema hash churn** (LO): adding `tl:offline` changes the schema text; no effective-schema (pset) hash changes,
  because the effective schema covers property sets only.

## 10. Owner questions
- **Q1** Approve the table of §4, in particular `core.Record` and `engineering.Tag` as `full`, renditions (markup) as
  drafting, and `documents.ReviewCycle` as `none` (reviewers cannot answer offline).
- **Q2** Is "a `controller` command is never captured offline, whatever the class" the rule you want? It makes every
  sign-off, approval, issue and void central.
