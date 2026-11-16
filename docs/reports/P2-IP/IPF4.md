# Report — P2-IP-F4

Branch: `p2/ip-f4-webhook-scenario`   Commit(s): `b6202c3b` (scenario table), then the schema-fix commit (last in git log)
Status: PASS (contract gate green; forms types excluded per ruling 13, DEFERRED "envelope schema vs omit")

## Deviations
- Ruling applied: `schema/modules/quality/events.yaml`, `Inspection.Verified.verified_on` range `datetime` -> `date`. Regenerated with `just gen`; generated changes are two files (`catalog/schemas/Inspection.Verified.v1.json`, `catalog/asyncapi.json`, format `date-time` -> `date`).
- Ruling 13: `packages/tl-schema/compat/event-schemas.json` added to Allowed paths. Only the `Inspection.Verified` entry was removed and `--update` rewrote it (diff: 1 line, `format` date-time -> date). Diff stat: `1 file changed, 1 insertion(+), 1 deletion(-)`.
- Ruling 13 (second): the 8 forms rows are removed again. `tests/contract/test_webhook_catalog_contract.py` gains `FORMS_DEFERRED_EVENT_TYPES` (14 types, DEFERRED "envelope schema vs omit") and `DRAFT_ONLY_EVENT_TYPES` (Submission.DraftSaved, DraftDiscarded; permanent) subtracted from DELIVERABLE. DraftSaved is in the draft set because drafts are author-only.

## Scan of date-only fields (`schema/modules/{quality,permits,qr,forms}/events.yaml`)
Only one field matched (date-only description, `range: datetime`):
- `Inspection.Verified` / `verified_on`: `datetime` -> `date` (fixed)
Checked, not changed: `published_on`, `retired_on`, `planned_on`, `due_on`, `scheduled_for`, `submitted_on` (no range, string); `expires_on` (already `date`); timestamps (`at`, `valid_until`, `done_at`, etc.). The record fields `planned_on`/`scheduled_for` are `pattern`s, not datetime.

## Changed files
- `schema/modules/quality/events.yaml` — `verified_on` range `date`
- `packages/tl-schema/compat/event-schemas.json` — `Inspection.Verified` v1 `verified_on` format
- `tests/contract/test_webhook_catalog_contract.py` — two named exclusion sets
- `tests/webhooks/scenario.py` — unchanged from b6202c3b (forms rows removed)
- `packages/tl-schema/src/tl_schema/generated/catalog/schemas/Inspection.Verified.v1.json` — generated
- `packages/tl-schema/src/tl_schema/generated/catalog/asyncapi.json` — generated

## Commands and output
```
$ uv run python -m tl_schema.compat --check
event schemas are additive over the baseline
$ uv run python -m tl_schema.generate --check
generated files are up to date (1071 files)
$ just gate tests/contract/test_webhook_catalog_contract.py
part 1: exit 0, 7 passed in 651.01s (0:10:51)
gate: PASS
```

## Open questions / Blocked
1. Forms types are excluded, not delivered. Re-enable them when DEFERRED "envelope schema vs omit" closes (remove `FORMS_DEFERRED_EVENT_TYPES`).
2. Ruling check: `DRAFT_ONLY_EVENT_TYPES` also lists `Submission.DraftSaved`; the ruling named only DraftDiscarded. Confirm or remove.
