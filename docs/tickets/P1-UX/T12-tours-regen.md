# P1-UX-T12 — Tours regenerated in plain language, narratives updated

Status: ready (staged: dispatch after T11, T11b, T11c are merged)
Tier: haiku
Kind: ticket
Review: full
Labels: docs, tui
Depends on: T11, T11b (merged; T11c recommended)
Branch: `p1/ux-t12-tours-regen`

## Goal
`just tour 0` and `just tour 1` run to the end against the plain-language TUI, every SVG is regenerated, the tour scripts' screen needles and the narrative sentences that quote screen text say what the screens now say, and a second run changes no file. No new section here (T12b).

## Brief references (pasted)
> SCOPE 5: the tour scripts regenerate every screenshot; narratives that quote screen text are updated; deterministic (a second run changes no file).
> The scripts check each screenshot with `tk.shot_tui(ws, app, name, title, *needles)`; a needle that is no longer on the screen raises `TourFailed` with the screen text. Needles that were ids, keys or codes become the plain words now shown (labels, type names, `Snapshot N`, `Item`, `Company`...).

## Interfaces (verbatim from repo)
```
just tour phase="1" out=""      # uv run python dev/tour/phase{phase}.py [--out DIR]; just tour-all = tour 0 then tour 1
tourkit: shot_tui(ws, app, name, title, *needles); until(pilot, predicate, what); screen_text(app); expect(cond, msg)
outputs: docs/reports/tour/phase-0/*.svg, docs/reports/tour/phase-1/*.svg; narratives docs/reports/PHASE-0-TOUR.md, PHASE-1-TOUR.md
```

## Context (read these, nothing else)
- `dev/tour/tourkit.py` (lines 437-496), the failing section of `dev/tour/phase0.py` or `phase1.py` that the run names (open only that function)
- `docs/reports/PHASE-1-TOUR.md`, `PHASE-0-TOUR.md` (only the section of a changed screenshot)
may explore: the TUI text module a changed screen reads, to find the new word

## Allowed paths
- `dev/tour/phase0.py`, `dev/tour/phase1.py`, `dev/tour/tourkit.py`
- `docs/reports/tour/phase-0/*.svg`, `docs/reports/tour/phase-1/*.svg`
- `docs/reports/PHASE-0-TOUR.md`, `docs/reports/PHASE-1-TOUR.md` (changed screen text only; the new section is T12b)
- `docs/reports/P1-UX/T12.md` (create)

## Steps
1. `just tour 0`; on `TourFailed` read the screen text it prints, fix the needle in `phase0.py` (new plain word, not a loosened check), rerun. Same for `just tour 1` (it takes long: run it in the background and wait for exit, no polling).
2. `git diff --stat` the SVGs: every change should be explained by plain language (ids, hashes, keys gone). An SVG whose layout changed without a text reason: list it.
3. Search both narratives for quoted screen text of changed screenshots (`grep -n` the old words, for example `Schema #`, `agent:`, `svc:`, `general/`, `required@`, `CODE#`, `valve_data.`) and rewrite those sentences to the new text. Do not touch sentences about CLI output.
4. Run `just tour-all` a second time: `git status --short docs/reports/tour` must not change.

## Acceptance
```
just check
just tour-all
git status --short docs/reports/tour
just tour-all && git status --short docs/reports/tour
```
Expected: the second `git status` equals the first (no new change). Paths: all exist. No pytest gate: the tour is the test; `dev/tour/*.py` is not under `just gate`.

## Tests to add
None.

## Report requirements
Standard report. List: needles changed (script, name, old -> new, one line each), SVG count changed, narratives edited (section numbers), SVGs changed without a text reason.

## Escalation triggers
- A needle can only be satisfied by changing TUI source: stop, report the screen and the word.
- A tour step fails for a reason that is not text (crash, `TourFailed` on state): stop and report.
- The second run differs: report the file; do not commit a nondeterministic output.

## Blocked
(implementer writes here)

## Decision
(supervisor or orchestrator writes here)
