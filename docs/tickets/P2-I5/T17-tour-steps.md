# P2-I5-T17 — Highlights tour: Activity, Insights, intent, and the weekly loop

Status: ready (all dependencies merged into `p2/i5`; T12 via T12b)
Tier: haiku
Kind: ticket
Review: full
Labels: tour, docs
Depends on: T12, T06c2, T06b, T07a, T09
Branch: `p2/i5-t17-tour`
Worktree: harness-created under `/home/user/wt/i5/t17` (from `p2/i5` head)

## Goal
Owner, 2026-11-09: after weekly plans, a highlights screenshot tour. `just tour highlights` (`dev/tour/highlights.py`, output `docs/reports/tour/highlights/`) gains screens for what P2-INT and I5 added, after the eight existing ones (those stay byte-identical: the clock is frozen and their world is unchanged). The tour is also where the leak check runs on every plain screenshot (`tourkit.py`), so this is the one pass that visits the new screens (rule 12).

## Brief references (pasted)
New shots, numbered on from 09, each `tk.shot_tui(ws, app, name, title, *needles)` with the needles that must be on screen (screen text, not ids):
- 09 `09-record-activity`: an RFI's Activity tab (key `4` in the record screen, as `record_shots` does) with its events by person and day.
- 10 `10-record-insights`: the same record's Insights tab (key `9`): the checks that apply, each with its result and what to do.
- 11 `11-intent-panel`: the Activity tab with the cursor on an event that carries an intent (`widgets/activity_tab.py`, `tl_tui/intent_text.py` `intent_lines`): the stated reason, expected effect and references as the panel shows them. Make the event in the tour world by running a command with an intent (read `dev/accept/P2-INT/S2.py` for the way a command takes one).
- 12 `12-iwp-landing`: a foreman signs in and the app opens on the IWP log with mine on (T06c2), the Ready and Blocking counts and Since columns (T06c1).
- 13 `13-week-look-ahead`, 14 `14-week-constraints` (a check-raised constraint shown waived, with who and why), 15 `15-week-commitments` (committed IWPs with hours and foreman, then an outcome recorded), 16 `16-week-progress` (earned % per IWP, the KPI line with PPC and constraint-free, T09), 17 `17-week-closed` (the closed week with its PPC): the weekly cycle screens of T06a and T06b opened from the palette entry "Weekly cycle", keys `1` to `5` as the steps line shows.
- The pack: not a terminal screen. `tl awp iwp pack NUMBER --out <out dir>/pack-<NUMBER>.html` through a CLI shot (`ws.shot_cli`, name `18-iwp-pack`, the command and its two lines) and the HTML file itself is kept beside the SVGs (self-contained, T07b).
- World: the weekly loop needs the awp project P200 of the generator: build it as `dev/tour/wave1.py` does (`seed_demo_project(ws)`; read how it shares a ledger) in the same `Workspace` after the RFI world, then add what the loop needs by CLI (a published schedule snapshot, Issued IWPs with a foreman, one constraint waived, the week opened, committed, outcomes, closed). Frozen clock, fixed archive key, no wall-clock text on screen.
- Docs: `docs/reports/HIGHLIGHTS-TOUR.md`: update the intro sentence (the count and what is shown), add one `## NN title` section per new screenshot with the image link and two or three sentences in the style of the existing sections (what the screen is for, what to read first); headings match file names. `docs/reports/tour/highlights/` holds the new SVGs and the pack HTML (committed).
- Method: skill `tui-layout` for wording; no new key. A screen that cannot be reached with the merged keys is a finding (Blocked), not a new key.

## Context (read these, nothing else)
- `dev/tour/{highlights.py (whole), tourkit.py (216-330), wave1.py (40-110, 165-185)}`, `docs/reports/HIGHLIGHTS-TOUR.md`, `dev/accept/P2-INT/S2.py` (the intent), the reports `docs/reports/P2-I5/{T06a,T06b,T06c1,T06c2,T07a,T12}.md`, `packages/tl-tui/src/tl_tui/widgets/{activity_tab.py, insights_tab.py, record_view.py (85-105)}`

## Allowed paths
- `dev/tour/highlights.py`, `docs/reports/HIGHLIGHTS-TOUR.md`, `docs/reports/tour/highlights/*` (generated)
- `docs/reports/P2-I5/T17.md`; no source change

## Acceptance
```
just check
just tour highlights
just tour highlights
git status --short docs/reports/tour/highlights
```
Expected: the first run writes 18 SVGs and the pack, the leak check reports none and exit 0; the second run changes no file (the `git status` after the second run equals the one after the first, `cmp` of the two listings); the first eight SVGs are unchanged against `HEAD`.

## Tests to add
None (the tour is the check). Each new shot lists its needles in the call.

## Escalation triggers
- A new screen shows an id, a key of a hidden record or a wall-clock time (the leak check names it): stop, it is a finding.
- A screen needs a key or an action the merged code does not have.

## Report requirements
Standard report (`docs/templates/haiku-report.md`), <= 60 lines, deviations first; pins updated outside Allowed paths listed. Commit subjects `P2-I5-T17: ...`; trailer is the attribution lines your harness requires then `Claude-Session: https://claude.ai/code/session_01MSkuXpRjf5XzVwbAVQNqK4`. No model names in committed files.

## Blocked
(implementer writes here)

## Decision
(supervisor or orchestrator writes here)
