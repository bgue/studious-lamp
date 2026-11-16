# Report — P2-IP-F4

Branch: `p2/ip-f4-webhook-scenario`   Commit(s): `b6202c3b` (scenario table), then the schema-fix commit (last in git log)
Status: BLOCKED (contract gate red: 3 tests; see Open questions). compat, generate and openapi checks green.

## Deviations
- Ruling applied: `schema/modules/quality/events.yaml`, `Inspection.Verified.verified_on` range `datetime` -> `date`. Regenerated with `just gen`; generated changes are two files (`catalog/schemas/Inspection.Verified.v1.json`, `catalog/asyncapi.json`, format `date-time` -> `date`).
- Ruling 13: `packages/tl-schema/compat/event-schemas.json` added to Allowed paths. Only the `Inspection.Verified` entry was removed and `--update` rewrote it (diff: 1 line, `format` date-time -> date). Diff stat: `1 file changed, 1 insertion(+), 1 deletion(-)`.
- Ruling 13: scenario extended with 8 forms rows (16 event types). Rows are `world.append` of sample payloads, the same way as the QR/INSP/PTW rows; they do not go through the forms command handlers.

## Scan of date-only fields (`schema/modules/{quality,permits,qr,forms}/events.yaml`)
Only one field matched (date-only description, `range: datetime`):
- `Inspection.Verified` / `verified_on`: `datetime` -> `date` (fixed)
Checked, not changed: `published_on`, `retired_on`, `planned_on`, `due_on`, `scheduled_for`, `submitted_on` (no range, string); `expires_on` (already `date`); timestamps (`at`, `valid_until`, `done_at`, etc.). The record fields `planned_on`/`scheduled_for` are `pattern`s, not datetime.

## Changed files
- `schema/modules/quality/events.yaml` — `verified_on` range `date`
- `packages/tl-schema/compat/event-schemas.json` — `Inspection.Verified` v1 `verified_on` format
- `tests/webhooks/scenario.py` — 8 forms rows
- `packages/tl-schema/src/tl_schema/generated/catalog/schemas/Inspection.Verified.v1.json` — generated
- `packages/tl-schema/src/tl_schema/generated/catalog/asyncapi.json` — generated

## Commands and output
```
$ uv run python -m tl_schema.compat --check
event schemas are additive over the baseline
$ uv run python -m tl_schema.generate --check
generated files are up to date (1071 files)
$ just gate tests/contract/test_webhook_catalog_contract.py
part 1: exit 1, 3 failed, 4 passed in 674.75s (0:11:14)
FAILED ...::test_the_scenario_delivers_every_event_type_of_the_catalog   (Submission.DraftDiscarded missing)
FAILED ...::test_every_delivered_body_validates_against_the_catalog_schema_of_its_type
FAILED ...::test_delivered_facts_match_the_ledger
gate: FAIL
(earlier, before ruling 13: ruff format/check, pyright, openapi --check exit 0,
 quality gate 221 passed PASS, test_generate 8 passed PASS)
```

## Open questions / Blocked
1. Catalog and handler conflict (escalation trigger): `Template.Created` `form_fields` is `required: true` in `schema/modules/forms/events.yaml` but `tl:webhook: omit`. Delivered bodies drop it, so every delivered `Template.Created` fails its catalog schema ("'form_fields' is a required property"). Scenario cannot fix this. Needs a schema decision (drop `required`, or drop `omit`), outside this ticket's paths.
2. `Submission.DraftDiscarded` is not delivered to the thin subscription although its row is appended. Cause not found; not guessed. Check the enqueue filter in `packages/tl-core/src/tl_core/webhooks/dispatch.py` (~line 366-386).
3. Gate note: the `test_delivered_facts_match_the_ledger` failure is the `form_fields` mismatch (`Right contains form_fields`), same as item 1.
