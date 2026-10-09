# Report — P0-I2 workstream A: Schema packages, effective schema, psets, conformance

Written 2026-10-09. Branch `p0/i2a` (integration branch `p0/i2`), plan `docs/tickets/P0-I2/README-A.md`. The increment demo and the increment report belong to workstream B.

## Outcome
Objective met: yes. Exit criteria owned by A:
| Criterion | Evidence |
|---|---|
| `tl schema hash P123` prints a stable content hash; changing a package changes it | `tests/test_compose.py` (hash stable, order independent, changes with description, tightening, version, order, value meaning), `packages/tl-cli/tests/test_cli_schema.py` |
| `Pset.ValuesSet` carries `effective_schema_hash` | `tests/services/test_pset_commands.py::test_sets_standard_values_and_emits_one_event`; `tl pset set` / `tl pset get` |
| Missing advisory property gives `warning`; missing required-in-state property gives `nonconformant` | `test_a_missing_advisory_property_shows_a_warning`, `test_a_required_in_state_property_is_nonconformant_in_that_state`, `tests/test_conformance.py` |
| Every row of the §6.3 "projects can / cannot" table has a test | `tests/schema/test_projects_can_cannot.py` (29 cases, real provider, handler and evaluator) |
| `tl schema hash|lint|validate|reload` and `tl pset set|get` work | `packages/tl-cli/tests/test_cli_schema.py`, `test_cli_schema_reload.py`, `test_cli_pset.py`, `test_cli_pset_errors.py` |

Demo commands (workstream B wires them into `just demo P0-I2`):
```
tl schema hash P123 ; tl schema lint ; tl schema validate
tl init ; tl record create --project P123 --key V-0001 --title "Valve 1"
tl pset set --project P123 V-0001 valve_data size_in=4 manufacturer=Acme
tl pset set --project P123 V-0001 valve_data --layer custom x.fat_witness_by=client
tl pset get --project P123 V-0001
```

## Tickets
| ID | Outcome | Review rounds | Notes |
|---|---|---|---|
| T01 package registry | merged | 1 | Six adoption interpretations confirmed (A17) |
| T02 pset compilation, fixtures | merged (supervisor-built) | orchestrator review, 4 findings fixed | Rule code for every "projects cannot" row |
| T03 effective schema, hash, cache | merged (supervisor-built) | orchestrator review | Meaning in the hash; cache rejects un-hashed schemas |
| T04 JSON Schema and validator | merged | 1 | Empty enum made unconstrained; empty code list rejected (A18) |
| T04b form metadata (added) | merged | 2 attempts | Attempt 1 only committed its report file |
| T05 conformance evaluator | merged (supervisor-built; plan said H) | orchestrator review | Lenient mode relaxes required-ness only (A15) |
| T06 `SetPsetValues` handler | merged | 1 | Supervisor later made `None` unset a property (A20) |
| T07 pset projector, `cur_pset_values`, promoted columns | merged (supervisor-built) | orchestrator review | `tl:table` generator extension |
| T08 `tl schema hash|lint|validate` | merged | 1 | Supervisor added `reload` |
| T08a lint rules (added) | merged | 1 | |
| T08b `tl pset set|get` (added) | merged | 1 | Supervisor wrapped `get` in the error handler |
| T09 matrix | taken over (supervisor) | orchestrator review | Tests-only ticket written directly to save a relay round |
| T10 `Schema.EffectiveChanged` and hook | merged | 1 | |

No ticket hit the two-strikes rule. Taken over: T09 (planned). Abandoned: none. Dispatch rounds: 4 (T01, T04, T04b, T08a; T06, T08, T10; T08b), plus relays for review fixes.

## Gates
| Gate | Result |
|---|---|
| `just check` | green on `p0/i2a` |
| `just test` | green 627 passed |
| Projection determinism (`tests/property -k projection`) | green; pset replay tests added (set, unset, set) |
| `just test-parity`, `just test-tui` | not applicable to workstream A (no adapter or screen change) |
| Schema classification (`tl schema classify`) | not run: not built (§27.8 later); approvals listed below |

## Deviations from plan
Decisions A1 to A22 in `docs/tickets/P0-I2/README-A.md`. The ones a reader must know:
- T05 and T09 done by the supervisor; T04b, T08a, T08b added; T08 split.
- Fixture psets apply to `core.Record` and `class_filter` is parsed but not evaluated (A7); a valve with `psets={}` reports `ok` until class binding arrives with P1-I1 (A14).
- Conformance mode and waivers are declared in a project package, not ledgered records (A8); a waiver that drops an issue while others remain is not visible because `ConformanceReport` has no waived list (follow-up for P1-I8).
- `required_in_states: ["*"]` means required in every state (A3); `FieldMeta` has no required flag.
- `None` in `SetPsetValues.values` unsets a property (A20, orchestrator ruling).

## Escalations and decisions
- Orchestrator: engagement rule kept for Phase 0 (A14); lenient mode semantics (A15); null-unsets (A20); locked values are clearable (A22); a project without packages gets the company schema re-scoped (A19).
- Review findings fixed: `states_cover` for `*`, value meanings in the hash, cache rejects un-hashed schemas, locked-pset guard test, reserved names and json dict storage, provider content signature, all-or-nothing `reload()`, `InvalidScopeError`.
- No unresolved *Blocked* entries.

## Open product questions
- Should values in a `locked` pset be non-clearable (A22)? Today clearing is a data edit.
- Clearing the last value of an optional pset hides its missing required properties, because a pset is engaged only while it holds a value (A4, A22).

## Learnings
Appended: L-P0-I2-1 to L-P0-I2-5 (importlib-mode conftest and pyright with partly typed libraries; rendering the effective schema as LinkML; the stub, provided-test and reference-implementation method; `ruff format` and `type: ignore`; runtime column promotion and payload-carried derived facts). Implementer proposals declined: none. Accepted for later tickets: list `schema/fixtures` in lint tickets' Context (T08a), name `<name@version>` in messages the tests assert (T01).

## Docs
- Package `README.md` and `AGENTS.md`: `packages/tl-schema`, `tl-core`, `tl-cli` updated. `tl-adapters` unchanged. `tl-tui` is workstream B's.
- Runbook: `docs/runbooks/schema-package-change.md`; `docs/runbooks/rebuild-projections.md` notes that `core_record` and `pset_values` rebuild together.
- Annotation tags documented in `schema/core/annotations.yaml`. Implementer reports: `docs/reports/P0-I2/`. Generated docs: nothing under `generated/` was edited by hand.

## Schema approvals requested
`schema/core/psets.yaml`, `schema/fixtures/co.acme.engineering@3.2.0.yaml`, `x.P123@1.4.0.yaml`, `prj.P123@1.0.0.yaml` (delegated); `schema/core/annotations.yaml` (tag documentation) and `schema/core/core.yaml` (one import) as entailed changes.

## Follow-ups filed
- P0-I4 (live TUI): wire `DirectorySchemaProvider.effective_by_hash` so records being edited keep validating against the schema they were opened with (§27.3).
- P1-I1: class binding for `class_filter`; engagement by class instead of by value.
- P1-I8: waiver records and a waived list in the conformance report.
- Re-evaluate stored `conformance` when the effective schema changes (today it updates on pset writes; `tl_core.services.psets.conformance` is the live answer).
- Postgres parity (P0-I5): promoted-column `ALTER`, `cur_pset_values` and the unset path are written dialect-neutrally but only executed on SQLite.
- Performance: `PsetProjector` rebuilds a record's `cur_pset_values` rows on every pset event and introspects columns each time; fine at Phase 0 scale, revisit in the 100k-record pass.
- `uv.lock` changed (pyyaml for tl-schema, tl-schema for tl-cli): run `uv lock` when integrating with workstream B.

## Cost notes
Seven implementer runs for seven tickets plus one retry (T04b false alarm); reviewer runs on each ticket and three supervisor-piece reviews. Supervisor effort went to the compiler and rules (T02, T03, T05), the projector (T07), and reference implementations used to verify every ticket specification before dispatch.
