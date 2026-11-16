# P2-IP-F4 - The webhook scenario delivers the QR, inspection and permit events

Status: ready (written r6; base `p2/ip-r3`; row in `docs/build-spec/DEFERRED.md`, "must pass before p2/ip merges to trunk")
Tier: haiku
Kind: ticket
Review: full
Labels: tests, webhooks
Depends on: P2-QR-S1, P2-INSP-S1, P2-PTW-S1 (event schemas; merged)
Branch: `p2/ip-f4-webhook-scenario`
Worktree: `/home/user/wt/ip/f4` (from `p2/ip-r3`)

## Goal
`tests/contract/test_webhook_catalog_contract.py::test_the_scenario_delivers_every_event_type_of_the_catalog` passes on `p2/ip-r3`: the scenario (`tests/webhooks/scenario.py`) appends and delivers every event type the three increments added. The table of module events there is `(record type, first event, follow-on events)` rows (the punch row near line 285 is the model); the sample payloads come from the generated catalog samples (`payload_of`). Events to add, by the samples in `packages/tl-schema/src/tl_schema/generated/catalog/samples/`:
- `qr.ScanCode`: `ScanCode.Issued`, then `ScanCode.Revoked` (a rotate writes Revoked plus Issued).
- `quality.Checklist`: `Checklist.Created`, then `Edited`, `Published`, `Retired`; `quality.Inspection`: `Inspection.Planned`, then `Scheduled`, `ResultRecorded`, `Verified`, and a second inspection or a second row for `Cancelled`.
- `permits.Permit`: `Permit.Requested`, then `Approved`, `Issued`, `Suspended`, `Resumed`, `Revalidated`, `Lapsed`, `IsolationLinked`, `IsolationUnlinked`, `HandedBack`, `Closed`; a second permit for `Rejected` and a third for `Cancelled`, each in a valid order for the projector; `permits.Isolation`: `Isolation.Applied`, `Verified`, `Removed`; `permits.GasTest`: `GasTest.Recorded` (first event names its permit: see the "child record names its parent" comment below the table).
The forms events are out of scope here (the forms branch is not in this tree; they follow after the integration merge). If the test still fails only for forms event types, say which and stop: that is the finished state of this ticket.

## Context (read these, nothing else)
- `tests/webhooks/scenario.py` (lines 1-60, the table at 250-340, the comment after it, `append_module_events`), `tests/contract/test_webhook_catalog_contract.py` (lines 1-60), `tests/webhooks/world.py` (names only)
- the sample files named above (open one of each; do not read the whole directory), `packages/tl-modules/permits/src/tl_mod_permits/projectors/` (file names, to see which first events a child needs)

## Allowed paths
- `tests/webhooks/scenario.py` (edit: table rows and the parent-naming map only)
- `docs/reports/P2-IP/IPF4.md` (create)
- if a pinned count in `tests/webhooks/` or `tests/contract/` fails only by the number of event types: update it in union form and list it (rule 12)

## Tests to add
None new: the existing contract tests are the acceptance (every delivered body validates against its catalog schema; the three modes carry the same events; delivered facts match the ledger).

## Acceptance
```
uv run ruff format --check tests/webhooks/scenario.py
uv run ruff check tests/webhooks/scenario.py
uv run pyright tests/webhooks/scenario.py
just gate tests/contract/test_webhook_catalog_contract.py
```
Expected: clean; `gate: PASS`, or red only on forms event types (reported). No `just check`, no whole-repo pyright.

## Escalation triggers
An event cannot be appended in a valid order without a projector or schema change; a body fails its catalog schema (a catalog or handler bug: write which type and field and stop); the table needs more than 120 lines.

## Report requirements
Standard report (`docs/templates/haiku-report.md`), <= 60 lines, deviations first; list the event types added. Commit subjects `P2-IP-F4: ...` with the trailers the dispatch message names; no model names.

## Blocked
(implementer writes here)

## Decision
(supervisor or orchestrator writes here)
