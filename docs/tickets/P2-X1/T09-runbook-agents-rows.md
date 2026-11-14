# P2-X1-T09 — Runbook `api-retries.md` and AGENTS.md rows

Status: staged (dispatch after T08 merges)
Tier: haiku   kind: ticket   review: lite
Labels: docs
Depends on: T08, T02 (merged)
Branch: `p2/x1-t09-runbook`   Worktree: `/home/user/wt/x1/t09`

## Goal
`docs/runbooks/api-retries.md` tells an operator and an integrator how retries are made safe (header, body field, replay, mismatch, in-progress, retention, what a replay shows after a clearance drop) and how the OpenAPI compatibility gate is used; `AGENTS.md` gets rows in "Where things go" for the two features.

## Brief references (pasted)
Fill from the reports (do not paste them): `docs/reports/P2-X1/{S1,S2,T01,T03,T05,T07,T08}.md`, `docs/reference/api-compat.md`, and the decisions D1, D4, D5, D6 in `STATE.md`. Load the `throughline-docs` skill's runbook rules.

## Context (≤ 6)
- `docs/runbooks/web-client.md` (shape of a runbook)
- `docs/reference/api-compat.md`
- `docs/reports/P2-X1/S1.md`, `T05.md`, `T08.md`
- `AGENTS.md`

## Allowed paths
- `docs/runbooks/api-retries.md` (create)
- `AGENTS.md` (two rows added to the table; nothing else)
- `docs/reports/P2-X1/T09.md`

## Acceptance
```
just check
grep -c "api-retries" AGENTS.md
```
Expected: check exit 0; grep prints 2 or more. Every command and path named in the runbook exists.

## Report requirements
Standard report; list any claim in the runbook not backed by a report line.

## Escalation triggers
- A report contradicts the code on a rule (key format, status codes): stop, name both.
