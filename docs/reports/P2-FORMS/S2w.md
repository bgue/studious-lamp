# P2-FORMS-S2w report

Deviation: none outside the spec. Envelope schemas and samples are NOT relaxed (see Open).

## Done
- Annotation `tl:webhook: omit` (documented in `schema/core/annotations.yaml`) on six slots in
  `schema/modules/forms/events.yaml`: `answers` (DraftSaved, Submitted), `on_behalf_of_claim` (IntakeItem.Accepted),
  `form_fields` (Template.Created), `changes` (Template.Edited), `heading` (IntakeCode.Issued). Annotation only.
- Catalog generator writes `webhook_omit` into `catalog/index.json` (only when non-empty); `tl_schema.catalog.webhook_omit`
  reads it. `tl_core.webhooks.envelope.without_omitted` removes the keys (absent, not null); `Dispatcher._detail` and
  `build_envelope` both call it, so a caller that passes no detail cannot leak. Same for every subscriber and clearance.
- Thin is unchanged (no detail). `data.changes` carries no forms slot (forms events have no `event_changes` branch).
- Tests: provided `test_webhook_answers.py` byte-identical (6/6 now); `packages/tl-core/tests/test_webhook_omit.py` (6): tagged
  slot dropped in delta and full on any event (monkeypatched tag), untagged unchanged, thin, the six catalog slots, lint that
  the tag sits only on attributes of `tl:event_type` classes with value `omit`.

## Gate (.gate/summary.txt)
check PASS; forms tests + omit + WHR + envelope + wiring + payload_refs 82 passed; test_generate 8; test_compat 18;
gate-pg answers test 12; gate: PASS. An earlier wide run (add tests/confidentiality, tests/contract) 217 passed, 2 failed:
the omit lint (my test bug, fixed, rerun green) and `test_webhook_catalog_contract::test_the_scenario_delivers_every_event_type_of_the_catalog`
(the scenario never delivers Permit, Checklist and forms events; merged earlier, not touched here). The contract's schema
validation test passed.

## Mutation
sentinel (omit set emptied) killed; 4/4 targeted killed: nulled instead of removed, thin leaks detail, ignored in full,
ignored in delta (both paths bypassed). No survivors.

## Open
1. Envelope schemas still list `heading`, `form_fields`, `changes` as required and the catalog samples show the omitted
   slots. Relaxing `required` makes compat flag it only after `just compat-update`, which removes 3 baseline lines; not done.
   Decision for orchestrator. (Dropping the properties instead is flagged by compat as removed.)
2. The catalog contract scenario failure above needs its own piece.
3. `data.record` (full) is the record projection; not checked for answers (forms projections hold no answers, S2).

## Sec row
A webhook body, any mode or clearance, never carries form answers, a sender's claimed name and company, template text or an
intake heading; hidden looks like never present.
