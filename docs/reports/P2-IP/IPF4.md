# Report — P2-IP-F4

Branch: `p2/ip-f4-webhook-scenario`   Commit(s): see git log (report commit is the last one)
Status: BLOCKED (the gate is red for a catalog bug, not for forms events only)

## Deviations
none in scope. Table rows and one `PARENTS` entry were added to `tests/webhooks/scenario.py`, as the ticket asks.

## Changed files
- `tests/webhooks/scenario.py` — 8 new rows in `MODULE_STREAMS` (qr, quality, permits); `permits.GasTest` added to `PARENTS`
- `docs/reports/P2-IP/IPF4.md` — this report

## Event types added
- `qr.ScanCode`: ScanCode.Issued, ScanCode.Revoked
- `quality.Checklist`: Checklist.Created, Edited, Published, Retired
- `quality.Inspection` (row 1): Inspection.Planned, Scheduled, ResultRecorded, Verified
- `quality.Inspection` (row 2): Inspection.Planned, Cancelled
- `permits.Permit` (row 1): Permit.Requested, Approved, Issued, Suspended, Resumed, Revalidated, Lapsed, IsolationLinked, IsolationUnlinked, HandedBack, Closed
- `permits.Permit` (row 2): Permit.Requested, Rejected
- `permits.Permit` (row 3): Permit.Requested, Cancelled
- `permits.Isolation`: Isolation.Applied, Verified, Removed
- `permits.GasTest`: GasTest.Recorded (names its permit via `PARENTS`)

## Commands and output
```
$ uv run ruff format --check tests/webhooks/scenario.py
1 file already formatted
$ uv run ruff check tests/webhooks/scenario.py
All checks passed!
$ uv run pyright tests/webhooks/scenario.py
0 errors, 0 warnings, 0 informations
$ just gate tests/contract/test_webhook_catalog_contract.py
part 1: exit 1, 2 failed, 5 passed in 722.67s (0:12:02)
FAILED tests/contract/test_webhook_catalog_contract.py::test_the_scenario_delivers_every_event_type_of_the_catalog
FAILED tests/contract/test_webhook_catalog_contract.py::test_every_delivered_body_validates_against_the_catalog_schema_of_its_type
gate: FAIL
$ uv run pytest tests/contract/test_webhook_catalog_contract.py -k "scenario_delivers_every or validates_against" -q
E  AssertionError: ('delta', 'Inspection.Verified', "'2026-12-07' is not a 'date-time'", ['data', 'detail', 'verified_on'])
2 failed, 5 deselected in 226.87s
```

Test 1 (`scenario_delivers_every_event_type`): the missing set starts with `Submission.*`, `Template.*`, `IntakeItem.*` (forms, out of scope). The printed diff is truncated, so I did not list every missing type; the forms types are the only ones I saw.

## Blocked — catalog bug (escalation trigger: "a body fails its catalog schema")
- Type: `Inspection.Verified` (v1). Field: `verified_on`.
- The sample `packages/tl-schema/src/tl_schema/generated/catalog/samples/Inspection.Verified.v1.json` has `"verified_on": "2026-12-07"`.
- The generated schema (`.../catalog/schemas/Inspection.Verified.v1.json`) requires `date-time` for that field.
- The source `schema/modules/quality/events.yaml` (around line 428-431) declares `verified_on` as `range: datetime` with description "YYYY-MM-DD". The record field in `schema/modules/quality/inspection.yaml` is a `YYYY-MM-DD` pattern, so the event range is the likely error.
- Fixing it needs a schema change (`schema/**`), which is not in this ticket's scope. I did not edit it.
- Question for the supervisor: should `Inspection.Verified.verified_on` be `date` (or a pattern) in `events.yaml`, followed by `just gen`? The same question applies to any other event that uses `range: datetime` for a date-only value.

## Learnings (proposed)
- `dev/gate.sh` writes only the summary to the task output file. Use `uv run pytest <file> -k ... -q` to see the assertion text.
- `PARENTS` and `streams` in `append_module_events` key by record type. Repeated record types (three `permits.Permit` rows) mean the last row wins, so `permits.GasTest` points at the cancelled permit's stream. It is valid, but the choice is implicit.
- One contract test run takes about 4 minutes; the full `just gate` on this file takes about 12.

## Open questions / Blocked
1. Catalog schema: `Inspection.Verified.verified_on` is `date-time` in the generated schema but a date in its sample and its description (see Blocked above). Needs a schema decision.
2. Forms event types (`Submission.*`, `Template.*`, `IntakeItem.*`) are not in this tree; the ticket says they follow after the integration merge.
