# P2-TOUR2-T01 — The Phase 2 tour: the wave 2-4 terminal screens on P200

Status: ready
Tier: haiku
Kind: ticket
Review: lite
Labels: tests, docs
Depends on: P2-SEED (merged; P200 seeds schedule, requisitions, release, weekly, progress, punch)
Branch: `p2/tour2-t01`   (from the trunk)

## Goal
A new tour, `dev/tour/phase2.py` (`just tour phase2`), copies the method of `dev/tour/wave1.py` exactly
(`seed_demo_project(ws)` imported from `wave1`, `scenario(...)`, frozen clock, `tk.shot_tui`, leak check on plain
shots) and writes one SVG per screen below to `docs/reports/tour/phase-2/` (default `--out`). Then run it and commit
the SVGs and transcripts it writes.

## Screens (open as wave1 does: `app.push_screen(make(app.client))`, wait for rows)
| shot | screen (tl_tui.widgets...) | constructor | actor |
|---|---|---|---|
| 01-iwps | iwp_register.IwpRegisterScreen | (c, PROJECT) | lhartmann |
| 02-constraints | constraint_screen.ConstraintScreen | read its `__init__` | lhartmann |
| 03-readiness | readiness_screen.ReadinessScreen | (c, PROJECT, <an IWP number from 01>) | lhartmann |
| 04-lookahead | weekly_screen.LookAheadScreen | (c, PROJECT) | lhartmann |
| 05-release | weekly_screen.ReleaseScreen | (c, PROJECT) | lhartmann |
| 06-commitments | weekly_screen.CommitmentsScreen | (c, PROJECT) | lhartmann |
| 07-progress | weekly_screen.ProgressScreen | (c, PROJECT) | lhartmann |
| 08-requisitions | requisition_register.RequisitionLogScreen | (c, PROJECT) | lhartmann |
| 09-work-orders | work_order_backlog.WorkOrderBacklogScreen | (c, PROJECT) | lhartmann |
| 10-punch | punch_log.PunchLogScreen | (c, PROJECT) | lhartmann |
| 11-schedule | schedule_screen.ScheduleScreen | (c, PROJECT, "user:lhartmann") | lhartmann |
| 12-packages | package_log.PackageLogScreen | (c, PROJECT) | lhartmann |

Needles: pick one or two strings each screen really shows on P200 (run the tour once, read the transcript). If a
screen shows no rows on P200 or the actor lacks access, try `treyes` or `mokafor` (same password); if it still
shows none, leave that shot out and list it in the report with the reason (do not change the seed or the screens).
Use `technical=True` only where wave1 does for the same reason (@N keys), and say which in the report.

## Allowed paths
- `dev/tour/phase2.py` (create)
- `justfile` (the `tour` recipe: add `phase2` beside `wave1`, nothing else)
- `docs/reports/tour/phase-2/**` (generated)
- `docs/reports/tour/index.html` (one link to phase-2, if the file lists the others)
- `docs/reports/P2-TOUR2/T01.md` (create)

## Context (read these, nothing else)
`dev/tour/wave1.py` (the template), `dev/tour/tourkit.py` (abridged: `Workspace`, `shot_tui`, `until`), the twelve
screen modules above (their `__init__` and the first lines of the class only), `justfile` lines 140-145.

## Gate
`NODE_OPTIONS=--max-old-space-size=6144 just check`; then `just tour phase2` must exit 0 and print
`wrote N screenshots`. No pytest gate beyond `just check` (the tour is its own check). Report the N and each shot's needle.

## Report
≤ 60 lines; commit `P2-TOUR2-T01: ...` with the session trailers; no model names in committed text.
