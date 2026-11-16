# P2-IP-F5 - Tour shots: the inspection and permit log and record screens

Status: staged (r6; dispatch after INSP-T10 and PTW-T11 merge; base `p2/ip-r3` head at dispatch)
Tier: haiku
Kind: ticket
Review: lite
Labels: tui, docs
Depends on: P2-INSP-T10, P2-PTW-T11, P2-INSP-T03, P2-PTW-T03 (the demo project holds inspections and permits)
Branch: `p2/ip-f5-tour`
Worktree: `/home/user/wt/ip/f5` (from `p2/ip-r3`)

## Goal
`dev/tour/phase2.py` writes four more SVGs of the full demo project P200, with the leak check on each: `13-inspections` (the log), `14-inspection` (one record: a Done inspection with failed questions), `15-permits` (the register), `16-permit` (one Active permit with its gas tests). Method exactly as the `10-punch` scenario (the `scenario(...)` helper and the actors block of the docstring; update the docstring list and the "twelve SVGs" count). Actors: the quality and permit roles of the demo roster (`user:hsato` for quality as in 10-punch; `user:ipetrov` for permits, D29). The record screens are pushed with the key read from the log shot, not hard-coded, unless the generator's keys are fixed (then pin them as 10-punch does). The QR scan page is a web page and `tourkit` drives the terminal only: no QR shot (decided r6, D36); the scan page text is in the P2-QR demo.

## Context (read these, nothing else)
- `dev/tour/phase2.py` (whole), `dev/tour/tourkit.py` (the `scenario`-related helpers: signatures only)
- `packages/tl-tui/src/tl_tui/widgets/inspection_log.py`, `permit_log.py` (constructor signatures), `docs/reports/P2-IP/{INSPT10,PTWT11}.md`

## Allowed paths
- `dev/tour/phase2.py` (edit)
- `docs/reports/tour/phase-2/` (the four new SVGs and the regenerated index if the tour writes one: the tour command writes them; commit what it writes)
- `docs/reports/P2-IP/F5.md` (create)

## Acceptance
```
uv run ruff format --check dev/tour/phase2.py
uv run ruff check dev/tour/phase2.py
uv run pyright dev/tour/phase2.py
just tour phase2 /tmp/phase2-tour
```
Expected: sixteen SVGs, the leak check prints no leak, exit 0. Copy the four new SVGs (and only those, unless the tour rewrites the others identically) to `docs/reports/tour/phase-2/`. Run the tour once. No pytest, no `just gate`.

## Escalation triggers
The demo project has no inspections or permits (the generator sections are off in `seed_demo_project`: name the section list); a record screen needs a key the log does not show; the leak check fails (a 32-hex id on a screen: report the screen, do not edit the widget).

## Report requirements
Standard report (`docs/templates/haiku-report.md`), <= 60 lines, deviations first; the `tui-layout` checks as one line per shot. Commit subjects `P2-IP-F5: ...` with the trailers the dispatch message names; no model names.

## Blocked
(implementer writes here)

## Decision
(supervisor or orchestrator writes here)
