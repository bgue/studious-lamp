# Report — P2-IP-F4

Branch: `p2/ip-f4-webhook-scenario`   Commit(s): `b6202c3b` (scenario table), then the schema-fix commit (last in git log)
Status: BLOCKED on one gate (`tl_schema.compat --check`); the contract test fails only for forms event types

## Deviations
- Ruling applied: `schema/modules/quality/events.yaml`, `Inspection.Verified.verified_on` range `datetime` -> `date`. Regenerated with `just gen`; generated changes are two files (`catalog/schemas/Inspection.Verified.v1.json`, `catalog/asyncapi.json`, format `date-time` -> `date`).
- Compat guard is red because of that change (see Blocked). I did not edit `packages/tl-schema/compat/event-schemas.json` (not in Allowed paths; `--update` refuses).

## Scan of date-only fields (`schema/modules/{quality,permits,qr,forms}/events.yaml`)
Only one field matched (date-only description, `range: datetime`):
- `Inspection.Verified` / `verified_on`: `datetime` -> `date` (fixed)
Checked, not changed: `published_on`, `retired_on`, `planned_on`, `due_on`, `scheduled_for`, `submitted_on` (no range, string); `expires_on` (already `date`); timestamps (`at`, `valid_until`, `done_at`, etc.). The record fields `planned_on`/`scheduled_for` are `pattern`s, not datetime.

## Changed files
- `schema/modules/quality/events.yaml` — `verified_on` range `date`
- `packages/tl-schema/src/tl_schema/generated/catalog/schemas/Inspection.Verified.v1.json` — generated
- `packages/tl-schema/src/tl_schema/generated/catalog/asyncapi.json` — generated

## Commands and output
```
$ uv run ruff format --check tests/webhooks/scenario.py
1 file already formatted
$ uv run ruff check tests/webhooks/scenario.py
All checks passed!
$ uv run pyright tests/webhooks/scenario.py
0 errors, 0 warnings, 0 informations
$ uv run python -m tl_schema.generate --check
generated files are up to date (1071 files)
$ uv run python -m tl_schema.compat --check
Inspection.Verified v1: payload.verified_on: format changed 'date-time' -> 'date'
non-additive schema change: events are never changed, only added to
exit=1
$ uv run python -m tl_api.openapi --check
exit=0
$ just gate tests/contract/test_webhook_catalog_contract.py   (before the compat question; run after the schema fix)
part 1: exit 1, 1 failed, 6 passed in 651.43s (0:10:51)
FAILED tests/contract/test_webhook_catalog_contract.py::test_the_scenario_delivers_every_event_type_of_the_catalog
gate: FAIL
   (test_every_delivered_body_validates_against_the_catalog_schema_of_its_type: PASS after the fix)
$ just gate packages/tl-schema/tests/test_generate.py
part 1: exit 0, 8 passed in 331.77s (0:05:31)
gate: PASS
$ just gate packages/tl-modules/quality/tests
part 1: exit 0, 221 passed in 82.00s (0:01:22)
gate: PASS
```
Scenario diff on the failing test (pytest `-l`): the extra items in the catalog set are exactly 16 forms types: IntakeCode.Issued, IntakeCode.Revoked, IntakeItem.Received, IntakeItem.Accepted, IntakeItem.Rejected, IntakeItem.Purged, Submission.DraftSaved, Submission.DraftDiscarded, Submission.Submitted, Submission.Returned, Submission.Accepted, Submission.Voided, Template.Created, Template.Edited, Template.Published, Template.Retired. No non-forms type is missing.

## Learnings (proposed)
- `dev/gate.sh` prints only the summary; use `uv run pytest <file> -k ... -p no:logging -l --tb=short` to see the set diff. `-vv` still truncates the set diff here.
- The compat guard treats any format change in a merged event version as non-additive, even for events with no stored data. A ruling that says "not on trunk" does not reach it; it needs an explicit baseline decision.

## Open questions / Blocked
1. `tl_schema.compat --check` is red: `Inspection.Verified` v1 `verified_on` format changed `date-time` -> `date`. The baseline `packages/tl-schema/compat/event-schemas.json` (outside Allowed paths) still records `date-time`, and `compat --update` refuses. Decision needed: (a) orchestrator approves a baseline refresh for this event (needs the path added to Allowed paths), or (b) another fix. I have not guessed.
2. Forms event types (16, listed above) are not appended by the scenario. Per ticket, this is the finished state; the forms events follow after the integration merge.
