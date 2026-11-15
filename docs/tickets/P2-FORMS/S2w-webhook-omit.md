# P2-FORMS S2w: a webhook body never carries a never-in-webhook slot (SR-X1 F3)

kind: piece (security, core)  branch: p2/forms-s2w-webhook  worktree: /home/user/wt/forms/s2w  base: p2/ip@8fc6ca62

## Goal
A webhook body in `delta` and `full` never holds an event slot the schema marks `tl:webhook: omit`. The slot is removed
(absent, not null) for every subscriber whatever the clearance. `thin` is unchanged (no detail).

## Mechanism
- Annotation `tl:webhook: omit` on an event payload slot (`schema/core/annotations.yaml` documents it; same pattern as
  `tl:valid_time`). Annotation only: no event shape change, compat stays additive.
- Catalog generator (`tl_schema/generators/catalog.py`) writes `webhook_omit: [slots]` into `catalog/index.json` (only when
  non-empty). Envelope schemas and samples are left whole: relaxing `required` for `heading`, `form_fields`, `changes`
  would remove 3 lines from the compat baseline (not additive); reported, not done.
- `tl_schema.catalog.webhook_omit(event_type)` reads it; `tl_core.webhooks.envelope.without_omitted` applies it, called by
  `Dispatcher._detail` and by `build_envelope` (so a caller that passes no detail cannot leak).

## Marked slots
`answers` on `Submission.DraftSaved` and `Submission.Submitted`; `on_behalf_of_claim` on `IntakeItem.Accepted`;
`form_fields` on `Template.Created`; `changes` on `Template.Edited`; `heading` on `IntakeCode.Issued`.

## Allowed paths
- `schema/modules/forms/events.yaml` (annotation lines only), `schema/core/annotations.yaml` (doc line)
- `packages/tl-schema/src/tl_schema/{catalog.py,catalog_types.py,generators/catalog.py}`, regenerated `generated/**` (`just gen`)
- `packages/tl-core/src/tl_core/webhooks/{dispatch.py,envelope.py}`
- `packages/tl-modules/forms/tests/test_webhook_answers.py` (byte-identical copy of `provided/S2w_test_webhook_answers.py`)
- `packages/tl-core/tests/test_webhook_omit.py` (create); `docs/reports/P2-FORMS/S2w.md`

## Tests
1. Provided `test_webhook_answers.py` (6 cases: two events x thin, delta, full; fails 4/6 before).
2. `test_webhook_omit.py`: an annotated slot on any event is dropped in delta and full, key absent, nothing nulled; untagged
   event unchanged; thin has no detail; catalog lists the six slots; lint: the tag sits only on attributes of event classes
   (`tl:event_type`), never on a class, a shared slot or a non-`omit` value.
3. Regression: WHR tests, envelope and wiring tests, catalog and generate tests, compat.

## Gate
`just check`; `just gate packages/tl-modules/forms/tests packages/tl-core/tests/webhooks...` (webhook tests listed in the
report); `just gate packages/tl-schema/tests/test_generate.py`; `... test_compat.py`; `just gate-pg
packages/tl-modules/forms/tests/test_webhook_answers.py`. Mutation: sentinel plus at most 4 (ignored in full, nulled, thin
leak, delta only).

## Sec row
Webhook body: form answers, a sender's unverified name and company, template text and the intake heading never leave the
ledger through a webhook, at any mode or clearance. Hidden looks like never present (key absent).
