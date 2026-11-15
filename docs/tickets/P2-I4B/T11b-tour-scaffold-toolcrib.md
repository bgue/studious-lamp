# P2-I4B-T11b — Tour shots: scaffold register, scaffold record and toolcrib

Status: ready after T11a merges
Tier: haiku
Kind: ticket
Review: lite
Labels: tests
Depends on: T06, T07a, T07b (merged), T11a
Branch: `p2/i4b-t11b-tour`
Worktree: `/home/user/wt/i4b/t11b` (from `p2/i4b` head)

## Goal
Owner rule 2026-11-14: screenshots of new modules go into the tour. `dev/tour/phase2.py` gains three shots after `12-packages`: `13-scaffolds` (the register), `14-scaffold-record` (one scaffold with its inspections) and `15-toolcrib` (the toolcrib screen at crib TC1 after one issue line), all as `user:<name>` actors, with the leak check as for the others. The module docstring list and the "twelve SVGs" sentence become fifteen.

## Brief references (pasted)
> Actor names are written `user:<name>`: a bare name resolves to no account (docstring of `phase2.py`). Screens: `ScaffoldLogScreen(client, project)` and `ScaffoldScreen(client, project, key)` in `tl_tui/widgets/scaffold_register.py`; `ToolcribScreen(client, project, actor, crib)` in `widgets/toolcrib_screen.py` (a modal: it has no `rows`, so `scenario()` does not fit; write the toolcrib shot with `build_app`, `tk.until` and `tk.shot_tui` as `scenario` does, waiting for the screen widget instead of `rows`).

## Interfaces (verbatim from repo at the branch point)
`scenario(ws, name, title, actor, make, what, *needles, technical=False)`; `tk.until(pilot, predicate, what)`, `tk.settle(pilot, n)`, `tk.shot_tui(ws, app, name, title, *needles)`. Needles: one scaffold key from the T11a section (`P200-SCF-0001`) and a state word (`In Use`) for 13; the key and `Inspections` for 14 (open it with the register's Enter or by constructing `ScaffoldScreen`); `TC1` and the status text after an issue line for 15 (the issue line grammar: `dev/accept/P2-I4B/T06.py` `check_issue_and_return`, the typed issue line). Actors: the project engineer `lhartmann` for 13 and 14 (scaffold view word by derivation; if refused, use `mokafor`), a stores person who holds the materials words for 15 (`treyes`, the materials coordinator (`STORES` in `dev/seed/demo_project/materials.py`)).

## Context (read these, nothing else)
- `dev/tour/phase2.py`, `dev/tour/tourkit.py` (`until`, `settle`, `shot_tui` only)
- `dev/accept/P2-I4B/T06.py` (the issue line and the pilot method)
- `docs/reports/P2-I4B/{T11a,T06,T07b}.md`

## Allowed paths
- `dev/tour/phase2.py` (edit)
- `docs/reports/P2-I4B/T11b.md` (create)

## Acceptance
```
just check
just tour phase2 /tmp/phase2-tour
```
Expected: `wrote 15 screenshots`, leak check clean, exit 0. The tour is long: background, once. Look at none of the SVG contents beyond the needles.

## Tests to add
none (the tour fails on a missing needle or a leak).

## Report requirements
Standard report; list the three file names and their needles.

## Escalation triggers
- Stop if a screen shows an id or a leak the check flags: write the text, do not fix the screen.

## Blocked
(implementer writes here)

## Decision
(supervisor or orchestrator writes here)
