# P2-X1-T06 — `docs/reference/api-compat.md`

Status: ready (dispatch r3)
Tier: haiku
Kind: ticket
Review: lite
Labels: docs
Depends on: T04 (merged)
Branch: `p2/x1-t06-api-compat-doc`
Worktree: `/home/user/wt/x1/t06`

## Goal
One page that tells an API consumer and a contributor what may change in the HTTP API, what never changes without notice, and how.

## Brief references (pasted)
- Additive only: new routes, new optional request fields, new optional header or query parameters, new response fields, new error codes.
- Breaking, refused by `just check` (`tl_schema.compat.diff_openapi` and the error-code check of T05): a removed route or method, a removed
  or renamed response field, a changed field type, a new required request field or parameter, an optional parameter that became required,
  a removed or re-statused error code.
- Owner rule (Q1, 2026-11-13): the baseline file `docs/reference/openapi.baseline.json` is refreshed only as a release step with
  `just openapi-baseline`. A breaking change between releases needs an `APPROVALS.md` line naming what breaks and a note on this page.
  Removals are deprecated for at least one release first (the field stays, the page lists it under Deprecated with the release it goes).
- Events are separate: event payloads are additive over `packages/tl-schema/compat/event-schemas.json` (`just compat-update`).
- Idempotency (this increment): `Idempotency-Key` header on `POST /commands/{Name}` (body field `idempotency_key` also accepted; both given
  and different: 422 `invalid_idempotency_key`); key is per actor, printable ASCII without space, 1..128 characters; same key and same body
  replays the first answer; same key, other body: 409 `idempotency_mismatch`; first send still running: 409 `idempotency_in_progress`.
  MCP proposing tools take optional `idempotency_key`.

## Context
- `docs/reference/punch.md` (style: short page, tables) — first 40 lines only
- `docs/reference/access-words.md` (first 20 lines, style only)

## Allowed paths
- `docs/reference/api-compat.md` (new)

## Steps
Sections: What may change; What never changes unannounced; The baseline and how it is refreshed; Deprecated (empty table with columns
Item, Deprecated in, Removed in); Retries and `Idempotency-Key`. At most 70 lines. Plain, technical wording; no model names.

## Acceptance
```
just check
```
Expected: pass. No test file (docs only). State in the report that the page names no command that does not exist
(`just openapi-baseline` is created by T05 in this batch; say so).

## Report requirements
Standard report.

## Escalation triggers
- Stop if a pasted fact contradicts a file you read.

## Blocked
(implementer writes here)

## Decision
(supervisor or orchestrator writes here)
