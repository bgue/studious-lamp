# P2-I5-T03 — `look_ahead_view`: activities, linked IWPs, readiness counts

Status: ready (S2 merged; the stub is in the tree; no dependency on S4a, plan check F5)
Tier: haiku
Kind: ticket
Review: full
Labels: read, confidentiality
Depends on: P1-I4 look-ahead (trunk), I2 readiness (merged)
Branch: `p2/i5-t03-look-ahead-view`
Worktree: harness-created under `/home/user/wt/i5/t03` (from `p2/i5` head)

## Goal
One read for the planner's look-ahead: the rows of `tl_mod_schedule.lookahead.look_ahead` for a snapshot, each with the IWPs linked to the activity, their need-by date, their readiness as counts and their open blocking constraints, all through the viewer. No text of a hidden record, no new table.

## Brief references (pasted)
- Interface fixed in the stub `packages/tl-modules/awp/src/tl_mod_awp/look_ahead_view.py` (dataclasses `LookAheadIwp`, `LookAheadItem`, `LookAheadView`; function `look_ahead_view(conn, scope, snapshot, viewer=None, *, weeks=4)`). Replace the body; keep every name and field.
- Steps of the read, each one statement for all rows (never one per activity or IWP; T06a3 rule):
  1. `look_ahead(conn, snapshot, weeks, scope=scope)` (a bad `weeks` raises its `ValueError`; a snapshot of another scope its error). `counts` and the window come from it; `items` keep its row order.
  2. IWPs: `iwp_views.iwp_list(conn, scope, limit=500)` (void and hidden left out; it reads the current viewer). Drop state `Cancelled` and `Split`. When `viewer` is given wrap steps 2 to 5 in `tl_core.confidentiality.use_viewer(viewer)`.
  3. Links, one statement: `SELECT l.from_id, a.activity_id FROM cur_links l JOIN cur_schedule_activity_ref a ON a.id = l.to_id WHERE a.schedule_id = :schedule AND a.scope = :scope AND l.scope = :scope AND l.status = 'active' AND a.activity_id IN :ids` with `bindparam("ids", expanding=True)` (chunks of 500 ids); `:schedule` is `snapshot.schedule_id`, `:ids` the listed activity ids. A link whose `from_id` is not in step 2's rows is dropped. An IWP lists under every activity it links. IWPs sort by number inside an item.
  4. Readiness, two statements over `cur_awp_readiness` and `cur_awp_readiness_check` (`names.READINESS_TABLE`, `READINESS_CHECK_TABLE`) for the IWP ids: `evaluated` is a head row exists, `ready` its `ready` flag, `checks_ok` the checks in state `ok` or `n_a` (`readiness.engine.PASSING`), `checks_total` all checks. No `resolve_via`, no detail text: counts only. Never evaluated: `evaluated False, ready False, 0/0`.
  5. `open_blocking`: one `tl_core.constraints.list_constraints(conn, scope, state=..., blocking=True, viewer=viewer, limit=500)` per state in `iwp_views.OPEN_STATES`, counted by `subject_id`.
  6. `lead_weeks = int(common.setting_value(conn, scope, "awp.iwp.ready_lead_weeks") or 0)`; `need_by = (date.fromisoformat(planned_start) - timedelta(weeks=lead_weeks)).isoformat()`, `None` without a start.
- The result is a plain function of the rows read: the same call twice is equal. Hidden looks like missing (a hidden IWP is absent, nothing says one was dropped).

## Context (read these, nothing else)
- `packages/tl-modules/awp/src/tl_mod_awp/look_ahead_view.py` (the stub), `iwp_views.py` (`iwp_list`, `OPEN_STATES`), `readiness/views.py` (lines 1-40, table names and SQL style), `common.py` (`setting_value`)
- `packages/tl-modules/schedule/src/tl_mod_schedule/lookahead.py` (lines 1-60: `LookAheadRow`, `look_ahead`), `packages/tl-core/src/tl_core/constraints/queries.py` (`list_constraints` signature, `ConstraintView.subject_id`)
- the provided test `docs/tickets/P2-I5/provided/T03_test_look_ahead_view.py`
may explore: (none)

## Allowed paths
- `packages/tl-modules/awp/src/tl_mod_awp/look_ahead_view.py` (the stub, body only)
- `packages/tl-modules/awp/tests/test_look_ahead_view.py` (create: byte-identical copy of the provided test)
- `docs/reports/P2-I5/T03.md` (create)
Not allowed: schema, `tl_core`, `tl_mod_schedule`, the readiness module, any CLI, API or TUI file.

## Acceptance
```
just check
just gate packages/tl-modules/awp/tests/test_look_ahead_view.py
```
Expected: 7 passed; `just check` clean. `cmp` of the test and the provided copy identical.

## Tests to add
The provided test (copied). Add nothing else.

## Report requirements
Standard report (`docs/templates/haiku-report.md`), <= 60 lines, deviations first; the number of statements the read runs for the demo snapshot (a `before_cursor_execute` count is not required; state the count from the code). Commit subjects `P2-I5-T03: ...`; trailer is the attribution lines your harness requires then `Claude-Session: https://claude.ai/code/session_01MSkuXpRjf5XzVwbAVQNqK4`. No model names in committed files.

## Escalation triggers
- An IWP cannot be linked to an activity in the provided test (`LinkActivity` refuses the IWP): write the refusal under Blocked and stop.
- `iwp_list` cannot be made to follow the passed viewer.
- The provided test fails on a line the ticket does not explain.

## Blocked
(implementer writes here)

## Decision
(supervisor or orchestrator writes here)
