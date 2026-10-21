# P1-UX-S3 — Example property sets, record-type titles, generated type labels

Status: draft
Tier: sonnet
Kind: piece
Review: full
Labels: schema, tests
Depends on: —
Branch: `p1/ux-s3-fixture-psets-and-labels`
Approver (schema): the owner approved the example sets on 2026-10-21 (orchestrator records APPROVALS). The
`title` annotations on module classes and the generated labels file are additive display metadata and are covered by
the same approval (decision Q2, answered in r2); the `95` line still lists the paths.

## Goal
The fixture company standard has example property sets for documents, RFIs and correspondence; every record-type
class has a human `title`; `just gen` emits `TYPE_LABELS` so the TUI shows `Control valve`-style names. Demo
ledgers carry values so the Properties tab has something to show.

## Brief references (pasted, abridged)
> SCOPE clause 4: in `schema/fixtures/co.acme.engineering@*`: `document_data` for documents (originator, area,
> system, confidentiality note, native file format, review due); `rfi_data` for RFIs (location or grid line,
> drawing reference, trade, cost estimate with currency, schedule impact days); `correspondence_data` for
> correspondence (contract clause, other party's reference number, response required by, delivery method). Labels
> and units on every property; at least one `required` and one with a code list per set. Additive only: no
> existing record becomes nonconformant in a way that breaks a demo or test. Seed values in the demo ledgers.
> Decision D4: edit the 3.2.0 file in place. Decision D3: LinkML `title` on every record-type class; generated
> `type_labels.py`.

## Interfaces
Fixture shape (existing, abridged): `psets: <name>: {label, description, applies_to: [...], enforcement,
adoption, custom_section, properties: {<key>: {label, description, range, unit, required, required_in_states,
value_list_policy, minimum, maximum}}}` and `code_lists: <Name>: {value_list_policy, values: [{code, label}]}`.
`applies_to` uses record type names: `documents.Document`, `correspondence.TechnicalItem` (RFI),
`correspondence.Correspondence`, `correspondence.CommercialItem`.

New generated file `packages/tl-schema/src/tl_schema/generated/type_labels.py`:
```python
TYPE_LABELS: Final[dict[str, str]] = {"engineering.Tag": "Tag", "documents.Document": "Document", ...}
```
Built by the existing generator run from the `title:` of each class that has `tl:record_types` (or is a record
type of a module) in `schema/core` and `schema/modules/*`. Drift-checked by `just check` like the other generated
files. Core types keep their names: `core.Record` -> "Record".

## Context (≤ 10 files)
- `schema/fixtures/co.acme.engineering@3.2.0.yaml`
- `dev/demos/p1_i8_demo.py` (anchors: `version: 3.2.0\n`, `\n\n  safety_data:`, exactly one `        range: decimal\n`)
- `packages/tl-schema/src/tl_schema/generate.py` and `packages/tl-schema/src/tl_schema/generators/` (where a new
  generated file is added; follow the closest existing one)
- `packages/tl-modules/correspondence/src/tl_mod_correspondence/names.py` (record type names)
- `schema/modules/correspondence/correspondence.yaml`, `schema/modules/documents/*.yaml`,
  `schema/modules/schedule/*.yaml` (class names to title)
- `dev/seed/seed.sh` and `dev/tour/phase1.py` (how demo ledgers set pset values: `tl pset set`)

## Allowed paths
- `schema/fixtures/co.acme.engineering@3.2.0.yaml`
- `schema/modules/**` (the `title:` lines only), `schema/core/**` (titles only)
- `packages/tl-schema/src/tl_schema/generate.py`, `packages/tl-schema/src/tl_schema/generators/**`,
  `packages/tl-schema/src/tl_schema/generated/**` (by `just gen` only)
- `packages/tl-schema/tests/**` (pins that move; new test file below)
- `packages/tl-tui/tests/**` pins and snapshots that render 3.2.0: `__snapshots__/test_psets_tab_*.raw`,
  `test_new_record_form.raw`, `test_edit_form.raw`, `fakes.py`, and `test_schema_text.py` (plan check F6)
- `dev/demos/p1_i8_demo.py` (anchors only, if a new set breaks one)
- `dev/seed/**` (values only)
- `docs/reports/P1-UX/S3.md` (create)

## Steps
1. Add the three sets and the code lists they need (`DocumentFormat`, `Trade`, `DeliveryMethod`, `Currency`).
   Each set: `enforcement: advisory`, `adoption: optional`, one property `required: true` with
   `enforcement: advisory`, one property with a code list, units on numbers (`d` days; money as a decimal with a
   sibling `currency` code-list property). Do not use `required_in_states` that existing demo states would trip.
2. Prefer `range: float`/`int` to `decimal` for new numbers, or change the anchor in `p1_i8_demo.py`.
3. Add `title:` to every record-type class (list them in the report).
4. Extend the generator for `type_labels.py`; run `just gen`; commit generated output with the source.
5. Find every test that pins what 3.2.0 contains (set counts, property lists, effective-schema hashes) with
   `pytest packages/tl-schema tests/contract packages/tl-modules/schemareg packages/tl-core/tests/test_schema_provider.py -q`;
   update pins, not behaviour (L-P1-I8-4).
6. Seed: where the seed and demo scripts create documents, RFIs and correspondence, set example values with the
   existing `tl pset set`; no new command.

## Acceptance
```
just gen && just check
just gate packages/tl-schema tests/contract packages/tl-modules/schemareg packages/tl-core packages/tl-tui
just gate-pg packages/tl-schema packages/tl-modules/schemareg
bash dev/demos/P1-I8.sh
```
Expected: pass; `P1-I8.sh` still ends with its 7/7 line; no uncommitted generated drift.

## Tests to add
`packages/tl-schema/tests/test_type_labels.py`: `test_every_record_type_has_a_title` (walk the module `names.py`
RECORD_TYPES constants against `TYPE_LABELS`), `test_labels_are_plain_words` (no dot, no CamelCase),
`test_the_three_new_sets_have_labels_units_a_required_property_and_a_code_list`,
`test_the_new_sets_apply_to_the_module_record_types`, `test_an_existing_demo_record_stays_conformant_with_the_new_sets`
(an existing document without values is not `nonconformant`).

## Guards for the sentinel and targeted mutants
Sentinel: drop one `title:`. Targeted: (1) `applies_to` of `rfi_data` pointed at `core.Record` (a test must catch
it); (2) a new set made `enforcement: required` (existing records go nonconformant: the conformance test must
catch it); (3) `type_labels.py` emitted with a stale title (drift check must catch it).

## Report requirements
Standard report; list each pinned test that moved and why; list every class titled; `95` line text:
paths `schema/fixtures/co.acme.engineering@3.2.0.yaml`, `schema/modules/**` (titles), `schema/core/**` (titles).

## Escalation triggers
- A pinned effective-schema hash inside a committed generated sample (`generated/catalog/samples`) must change.
- A new set makes any existing demo or test record nonconformant and the cause is not a pin.
- The generator cannot read `tl:record_types` for a class without a core interface change.

## Blocked
(builder writes here)

## Decision
(supervisor or orchestrator writes here)
