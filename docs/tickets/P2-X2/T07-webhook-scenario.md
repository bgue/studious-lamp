# P2-X2-T07 — Webhook contract scenario delivers Agent.Stopped and Agent.Resumed

Status: in-progress. Branch `p2/x2-t07-webhook-scenario`, base `p2/x2`. Tier: ticket, lite. Tests only.

## Problem
`tests/contract/test_webhook_catalog_contract.py::test_the_scenario_delivers_every_event_type_of_the_catalog`
fails: `run_scenario` (`tests/webhooks/scenario.py`) never produces `Agent.Stopped` / `Agent.Resumed`
(added by S3), which are in the deliverable set (not in `ACCOUNT_EVENT_TYPES`).

## Change
In `run_scenario`, before delivery: create an admin person account and an agent account, grant the
agent the module `user` word on `project:P1`, let the agent file once (`submit`), then run
`StopAgent` and `ResumeAgent` as the admin through the real handlers.

## Allowed paths
`tests/webhooks/scenario.py`, this ticket, `docs/reports/P2-X2/T07.md`.

## Acceptance
- Both tests in `tests/contract/test_webhook_catalog_contract.py` named above and
  `..._validates_against_the_catalog_schema_of_its_type` pass; the parity tests using the scenario still pass.
- If the subscriber cannot receive Agent.* by design: stop, report, propose the test change.

## Gate
`NODE_OPTIONS=--max-old-space-size=6144 just check`; `just gate tests/contract`.
