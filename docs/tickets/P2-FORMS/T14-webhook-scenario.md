# P2-FORMS-T14 — Webhook contract scenario delivers the Permit, Checklist, Inspection, QR and forms events

Status: ready
Tier: haiku
Kind: ticket
Review: full
Labels: tests, tl-schema (generator, generated output)
Depends on: S2 and S2w merged (on `p2/ip` @f137cca7)
Branch: `p2/forms-t14-webhook-scenario`
Worktree: harness-created under `/home/user/wt/forms/t14` (from `p2/ip` head)

## Goal
`tests/contract/test_webhook_catalog_contract.py` passes again on `p2/ip`. Two causes, one ticket:
(A) `tests/webhooks/scenario.py` never delivers the events of `permits`, `quality.Checklist`, `quality.Inspection`, `qr` and
`forms` (pre-existing since the PTW, INSP and QR merges; the DEFERRED row). (B) once forms events are delivered, the schema
test fails for three events: S2w removes the `tl:webhook: omit` slots from `delta` and `full` bodies, but the generated envelope
schema still lists them in `data.detail.required`. The ledger payload schemas stay as they are.

## Brief references (pasted)
Precedent: `docs/tickets/P2-WAVE1/T01-merge-pins.md` section C (awp rows added to the scenario table). `MODULE_STREAMS` is a tuple of
`(record type, defining event, follow-on events)`; the scenario appends `Record.Created`, then each event with the catalog's sample
payload (`payload_of`) on one stream per record type. The projectors update by id and do not check workflow order.
Catalog events not yet in the table (the thin subscription must hear each one):
- `quality.Checklist`: `Checklist.Created`; then `Edited`, `Published`, `Retired`.
- `quality.Inspection`: `Inspection.Planned`; then `Scheduled`, `ResultRecorded`, `Verified`, `Cancelled`.
- `permits.Permit`: `Permit.Requested`; then `Approved`, `Rejected`, `Issued`, `Revalidated`, `Suspended`, `Resumed`, `HandedBack`,
  `Closed`, `Cancelled`, `Lapsed`, `IsolationLinked`, `IsolationUnlinked`.
- `permits.Isolation`: `Isolation.Applied`; then `Verified`, `Removed`. `permits.GasTest`: `GasTest.Recorded`.
- `qr.ScanCode`: `ScanCode.Issued`; then `Revoked`.
- `forms.Template`: `Template.Created`; then `Edited`, `Published`, `Retired`.
- `forms.Submission`: `Submission.DraftSaved`; then `DraftDiscarded`, `Submitted`, `Accepted`, `Returned`, `Voided`.
- `forms.IntakeCode`: `IntakeCode.Issued`; then `Revoked`. `forms.IntakeItem`: `IntakeItem.Received`; then `Accepted`, `Rejected`, `Purged`.
Event names are as in `schema/modules/<m>/events.yaml` (check the exact spelling there).

## Interfaces (verbatim from repo)
`packages/tl-schema/src/tl_schema/generators/catalog.py`:
```python
def _envelope_schema(
    defs: dict[str, Any], event_type: str, version: int, payload_schema: dict[str, Any]
) -> dict[str, Any]:
    ...
    detail = copy.deepcopy(payload_schema)
# called at line 164:  envelope_schema = _envelope_schema(envelope_defs, event_type, version, payload_schema)
# `omit` (the slots tagged tl:webhook: omit) is computed at line 153, before that call
```

## Context (read these, nothing else)
- `tests/webhooks/scenario.py` (the table around lines 196-320, `PROJECTABLE`, `PARENTS`, `KEEP_INTERNAL`)
- `packages/tl-schema/src/tl_schema/generators/catalog.py` (lines 140-235)
- `packages/tl-schema/tests/test_catalog.py` (where a pin is added)
- `docs/tickets/P2-WAVE1/T01-merge-pins.md` (section C only)
may explore: `schema/modules/{permits,quality,qr,forms}/events.yaml` (event names, payload slots)

## Allowed paths
- `tests/webhooks/scenario.py`
- `packages/tl-schema/src/tl_schema/generators/catalog.py` (part B: pass `omit` in and drop those slot names from `detail["required"]`)
- `packages/tl-schema/src/tl_schema/generated/**` (`just gen` output only)
- `packages/tl-schema/tests/test_catalog.py` (one test)
- consequential pins only: a test outside these paths that breaks only because the scenario now has more events or the three
  envelope schemas lost a required entry (`tests/parity/test_webhooks_parity.py`, `packages/tl-tui/tests/test_domain_plain.py`):
  update the count or list, name each in the report
- `docs/reports/P2-FORMS/T14.md` (create)

## Steps
1. Part B first: in `_envelope_schema` remove each `omit` slot from `detail["required"]` (keep it in `properties`). Run `just gen`.
   Only the envelope schemas of events that have an `omit` slot change (`Template.Created`, `Template.Edited`,
   `IntakeCode.Issued` at least). `schema/**` and the ledger payload schemas must not change.
2. Add to `test_catalog.py` one test: for every event with `webhook_omit` in the catalog index, the envelope's `data.detail.required`
   holds none of those slots and the payload schema of the same event still requires the ones it required.
3. Part A: add the rows to `MODULE_STREAMS` under comments `# permits (P2-PTW)`, `# quality (P2-INSP)`, `# qr (P2-QR)`,
   `# forms (P2-FORMS)`. If a sample names a record that must exist or an id that is not a ULID, add an override to
   `PROJECTABLE` (as `MTOLine.Defined` does) and say so in the report. The scenario helper `stream_of` takes indexes up to 99.
4. Never weaken a test, delete a row or skip an event. If an event cannot be produced by the table's generic mechanism, stop and
   write Blocked naming it and the error line.

## Acceptance
```
NODE_OPTIONS=--max-old-space-size=6144 just check
just gate tests/contract/test_webhook_catalog_contract.py packages/tl-schema/tests/test_catalog.py
```
Expected: `just check` exit 0 (no drift, compat clean); the gate ends `gate: PASS`. Do not run the whole suite. Parity
(`just gate-pg tests/parity/test_webhooks_parity.py`) once, because the scenario is shared.

## Tests to add
- `packages/tl-schema/tests/test_catalog.py`: the one test of step 2. Scenario rows are covered by the existing contract test.

## Report requirements
Standard report (`docs/templates/haiku-report.md`): first line deviations or none; the events added, every `PROJECTABLE` override,
every pin changed with old and new count, the three (or more) envelope schemas that changed.

## Escalation triggers
- `just check` reports a compat failure, or `schema/**` would have to change.
- An event cannot be delivered through the generic mechanism, or a projector refuses a sample.
- A schema test fails for a reason other than a required omitted slot.

## Amendment 1
Orchestrator rulings, extra allowed paths: (1) `schema/modules/quality/events.yaml:441` `Inspection.Verified` sample `verified_on`
becomes a valid date-time (sample only; additive compat; `just gen`). (2) `Submission.Draft` (a stream prefix in `cards.py`) goes
into `NOT_EVENTS` in `packages/tl-schema/tests/test_catalog.py`; `cards.py` unchanged. (3) `tests/contract/test_webhook_catalog_contract.py::
test_delivered_facts_match_the_ledger` compares delivered detail with the ledger payload minus `catalog.webhook_omit(type)`.
(4) gate-pg parity run as its own background task after the sqlite gates pass.

## Blocked
(implementer writes here)

## Decision
(supervisor or orchestrator writes here)
