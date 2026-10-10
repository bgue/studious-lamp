# Increment plan: P0-I8 workstream B, extension record type registry v0

Status: in-progress
Supervisor session: 2026-10-10
Brief sections: §31 (extension record types), §27.3 and §27.4 (effective schema, package lifecycle), §6.3 (psets), §30 (settings, for the last ticket)
Branch: `p0/i8b` (worktree `/home/user/wt/p0-i8b`), based on `p0/i8`; fanout plan `docs/tickets/P0-I8/FANOUT.md` (decisions D7 to D11 bind this workstream)

## Objective
A company, project or partner can add a record type by putting a package of files in a directory, without a release or a schema change. `tl types sync <root>`
validates each package (layout, `type.lock`, LinkML lint, compile into the effective schema, examples, form, workflow and settings files), registers it with one
ledger event, or quarantines it with a report, and does nothing the second time. A registered type is a generic record type: `CreateRecord.record_type =
"co.acme.SafetyObservation"` works, its index fields are pset values the query language filters, and the API, the MCP read tools, the CLI and the TUI list it. A
managed type keeps its body in the ledger; an object-backed type keeps it in the object store as a content-addressed document that is hash-verified on every read,
with a mismatch quarantined. Editing the files of a registered version is a conflict that is reported and never takes the registration away; a change ships as a new
version.

## Demo
```
just demo P0-I8-B
```
`dev/demos/P0-I8-B.sh` (written last): a scratch ledger and object store; `tl types sync schema/fixtures/types` registers the two example packages and a second run
prints `up to date`; one package is broken (`examples/bad.json`) and quarantined with its issue; `tl types ls`, `show`; a `SafetyObservation` and a `LiftPlan` are
created (the lift through the API, with its body) and found by `psets.co_acme_lift_plan.risk_class:high`; the lift's object is damaged and the next read is refused and
the record quarantined; `tl types quarantine ls` shows it; storing the body again heals it; the MCP tools list the types and `create_record` proposes.

## Published for other workstreams and increments
| Surface | Where | Notes |
|---|---|---|
| Contract (frozen) | `tl_core/extypes/types.py` | unchanged. `store_body` gained one optional keyword, `expected_version`, in the implementation |
| Registry | `tl_core.extypes.registry` | `scan`, `sync`, `list_types`, `get_type`, `versions_of`, `current_type`, `usable_types`, `list_quarantined`, `deprecate_type` |
| Validator | `tl_core.extypes.validate` | `validate_package`, `describe_package`, `read_settings` (returns `SettingDefinition`s for the last ticket) |
| Compiler | `tl_core.extypes.compile` | `compile_type`, `to_package_doc`, `body_schema`, `body_issues` |
| Bodies | `tl_core.extypes.body` | `store_body`, `create_extension_record`, `load_body`, `read_body`, `recheck_body`, `body_pointer`, `list_body_quarantine` |
| Forms | `tl_core.extypes.forms`, `service.type_detail` | `type_form` gives every slot of a type, grouped by `form.yaml`; `TypeDetail` is what the API and MCP return |
| Schema provider | `tl_core.extypes.provider.attach(factory)` | call it once where a process opens its ledger; done for the CLI root, `create_app`, `build_server` and `EmbeddedClient` |
| Events | `TypeRegistration.Registered\|Quarantined\|Deprecated`, `Record.BodyStored` | catalog classes in `schema/core/extension.yaml` |
| Tables | `cur_core_type_registration`, `cur_core_record_body`, `tl_body_quarantine` | the third is operational, a rebuild never clears it |
| Errors | `tl_core.extypes.errors` | eight classes, rows in `tl_api/errors.py` |
| API / MCP context | `ApiContext.objects`, `create_app(object_store=)`, `McpContext.objects`, `build_server(object_store=)` | the store that holds bodies |

## Decisions
| # | Decision |
|---|---|
| B1 | **A package is real LinkML.** `type.yaml` imports `throughline/core/extension` and declares a class that is_a `ExtensionRecord` (new, `schema/core/extension.yaml`). The compiler lints it with the LinkML linter (error level) and reads it with `SchemaView`, both on a private temporary copy of `schema/core` so the import resolves without a repository path in the package. Annotations: `tl:storage_mode` (class), `tl:index` and `tl:kind` (slot), documented in `annotations.yaml`. |
| B2 | **A registered type enters the effective schema as a `PackageDoc`** of kind `company`, named for the type, with one pset (adoption `mandatory`, `applies_to` the type name). Form metadata, JSON Schema, conformance and `SetPsetValues` then work with no change. `DirectorySchemaProvider` takes an optional `ExtensionSource`; with none attached, or no types, every effective-schema hash is what it was. A type that cannot compose (a pset-name clash that arrived later) is left out, not the whole scope. |
| B3 | **The pset is named for the type**: `<namespace with dots as underscores>_<snake_case(Name)>`, so `co.acme.LiftPlan` is `co_acme_lift_plan` (a pset path has one segment). Two types that give the same name conflict: the second is quarantined with a `conflict` issue. The namespaces `core`, `tl` and `throughline` are reserved. |
| B4 | **What is in the pset.** Managed: every slot, written as `Pset.ValuesSet` events after `Record.Created`, so values carry conformance and the schema hash like any write. Object-backed: the index fields only, copied from the body in the unit of work that stores it; writing them directly (`SetPsetValues`, `UpdateRecord` with `psets`) is refused (`body_not_allowed`), because they are copies. |
| B5 | **Versions are immutable.** `sync` compares the files' content hash with the registry row (decision table in `registry.py`). Same hash: nothing. New hash on a quarantined row: validate again. New hash on an `active` or `deprecated` row: a `Quarantined` event with a `conflict` issue; the projection keeps the registration and records `conflict_hash` and the report. Reverting the files re-registers (clearing the note). A refused change is reported once. |
| B6 | **The files stay where they are and are verified when loaded** (`TypeLoader`): the directory must exist, hash to the registered `content_hash` and compile to the registered `schema_hash`. Otherwise the type is *unavailable*: it leaves the effective schema and takes no new instances, existing records stay readable, and it comes back when the files do. Compiled types are cached by those hashes. No compiled copy is stored, so a registered package must stay in place (v0, `file://` only). |
| B7 | **Identity.** `content_hash` is the sha256 of the canonical lock bytes (D9), of the files *as found* (so a quarantined row has a stable hash). `location_uri` is the directory's `file://` URI. `schema_hash` covers the type name, pset, storage mode and slots, not the version, so a release that changes no slot keeps the hash and older bodies stay valid. |
| B8 | **Body store (D10).** Key `records/<type>/<id>/<sha256>.json`, canonical JSON, at most 1 MiB. A new body is a new object; the old stays and `previous_hash` chains them. Storing the same body again appends nothing but re-puts the object (a non-content key is overwritten by verified bytes), which heals a damaged object. A body is validated before anything is put or appended. `store_body` takes an optional `expected_version` so an editor holding an old version gets a 409 instead of a lost update. |
| B9 | **Quarantine of a body is operational state**, not an event: `tl_body_quarantine`, created next to the other tables and never cleared by a rebuild (like `wh_*`). `load_body` only reads and raises; `read_body` (the callers with a unit-of-work factory) records the quarantine in a fresh unit of work, because the failing read's own transaction ends in rollback. A quarantined record answers `BodyQuarantinedError` without touching the object until a new body is stored or `recheck_body` finds the object sound. |
| B10 | **`handle_create_record` stays the 03 §7 function.** It accepts a registered, active type; an object-backed type raises `body_required` because a record with no body is a state the registry never wants, and `create_extension_record` does both writes in one unit of work. The deprecated, unavailable and unknown cases are `type_not_active` and `unsupported_record_type`. |
| B11 | **Agents.** Reads are open. `create_record` over MCP is a proposal for a managed type and is refused for an object-backed type (a proposal carries no body; a proposable `store_body` is a follow-up). The API's two write routes are `changes_records` routes, so an `agent:` token gets `agent_must_propose`. |
| B12 | **Discovery is polling (D8).** `watch` compares per-package signatures (file sizes, mtimes, the lock bytes) every interval and syncs on a change. The schema provider asks the database for a cheap token at most once a second (and at once after this process registers something), so a `tl types sync` in another process shows up within a second. |
| B13 | **Not in v0** (recorded as follow-ups): directory-backed storage and external `incoming/` writers (D11); signing `type.lock` on publish (D9); a change-classification gate between versions of one type (§27.5: additive, constraining, breaking); `workflow.yaml` is validated but not yet loaded into the workflow registry; proposable `store_body`; bucket events. |
| B14 | **A ledger made before this change has no registry tables.** The source treats any failure to read them as "no types", so nothing else breaks; `tl init` (idempotent) adds the tables. |

## Supervisor-built pieces (in order)
| # | Piece | Why supervisor-tier | Reviewer | Status |
|---|---|---|---|---|
| S20 | `schema/core/extension.yaml`, annotations, event catalog classes, generated output, test and webhook-scenario updates | schema (delegated approval) | orchestrator | done |
| S21 | Package model: `names`, `lock`, `model`, `compile`, `validate`, the example packages `co.acme.LiftPlan` (object-backed) and `co.acme.SafetyObservation` (managed) | effective-schema compiler and conformance rules (`01-tiers.md` §3) | fresh reviewer, then orchestrator | done |
| S22 | Registry: projectors, `sync` (idempotence, conflicts), `deprecate_type`, `TypeLoader`, `LedgerExtensionSource` and the `DirectorySchemaProvider` hook, `CreateRecord` and pset guards, wiring in the CLI root, `create_app`, `build_server`, `EmbeddedClient` | effective-schema integration, a shared handler | fresh reviewer, then orchestrator | done |
| S23 | Body store: `store_body`, `load_body`, `read_body`, quarantine, `create_extension_record` | hash-verified load, a security-relevant rule (§31.4) | fresh reviewer, then orchestrator | done |
| S24 | `type_form`, `type_detail`, the polling watcher, API error rows, `ApiContext.objects`, `McpContext.objects` | contracts the tickets share | | done |
| S25 | Stubs and provided tests for T20 to T22, with scratch reference implementations | scaffolds | | done |

## Tickets
| ID | Title | Tier | Depends | Status | Outcome |
|---|---|---|---|---|---|
| P0-I8-T20 | `tl types sync\|ls\|show\|validate\|lock\|deprecate\|watch` (23 provided tests) | haiku | S22, S24 | merged | pass, 1 round; supervisor fix S29: `sync` prints `conflict` for a refused edit (orchestrator ruling) |
| P0-I8-T21 | API: `/types`, `/types/{ref}`, `POST /types/{name}/records`, `GET\|PUT /records/{id}/body` | haiku | S23, S24 | merged | pass, 1 round, no findings |
| P0-I8-T22 | MCP: `list_record_types`, `get_record_type`, `get_record_body`, `tl://types` resources | haiku | S23, S24 | merged | implementation passed; provided test corrected by supervisor (pyright: `assert row is not None`) |

Later rounds (tickets written when their dependencies are merged): `ApiClient` and `RemoteClient` type and body methods; the `ClientInterface` growth and fakes (supervisor), then the TUI grid
for a type and the generated form with `form.yaml` hints; `tl types quarantine ls\|recheck`; the runbook; cross-surface parity tests; the demo; and, once WS-A is merged, registering a
package's `settings.yaml` through `tl_core.settings.register_definitions`.

## Order of work
1. Round 1 (this one): plan, schema, S21 to S25, tickets T20 to T22; DISPATCH.
2. Round 2: merge T20 to T22; client plumbing (S, then tickets), TUI, quarantine command.
3. Round 3: runbook, parity tests, demo, report; after WS-A merges, the settings ticket.

## Risks and escalation triggers
- The schema provider is process-wide and shared by every workstream. The hook is additive and inert without `attach`; a test double provider is never touched. Escalate if WS-A needs to change `DirectorySchemaProvider` too.
- `just test` has one failure that is not this workstream's: `test_every_event_type_the_code_names_is_in_the_catalog` names `Setting.Changed` and `Setting.Locked`, which WS-A adds to the catalog.
- A registered package must stay on disk (B6). A deployment that moves the directory needs an `s3://` location, a follow-up.
- Escalate for: a change to `Command`, `Event`, `UnitOfWork`, `Projector` or `ObjectStore`; any permission rule for who may register a type or write a body (human gate: v0 applies the mechanism only, ADR-0005); the settings registration if A's `register_definitions` differs from `settings/types.py`.

## Blocked / Decision
Review of S20 to S24 (orchestrator, fresh context): changes-requested, 1 high, 2 medium, 3 low. Fixed in S26 (base merge, NOT_EVENTS) and S27 (H1 imports confined to the package and `validate_package` never raises; M2 the loader re-verifies each second; M3 retry once on a lost race; L4 hidden files locked, `__pycache__` refused; L5 one read per package; L6 `registry.deprecate` bumps after the commit and a reverted conflict on a deprecated version clears; patterns capped at 200 characters). Follow-up: full ReDoS hardening of package patterns (a short pattern can still backtrack).
