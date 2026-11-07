# P2-I1-T14 — `sim_assert` excuses the awp setup of an operator

Status: staged (r13; dispatch only after P2-I3 T12 `p2/i3-t12-sim-desk` has merged into trunk and trunk into p2/i1)
Tier: haiku
Review: lite
Labels: tests, sim
Depends on: T07 (merged), P2-I3 T12 (merged; same package `tl-sim`)
Branch: `p2/i1-t14-sim-awp-excuse`
Worktree: `/home/user/wt/i1/t14` (from `p2/i1` head after both merges)

## Goal
T08 clause 10: an operator who defines awp data by hand on the sim project (`tl awp cwa define`, `path define`, as D43) no longer fails `tl sim assert`. Today `CWA.Defined`, `PathOfConstruction.Defined` and `Record.Created` of those records are judged like a simulated actor's. They are excused the way schedule and correspondence setup is, and counted in `report.excused`.

## Brief references (pasted, abridged)
`packages/tl-sim/src/tl_sim/assertions.py`: `OPERATOR_EVENTS` (frozenset of schedule event names, ~line 73); `OPERATOR_STREAM_EVENTS` (`Record.Created`, `Workflow.Transitioned`, file events, excused only when the stream type starts with `SCHEDULE_TYPES`); `CORRESPONDENCE_TYPES = "correspondence."`; inner `operator_event(event)` (~line 233) returns True for `OPERATOR_EVENTS`, any event on a correspondence stream, and stream events on a schedule stream; the `unexpected_record` loop (~line 262) excuses a record whose creator is an operator and whose type starts with `(SCHEDULE_TYPES, CORRESPONDENCE_TYPES)`.

## Steps
1. Add `AWP_TYPES = "awp."` and `AWP_OPERATOR_EVENTS = frozenset({"CWA.Defined", "PathOfConstruction.Defined"})` next to the other constants.
2. In `operator_event`: return True for `kind in AWP_OPERATOR_EVENTS`; and for `Record.Created` on a stream whose type starts with `AWP_TYPES` (only that event; no other event on an awp record).
3. In the `unexpected_record` loop add `AWP_TYPES` to the prefix tuple.
4. Extend the module docstring "Operators" paragraph by one sentence naming the awp setup. No model names anywhere.
Nothing else is excused: other events of an operator, and every event of a simulated actor, are judged as before.

## Context (read these, nothing else)
- `packages/tl-sim/src/tl_sim/assertions.py`
- `docs/tickets/P2-I1/provided/test_assertions_awp.py` (copy byte for byte)
may explore: `packages/tl-sim/tests/test_assertions.py` (existing operator tests must still pass)

## Allowed paths
- `packages/tl-sim/src/tl_sim/assertions.py`
- `packages/tl-sim/tests/test_assertions_awp.py` (create: the provided test, unchanged)
- `docs/reports/P2-I1/T14.md`

## Acceptance
```
NODE_OPTIONS=--max-old-space-size=6144 just check
uv run pytest packages/tl-sim/tests/test_assertions_awp.py packages/tl-sim/tests/test_assertions.py -q
```
Expected: all pass (the 4 provided tests are red before the change); report says `101`.

## Report requirements
`docs/templates/haiku-report.md`, <= 60 lines, <= 5 output lines per command.

## Escalation triggers
- Stop and report *Blocked* if a provided test cannot pass without editing `testing.py` or `Expected`.

## Blocked
(implementer writes here)

## Decision
(supervisor or orchestrator writes here)
