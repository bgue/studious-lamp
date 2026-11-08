# P2-INS-T04 — Twin tests of Activity and Checks (INS-A4 + INS-B5, reduced by plan check F8)

Status: draft (written round 1; the next round pastes the fixture helpers after S1 and S2 merge)
Tier: haiku
review: full
Labels: tests
Depends on: S1, S2 merged. The walking tests (five readers, route level) are already inside S1 and S2; this ticket adds the twin tests
Branch: `p2/ins-t04-twin-tests`
Worktree: `/home/user/wt/ins-t04`

## Goal
Twin tests prove that a hidden record leaves no trace in what a viewer reads: the Activity read and the Checks read give the same rows, order and counts for a record linked to a hidden record as for its twin without that link. Tests only; no source change. A failing twin is reported as a finding (`F<n> HI file:line`), never fixed here.

## Brief references (pasted; spec C3)
- Twin, Activity: record X linked to hidden H versus X without the link: identical rows, order, `next_before_seq` and row count, for a viewer who cannot read H. The same for a constraint whose target is hidden (the row stays, the target is absent) against a no-target twin, and for a proposal that names H in its stored command.
- Twin, related: a linked record's causal events (a workflow move, an RFI answered, a constraint cleared) vanish for a viewer who cannot read it, at the link (either end hidden) and at the events; a reader who can read it sees them, marked related with `from_key`.
- Twin, Checks: a hidden RFI that a constraint targets, versus no target: equal findings and equal text; a readiness result with a hidden `resolve_via` record carries the fixed line and no key, in any finding `text`.
- Intent: nothing to test until the ADR-0025 slice lands (no `why` on the base). Write no skipped test (AGENTS.md); list it under "not covered" in the report.
- Read-only: both routes and both `ClientInterface` methods issue no INSERT, UPDATE or DELETE and leave `telemetry_need` unchanged, on SQLite and Postgres (`just gate-pg`).
- Page cap: seed fewer than 1000 candidate events so the scan cap of S1 is not reached (the one case where a page may differ from its twin).
- Readers: the five the existing walks use (anonymous or lowest clearance, a user, a controller, an admin, an agent token); the agent gets the route's normal refusal, which is the same for visible, hidden and missing ids.

## Interfaces (open these)
Route and client signatures of S1 and S2; the fixture builders of `packages/tl-api/tests/test_confidentiality_walk.py` and `packages/tl-core/tests/` (confidential records, links, constraints with a hidden target, proposals).

## Context (<= 6 files)
`packages/tl-api/tests/test_confidentiality_walk.py`; `packages/tl-api/tests/test_activity_walk.py` and `test_checks_walk.py` (S1, S2); `docs/tickets/P2-INS/S1-activity-read.md`, `S2-checks-telemetry.md` (Guards sections); `packages/tl-core/src/tl_core/insights/activity.py` (read only).

## Allowed paths
- `packages/tl-core/tests/insights/test_activity_twin.py`, `test_checks_twin.py` (create)
- `packages/tl-api/tests/test_insights_twin_routes.py` (create)
- `docs/reports/P2-INS/T04.md` (create)
Not allowed: any `src/` file, `confidentiality.py`, existing tests.

## Acceptance
```
just check
just gate packages/tl-core/tests/insights packages/tl-api/tests/test_insights_twin_routes.py
just gate-pg packages/tl-core/tests/insights packages/tl-api/tests/test_insights_twin_routes.py
```

## Tests to add
The ones in the list above, one function per twin pair, each asserting equality of the full result (not a count only), and one deliberate break per pair run once by the author by hand (reported in one line, not committed).

## Report requirements
`docs/templates/haiku-report.md`, <= 60 lines; deviations first; the "not covered" line (intent); output of the three commands (<= 5 lines each).

## Commit
`P2-INS-T04: <imperative summary>`; trailer lines as `SUPERVISOR-PROMPT.md`; no model names. Do not merge; do not push.

## Escalation triggers
- Stop and report *Blocked* if a twin differs (that is a finding to escalate, not to fix); a fixture needs a source change; the seed reaches the scan cap.

## Blocked
(implementer writes here)

## Decision
(supervisor or orchestrator writes here)
