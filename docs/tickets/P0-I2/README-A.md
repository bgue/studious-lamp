# Increment plan — P0-I2 workstream A: Schema packages, effective schema, psets, conformance

Status: in-progress
Supervisor session: 2026-10-09
Brief sections: §6.3, §6.4, §27.1–§27.5, §5.4, §5.1 (event model)
Branch: `p0/i2a` (integration branch `p0/i2`; trunk `claude/wizardly-allen-m2v96s`). Fanout: `docs/tickets/P0-I2/FANOUT.md`.

## Objective
A company standard pset package with enforcement (`co.acme.engineering@3.2.0`), a project extension (`x.P123@1.4.0`) and a project
custom pset package (`prj.P123@1.0.0`) load from `schema/fixtures/`, compile into a hashed effective schema, and drive: JSON Schema
validation, form metadata, a conformance evaluator (`ok / warning / nonconformant / waived`), a `SetPsetValues` command that emits
`Pset.ValuesSet` carrying `effective_schema_hash`, a `cur_pset_values` long-form projection and promoted columns for `materialize: true`
properties, and the CLI commands `tl schema hash|lint|validate` and `tl pset set|get`. Out of scope: schema registry as ledgered
`SchemaPackage` records, publish/adopt workflow, classification and impact reports (§27.4–§27.5), enrichment and source psets (read-only
layers; no writer exists), workflow-state evaluation (records have no state until Increment 3), the query language.

## Demo (workstream B owns the increment demo; these are WS-A's contributions)
```
tl schema hash P123                          # 64-hex content hash; edit a fixture, run again, the hash differs
tl schema lint                               # one L004 warning on the fixtures
tl schema validate                           # ok company ..., ok project:P123 ...
tl init ; tl record create --project P123 --key V-0001 --title "Valve 1"
tl pset set --project P123 V-0001 valve_data size_in=4 manufacturer=Acme
tl pset set --project P123 V-0001 valve_data --custom fat_witness_by=client
tl pset get --project P123 V-0001            # psets, effective_schema_hash, conformance
```

## Supervisor-built pieces (in order)
| # | Piece | Why supervisor-tier | Reviewer | Status |
|---|---|---|---|---|
| T02 | Package models (`packages.py`), pset compilation and the "projects cannot" rules (`compile.py`), LinkML rendering (`linkml_render.py`), fixtures | Effective-schema compiler and package merge (`01-tiers.md` §3); `schema/**` | Orchestrator | built (55 compile tests) |
| T03 | Effective schema model and hash (`effective.py`), composition and adoption filter, conformance settings, cache by hash (`compose.py`) | Effective-schema compiler | Orchestrator | built |
| T05 | Conformance evaluator (`conformance.py`) | Conformance rules are Sonnet-authored by rule (`01-tiers.md` §3); the plan's "H (rules pasted)" fails Haiku-ability item 5 | Orchestrator | built on `p0/i2a-t05-conformance` (22 tests); merges after T04, which provides the validator it calls |
| T07 | `PsetProjector` (`cur_pset_values`, `psets_json` merge, promoted columns), `tl:table` generator extension, `schema/core/psets.yaml` | Projector transaction rules, DDL generator (§5.4) | Orchestrator | built (27e2e54; 18 tests) |
| — | Schema provider (`schema_provider.py`), `form_metadata` and `conformance` services (`psets.py`), error types | Glue over T01, T04b and T05 | Orchestrator | built (d4feec7) |

## Tickets
| ID | Title | Tier | Depends | Status | Outcome |
|---|---|---|---|---|---|
| T01 | Package registry: parse, load, versions, adoption, checks | H | models | merged | pass, 1 round; six adoption interpretations confirmed (A17) |
| T02 | Compile psets, enforce the "cannot" rules | S | T01 interface | built | |
| T03 | Effective schema, hash, cache | S | T02 | built | |
| T04 | JSON Schema per record type and psets validator | H | T03 | merged | pass, 1 round; empty-enum follow-up fixed by the supervisor (A18) |
| T04b | Form metadata from the effective schema (added) | H | T03 | merged | pass on attempt 2 (attempt 1 committed its report file) |
| T05 | Conformance evaluator | S (plan: H) | T03, T04 | merged | 23 tests green on the real validator |
| T06 | `SetPsetValues` handler and `Pset.ValuesSet` | H | T04, T05, T07 | ready | round 2 |
| T07 | `PsetProjector`, `cur_pset_values`, promoted columns | S | T03 | built | |
| T08 | `tl schema hash|lint|validate` | H | T01, T08a | ready | round 2 |
| T08a | Lint rules (added; split from T08) | H | T03 | merged | pass, 1 round; context gap: the ticket did not list `schema/fixtures` |
| T08b | `tl pset set|get` (added; split from T08) | H | T06, T08 | planned | |
| T09 | Fixture-driven matrix: every row of the §6.3 "projects can / cannot" table | H | T06 | planned | |
| T10 | `Schema.EffectiveChanged` event and hot-reload hook | H | T03, T07 | ready | round 2 |

Haiku-ability (`01-tiers.md` §6): T01, T04, T04b, T08a ship a provided test file plus a precise specification, touch two files each, and
avoid every row of the Sonnet-authored table (the conformance rules, which T04 only feeds, are T05). T06 writes layer-aware
validation for one command against a pasted rule table; it passes item 5 because the permission-like rules are schema semantics
(locked, custom section, read-only layers), not auth. T08 and T08b are CLI wrappers; the rules they call exist. Anything that fails a
check is split (T08 became T08, T08a, T08b; T04b was added because form metadata did not fit the plan's T04) or built by the supervisor.

## Design decisions taken by the supervisor (within the plan's scope)
| # | Decision | Why |
|---|---|---|
| A1 | Packages are a constrained YAML subset (`packages.py`), compiled to LinkML on demand | §27.1 allows "a constrained subset authored as YAML"; the §6.3 example is not raw LinkML. Extra keys are forbidden, so "rename, remove, retype" cannot be written |
| A2 | `EffectiveSchema` (pydantic) is the runtime representation; the LinkML view (`linkml_render.py`) is a derived artefact for lint and export. The hash is SHA-256 over the canonical JSON of the model plus a digest of the committed core JSON Schema | Enforcement, required states and value-list policy are not LinkML or JSON Schema; one model feeds validation, forms and conformance. Deviation noted in FANOUT risk list (custom sections compile to `ValveData_P123_x`, as §27.3) |
| A3 | Always-required is `required_in_states: ["*"]` (`ALWAYS`); the package field `required: true` is sugar for it | `FieldMeta` (frozen contract) has no `required` flag. WS-B must read `["*"]` as "required in every state" |
| A4 | A pset is *engaged* for a record when its `applies_to` matches and the record has a value in it, or when the pset is `mandatory` with no `class_filter`. Missing-property rules apply to engaged psets only | `class_filter` cannot be evaluated before the query language; without engagement every `core.Record` would be flagged for `valve_data` |
| A5 | `Pset.ValuesSet` payload is `pset, layer, values, effective_schema_hash` plus `conformance` (status after the write) and `units` (unit by key). The projector reads only the payload | Projectors must be deterministic (no registry lookups); the brief's payload list is a minimum |
| A6 | `tl_core.schema_provider` supplies the effective schema to the three fixed-signature services; default directory `TL_SCHEMA_DIR` or `schema/fixtures` | The signatures in `psets.py` carry no registry |
| A7 | Fixture psets apply to `core.Record` (the only Phase 0 type) instead of `ed.Tag`; `class_filter` is parsed and kept, not evaluated; `fat_witness_by` is a string, not `Party` | No such types exist yet |
| A8 | Conformance mode, lenient end date and waivers are declared in a project package (`conformance:`), not ledgered records | Ledgered waivers need the registry and approvals (later increments); the evaluator reads the same data either way |
| A9 | Promoted columns are named `pset__<pset>__<property>` and added to `cur_core_record` by generated `ALTER TABLE` DDL; names may not contain `__`. Existing rows are backfilled from `psets_json` | `cur_core_record` is generated from core LinkML; promotion is runtime (§5.4, §27.7) |
| A10 | `cur_pset_values` comes from a LinkML class in `schema/core/psets.yaml` with `tl:table: cur_pset_values`; the generator learns `tl:table` | The brief names the table `cur_pset_values`; the generator derives `cur_core_pset_value` otherwise |
| A11 | T05 is supervisor-built; T04b, T08a, T08b are additions | See Haiku-ability notes |
| A13 | Hash content: the resolved psets (properties, constraints, code-list values with labels, crosswalks and `meaning` IRIs, enforcement, adoption, custom-section limits), packages and versions, conformance settings and waivers, and the core digest. Not hashed: code-list descriptions, unused code lists, package titles and descriptions | Meaning is append-only (§27.1): editing a value's meaning must change the hash; text that no runtime reader sees must not |
| A14 | Ruling (orchestrator): pset engagement (A4) stays for Phase 0. Class-filter evaluation needs a record class, which arrives with Tag/TagClass in P1-I1 (T08 class binding); follow-up there. Known Phase 0 gap: a valve with `psets={}` reports `ok` | Recorded in the report |
| A15 | Ruling (orchestrator): lenient mode downgrades required-ness only. A missing value for a `required` or `locked` property becomes a warning; type, range, pattern, value-list and locked-extension violations stay at their enforcement level in every mode, and waivers are the tool for them | They are data or governance errors, not enforcement levels |
| A16 | Reserved names: psets `x`, `prj`, `enrich`, `src`; property `x`. `required_in_states` containing `*` covers every state (one helper, `states_cover`/`required_in`, for compiler and evaluator). A `json` property keeps a dict value as one `cur_pset_values` row; an empty dict leaves a row | The projector classifies paths by those markers and depth |
| A17 | T01 interpretations confirmed: the highest version is taken among the project's own documents; "those documents" are the ones chosen by that rule; a pin to a stored non-company package is skipped by `adopted` and reported by `check`; a pin to an unstored version raises `PackageError` from `adopted`; an error with no location reads `(document)`; `load_package` also wraps read and decode errors; `projects()` returns the distinct non-null `project` values. Tests: `test_registry_pins.py` | The reviewer found them consistent with the ticket |
| A18 | An enum property with no values is unconstrained in JSON Schema (no `"enum": []`), and the compiler rejects a code list without values | An empty list would reject every value |
| A19 | Schema provider: change detection hashes file bytes (a same-size edit in one mtime tick is noticed; touch alone is not a change). `reload()` compares against what the previous `reload()` reported, so an edit that `effective()` noticed first is still reported, and it is all-or-nothing. A project scope with no project packages uses the company effective schema composed for that scope (orchestrator ruling; the scope is in the hash). A malformed scope raises `InvalidScopeError`, a `ServiceError`. `effective_by_hash` exists on the directory provider | Review of d4feec7/00291bd |
| A12 | JSON Schema is generated from `EffectiveSchema` directly, not by the LinkML generator | The LinkML generator cannot express the policy annotations and would lose layer information; the LinkML view stays for lint and export |

## Order of work (relay rounds)
| Round | Ticket batch | Supervisor work in the same turn |
|---|---|---|
| 1 | T01, T04, T04b, T08a | Plan; T02, T03; fixtures; provided tests; T05 (side branch); T07; `schema/core/psets.yaml` |
| 2 | T06, T10, T08 (round 2 supervisor work done: merges, provider, services, tickets) | Merge round 1 and T05; provider; `form_metadata` and `conformance` services; handler hooks |
| 3 | T08b, T09 | Merge round 2; READMEs, AGENTS.md; learnings |
| Final | — | Gates, report `docs/reports/P0-I2-A.md` |

## Risks and escalation triggers
- SchemaView merge of packages cannot express `x.` sections: handled by `ValveData_P123_x` classes (A2); not an escalation.
- A change to `forms.py` or the `psets.py` signatures: stop with BLOCKED; WS-B depends on them.
- `schema/**` beyond `psets.yaml` and fixtures (this plan also edits `schema/core/annotations.yaml` and `core.yaml`, both entailed by `psets.yaml`): listed under SCHEMA_APPROVALS.
- Postgres: promoted-column `ALTER` and `ON CONFLICT` upserts are not executed on Postgres in this increment (parity arrives in P0-I5); the SQL is dialect-neutral.

## Known gaps recorded for later increments
- A waiver is dropped silently when other issues remain: `ConformanceReport` has no waived list (contract field). Follow-up for P1-I8 (waiver records).
- `class_filter` is not evaluated (A14); `conformance` on a row updates only on pset writes, not when the schema changes.

- §27.3 "records being edited keep validating against the schema they were opened with" needs a by-hash lookup in the services and the TUI; `DirectorySchemaProvider.effective_by_hash` exists, the wiring is a follow-up for P0-I4 (live TUI).

## Blocked / Decision
(none)
