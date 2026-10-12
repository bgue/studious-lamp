# Increment plan — P1-I1 M2 Standards registry, numbering patterns, Tag/TagClass

Status: in-progress
Supervisor session: 2026-10-12
Brief sections: §6.4 (standards registry), §6.3 (value lists, enforcement), §8 (numbering), §9 M2, §27.3 and §27.5 (effective schema, change classes), §29.6 and §29.8 (legacy loads, module definition of done), §5.4 (current state), §7 (links)
Branch: `p1/i1` (base: the trunk merge of P1-I0, `d6e3afc`)
Decisions: ADR-0008 (Phase 1 owner decisions), ADR-0009 (authentication), ADR-0010 (module record storage, accepted 2026-10-12)

## Objective
Build the company "holding zone" (§6.4) as the first module, `engineering`: code lists with `value_list_policy` and
crosswalks, mnemonics, numbering patterns that validate and parse keys, units of measure, and the `Tag` and `TagClass`
records whose class drives the mandatory property sets. It is also the first module of Phase 1, so it sets the shape every
later module follows: how a module's record types are stored, how its tables and events are generated, and how the
platform learns about it (ADR-0010).

## Demo
`just demo P1-I1` (SQLite and Postgres). The commands a person types:
```
tl login demo                                 # password demo; the registry is admin-only
tl standards load schema/fixtures/standards/co.acme.standards@1.0.0.yaml
tl tag create --project P123 47-FV-1001 --class ControlValve
tl tag create --project P123 47-XX-1          # refused: the mnemonic XX is not registered; the sequence must have 4 digits
tl tag show --project P123 47-FV-1001         # segments area 47, mnemonic FV, sequence 1001; class; non-conformant: valve_data is required
```
Then: a project adds a value to an extensible list with a crosswalk and a closed list refuses it; a bulk import shows
new, changed and removed tags before it applies them; a rename leaves the old tag superseded with a `supersedes` link;
the tag register and the reports show the tags by class, status and missing property sets.

## Design decisions (supervisor, this increment)
| ID | Decision | Why | Where |
|---|---|---|---|
| D1 | A module record is a row of `cur_core_record` plus a row of the module's own table, joined on `id` (ADR-0010). | Links, psets, workflow, queries, the feed and the outbox all read `cur_core_record`; keeping module records out of it would cost a second code path in each. | `docs/adr/0010-module-record-storage.md` |
| D2 | A module reaches the core through the entry point group `throughline.modules` and a `ModuleSpec`; generators read `schema/modules/<m>/module.yaml`. | `tl_core` cannot import a module. | `tl_core/modules.py`, `tl_schema/modules.py` |
| D3 | The registry is made of ledgered records in `company` scope: `engineering.CodeList`, `Mnemonic`, `NumberingPattern` (all in `cur_engineering_standard`, told apart by `kind`) and `engineering.CodeValue` (`cur_engineering_code_value`). Tag classes are `engineering.TagClass`. | Each entry needs an owner, effective dates, supersession and history, which records give for free. | `schema/modules/engineering/` |
| D4 | Record keys: `CL:<code>@<version>`, `MN:<code>@<version>`, `NP:<code>@<version>`, `CV:<list>.<code>@<version>`, `TC:<code>`. A new edition is a new record that supersedes the old one. | Unique per scope; the edition is visible in the key. | handlers (T03, T07) |
| D5 | A tag's number is its record key. Its typed columns (`area`, `mnemonic`, `sequence`, all segments, the pattern used, `number_status`, `violations`) are in `cur_engineering_tag`. `title` is the service description. | The register and reports need typed segments; links and the feed need the key. | `schema/modules/engineering/tag.yaml` |
| D6 | A class binds property sets by name (`TagClass.required_psets`). `tl_core.modules.ModuleSpec.bound_psets` tells the core which; `evaluate`, `validate_psets`, forms and pset writes take the bound names. The effective schema and its hash do not change. | Needs no edit to the committed company packages (their hashes are pinned by many tests), and keeps `applies_to` about record types. | `tl_schema/conformance.py`, `tl_core/services/psets.py` |
| D7 | A bound pset with no values is the issue `class_required` at the pset's enforcement (`required` gives non-conformant). Property rules (`required_in_states`) follow as before. | The brief says the class makes the pset mandatory; the demo shows that at creation, before any state rule applies. | `tl_schema/conformance.py` |
| D8 | Registry writes (`tl standards ...`, `DefineTagClass` ...) are admin-only; tag writes are for any signed-in user. | ADR-0008 has two roles; the registry is company data. | CLI `require_admin`; API action override (T09c) |
| D9 | Module events use the `tl.core.` CloudEvents prefix and are catalogued with the core ones. The webhook contract scenario writes one stream per module record type. | One catalog, one delivery path. | `schema/modules/engineering/events.yaml`, `tests/webhooks/scenario.py` |
| D10 | Dates in module tables are ISO text (`YYYY-MM-DD`), not the `date` column type. | No `date` column exists in the core; Postgres would return `date` objects where SQLite returns text. | `schema/modules/engineering/*.yaml` |
| D11 | Tag numbers are typed in, not allocated (`allocate: false` in the fixture's pattern). Registry patterns with `allocate: true` use the Phase 0 allocator through `numbering_for(conn)`. | Engineers take tag numbers from the P&ID; the allocator still serves patterns that want it. | `tl_core/numbering/config.py` |
| D12 | The registry code lists `MaterialCode` and `FailAction` mirror the lists of the pset package. Feeding pset value lists from the registry is a follow-up. | The package lists are what pset validation uses today. | follow-ups |

## Supervisor-built pieces (in order)
| # | Piece | Why supervisor-tier | Reviewer | Status |
|---|---|---|---|---|
| S1 | ADR-0010; `tl_core.modules` (`ModuleSpec`, discovery, `use_modules`); `default_registry` hook; `create_module_record`; `numbering_for`; generators for `schema/modules` (DDL, event catalog); scaffold of `packages/tl-modules/engineering`; webhook contract scenario | Core interface and generator core (01-tiers §3); orchestrator review | orchestrator | done |
| T02 | `schema/modules/engineering/*.yaml`: `Standard`, `CodeValue`, `TagClass`, `Tag` and ten event payload classes; generated DDL and catalog | Schema, human gate (ADR-0008 decision 6) | orchestrator | done |
| S3 | Four projectors, `registry.py` reads, `errors.py`, `document.py` (the standards document), tests | Projection correctness; they are the base of every ticket | reviewer | done |
| S5 | Class binding in `tl_schema` (`psets_for`, `bound` in `validate_psets`, `record_json_schema`, `form_metadata`, `evaluate`) and in the pset, workflow and conformance services | Conformance semantics (01-tiers §3: schema semantics) | orchestrator | done (hook wired; the engineering hook comes with T08) |
| S4 | Code-list service (T04): resolve, crosswalk, `value_list_policy` enforcement | Policy semantics | reviewer | done |
| T05 | Pattern engine: segment-level parse and diagnosis, registry patterns, allocator wiring | Numbering (01-tiers §3) | orchestrator | done |
| T06 | Tag commands: create, reclassify, rename, split, merge; the `engineering.tag` workflow | Invariants across several streams | reviewer | done |
| T08 | The engineering `bound_psets` hook; conformance on tag events | Conformance semantics | orchestrator | done |
| S13 | Demo `dev/demos/P1-I1.sh`, module spec pages, runbook, package READMEs, report | Closing | — | planned |

## Tickets
| ID | Title | Tier | Depends | Status | Outcome |
|---|---|---|---|---|---|
| T01 | Standards fixture `schema/fixtures/standards/co.acme.standards@1.0.0.yaml` | H (schema label, data only) | S3 | merged | first attempt; placeholder Area labels accepted as sample data |
| T07 | TagClass commands: define, revise, close | H | S3 | merged | first attempt |
| T10a | Tag-list mapping template and CSV reader | H | S3 | merged | first attempt; follow-ups done by the supervisor: text-only key columns, duplicate headers |
| T10b | Import diff: new, changed, unchanged, removed, invalid | H | S3 | merged | first attempt |
| T03 | Registry commands (`RegisterCodeList`, `AddCodeValue`, `RegisterMnemonic`, `RegisterNumberingPattern`, `Close*`); the loader (`load_standards`) follows as a supervisor piece | H | S4 | ready | |
| T09a | `tl standards` CLI (admin) | H | T03 | planned | |
| T09b | `tl tag` CLI (create, show, ls, reclassify, rename, split, merge) | H | T06, T08 | ready | |
| T09c | API routes, command table and MCP read tools for standards and tags | H | T06, T08 | planned | |
| T09d | TUI: tag register grid, tag record view (segments, class, missing psets) | H | T09c | planned | |
| T10c | Import apply (`tl tag import`) with diff preview | H | T06, T10a, T10b | planned | |
| T11 | Reports: summary by class and state, missing mandatory psets, pattern violations (module functions and `tl tag report`) | H | T08 | ready | |
| T12 | Simulator tag-list actor; legacy mapping template `dev/seed/templates/tag-list-instrument-index.yaml` | H | T10c | planned | |

Haiku-ability notes. T01 touches `schema/**` (a fixture, data only); it carries the `schema` label and the delegated
approver below, and a provided test pins its content. Every other ticket passes the checklist (01-tiers §6) after the
supervisor writes the stub and the test that fix its interfaces.

## Order of work
1. Round 1: S1, T02, S3, S5; dispatched T01, T07, T10a, T10b (all passed first time, merged).
2. Round 2 (this one): S4, T05, T06, T08 built; dispatch T03, T09b, T11.
3. Round 3: the standards loader (supervisor, needs T03), then T09a (`tl standards`), T09c (API and MCP), T10c (import apply).
4. Round 4: T09d (TUI), T12 (simulator and legacy template).
5. Last: S13, gates (`just check`, `just test`, `just test-parity`, `just test-tui`), demo on both databases, report.

## Brief coverage map (L-P0-I8E-3)
| Brief item | Where |
|---|---|
| §6.4 mnemonics and abbreviations | `Mnemonic` records; fixture; T03 |
| §6.4 tag/document/line numbering conventions as parseable patterns | `NumberingPattern` records; T05 |
| §6.4 code lists (disciplines, areas, document types, NDE methods, weld types, crafts, units) | `CodeList` and `CodeValue`; fixture (T01). Status codes, gasket types, piping classes, test media, punch categories: later modules add their lists as editions of the same fixture |
| §6.4 units of measure and conversions | `UnitOfMeasure` list with UCUM code and dimension; conversion factors are follow-ups |
| §6.4 owner, effective dates, supersession links, project adoption status | columns on the tables; supersession by `*.Closed`; adoption policy per entry; per-project adoption status is a follow-up (P1-I8 impact reports) |
| §6.4 code lists follow `value_list_policy` and crosswalk rules | S4, T03 |
| §9 M2 `Tag`, `TagClass`, `Standard` | T02, T06, T07, T03 |
| §9 M2 class determines mandatory psets | S5, T08 |
| §9 M2 bulk import with diff preview | T10a, T10b, T10c |
| §9 M2 property values carry source provenance | the import writes `source=import:<job>` and the file's row number into the event; document revision provenance comes with the derivation pipeline (P1-I3) |
| §9 M2 rename/split/merge with `supersedes` links | T06 |
| §27.5 constraining class change flags existing tags, rewrites nothing | live conformance by `bound_psets`; reports T11 |
| §29.8 module definition of done | see below |

### Module definition of done (§29.8) for `engineering`
| Item | Plan |
|---|---|
| LinkML reviewed, artefacts current, tables generated | T02, `just gen`; lake tables: the module's tables are not mirrored in the lake in this increment (follow-up) |
| Workflows, required psets, file slots, spatial paths | Tag workflow YAML in T06; required psets by class (D6); file slots: none in M2; spatial context: not used |
| TUI screens, forms, API, MCP, webhooks | T09c, T09d; webhooks by the catalog (D9) |
| Merge policies, settings keys, expected links | merge policies are Phase 3 sync work: none declared; settings: none; expected links: none in M2 |
| Base reports | T11 |
| Simulation actors | T12 |
| Legacy mapping template | T12 |
| Parity, contract, snapshot, permission and restore tests | parity: every module test uses the parity fixtures; contract: the webhook scenario; snapshots: T09d; permission: admin-only registry (CLI and API tests); restore: a rebuild-equals-incremental test in S13 |

## Risks and escalation triggers
- ADR-0010 is accepted (2026-10-12) on one condition: the generated wide view `v_<module>_<class>` must exist before the first consumer that needs a flat per-type row (P1-I8 lake marts, or any report or grid that would hand-write the join). T11 reports must read through `registry.py` joins or this view, never a new ad hoc join.
- `schema/fixtures/standards/` adds a data directory the package registry ignores (it reads `*.yaml` at the top level only). If a later change makes the registry recurse, the fixture would be read as a package and fail.
- The class binding changes what `conformance` means for a record with a class. Existing core record tests are unaffected (no module, no binding); the Tag path is covered by T08.
- Escalate to the orchestrator: any change to a `tl_core` interface that another workstream uses; a change to what `ModuleSpec` offers once P1-I2 has started; anything in `04-gates.md` §2 beyond the delegated schema approvals.

## Schema approvals requested (ADR-0008 decisions 6 and 7a)
| Path | Class | Ticket |
|---|---|---|
| `schema/modules/engineering/module.yaml`, `standard.yaml`, `code_value.yaml`, `tag_class.yaml`, `tag.yaml`, `events.yaml` | additive (a new module) | T02 |
| `schema/core/annotations.yaml` | additive (documents the annotation `tl:record_types`) | S1 |
| `schema/fixtures/standards/co.acme.standards@1.0.0.yaml` | additive (a new fixture) | T01 |

## Blocked / Decision
(none)
