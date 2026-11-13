# P2-I5-T11a2 — API read routes: weekly plans, miss reasons, look-ahead

Status: ready (S4a, T03 merged); run after T11a1 has merged (both edit `app.py` and `openapi.json`)
Tier: haiku
Kind: ticket
Review: full
Labels: api, read, confidentiality
Depends on: S4a, T03, T11a1
Branch: `p2/i5-t11a2-weekly-routes`
Worktree: harness-created under `/home/user/wt/i5/t11a2` (from `p2/i5` head)

## Goal
Four GET routes over the merged weekly readers and `look_ahead_view`, same word and viewer rule as T11a1.

## Brief references (pasted)
- `GET /projects/{project}/awp/weeks` (`list_weekly_plans`; query `limit` 1..520, default 60) -> `list[week_views.WeekRow]` from `list_weeks(conn, scope, viewer, limit=limit)`.
- `GET .../awp/weeks/{week}` (`get_weekly_plan`; `week` is `YYYY-Www`, pattern checked, else 422) -> `week_views.WeekDetail`: find the id in `list_weeks(limit=520)` by `.week`, then `week_detail`; a missing, hidden or voided plan is 404 `record_not_found` with one text (`RecordNotFoundError(f"no week {week!r}")`).
- `GET .../awp/miss-reasons` (`list_miss_reasons`) -> `list[str]` (`week_views.miss_reasons(conn, scope)`: keys only, never labels).
- `GET .../awp/look-ahead?schedule=MAIN&snapshot=&weeks=4` (`get_look_ahead`; `schedule` 1..64 chars, `snapshot` int >= 1 or absent, `weeks` 1..26) -> `LookAheadBody` = `LookAheadView` as a pydantic model (`LookAheadBody.model_validate(dataclasses.asdict(view))`; `items[*].row` carries the `LookAheadRow` fields, `items[*].iwps` the `LookAheadIwp` fields). The snapshot is `schedule_views.find_snapshot(conn, schedule_views.find_schedule(conn, scope, code), snapshot, built=True)` (not found maps to the 404 of the schedule routes; see `routes/schedule.py` for the error mapping); the view is `look_ahead_view(conn, scope, row, current_viewer(), weeks=weeks)`.
- Hidden looks like missing: a hidden plan, and a hidden IWP inside the look-ahead, are as the readers give them; the routes add nothing. No id of a hidden record appears.

## Interfaces (verbatim from repo)
```python
# tl_mod_awp/week_views.py
def list_weeks(conn, scope, viewer, *, limit=60) -> list[WeekRow]
def week_detail(conn, plan_id, viewer) -> WeekDetail           # RecordNotFoundError
# tl_mod_awp/look_ahead_view.py
def look_ahead_view(conn, scope, snapshot: SnapshotRow, viewer=None, *, weeks=4) -> LookAheadView
# tl_mod_schedule/views.py
def find_schedule(conn, scope, code) -> ScheduleRow; def find_snapshot(conn, schedule, number, *, built=False) -> SnapshotRow
```

## Context (read these, nothing else)
- `packages/tl-api/src/tl_api/routes/{awp_progress.py (T11a1, the pattern), schedule.py (error mapping)}`, `app.py` (the include)
- `packages/tl-modules/awp/src/tl_mod_awp/{week_views.py, look_ahead_view.py (27-60)}`
- `packages/tl-api/tests/test_api_awp.py` (1-110), `packages/tl-modules/awp/tests/progress_world.py (362-430: WeekWorld)`, `docs/reports/P2-I5/{S4a,T03}.md`

## Allowed paths
- `packages/tl-api/src/tl_api/routes/awp_weeks.py` (create), `packages/tl-api/src/tl_api/app.py` (import and one include line)
- `packages/tl-api/tests/test_api_awp_weeks.py` (create)
- `docs/reference/openapi.json` (generated), `docs/reference/awp.md` (one API row), `docs/reports/P2-I5/T11a2.md`
- consequential pins (union): route-count or auth-table tests the gate names

## Acceptance
```
just gen && just check
just gate packages/tl-api/tests/test_api_awp_weeks.py packages/tl-api/tests/test_confidentiality_walk.py packages/tl-api/tests/test_openapi.py packages/tl-api/tests/test_auth_review.py
```

## Tests to add
`test_api_awp_weeks.py` (`Rig` of `test_api_awp.py`, a week built with `WeekWorld`): list has the plan with `ppc`; detail has one commitment row with the declared keys; unknown week and hidden week answer the same 404 body; `miss-reasons` returns keys; `look-ahead` over a published demo snapshot (`ScheduleWorld`, as `docs/tickets/P2-I5/provided/T03_test_look_ahead_view.py` `Plant`) lists the linked IWP with `evaluated`, and `weeks=0` is 422; no token is 401.

## Escalation triggers
- The schedule 404 mapping needs a new error class; a pin that cannot be updated as a union.

## Report requirements
Standard report (`docs/templates/haiku-report.md`), <= 60 lines, deviations first; pins updated outside Allowed paths listed. Commit subjects `P2-I5-T11a2: ...`; trailer is the attribution lines your harness requires then `Claude-Session: https://claude.ai/code/session_01MSkuXpRjf5XzVwbAVQNqK4`. No model names in committed files.

## Blocked
(implementer writes here)

## Decision
(supervisor or orchestrator writes here)
