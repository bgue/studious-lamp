# P2-SEED-T03 — The tour and demos use the demo project

Status: ready
Tier: haiku
Kind: ticket
Review: full
Labels: tests, docs
Depends on: S1, T01, T02 (merged on p2/seed)
Branch: `p2/seed-t03-tour`   (from p2/seed)

## Goal
A new tour, `dev/tour/wave1.py` (`just tour wave1`), builds P200 once with the generator and then drives the real TUI
over it, so the M3 and M4 terminal screens are shown on a full, realistic ledger instead of a hand-made one.
It follows `dev/tour/highlights.py` (same method: `Workspace`, frozen clock, `tk.shot_tui`, leak check). It must run on
SQLite with no network. It also exports `seed_demo_project(ws)`, the one place a tour or demo gets the project.

## Interfaces (verbatim at the branch point)
```python
# dev/seed/demo_project/__main__.py
def run(target: DbTarget, *, seed: int | str = 2026, sections: Sequence[str] | None = None,
        objects: Path | None = None) -> list[Done]: ...
# tl_adapters.db: as_target(str) -> DbTarget
# core.py: PASSWORD = "p200-demo-pass"; users mokafor (admin), treyes (materials), lhartmann (awp), cbrooks ...
# project id "P200" (dev.seed.demo_project.world.PROJECT)
```
Screens, opened directly: `app.push_screen(Screen(app.client, "P200"))` after `tk.until(pilot, lambda: len(app.query("RecordGrid")) > 0, "the shell")`:
`tl_tui.widgets.wbs_screen.WbsScreen`, `cwp_register.CwpRegisterScreen`, `path_screen.PathScreen`,
`receipt_log.ReceiptLogScreen`, `stock_screen.StockScreen`, `mto_screen.MtoLinesScreen`, `movement_screen.MovementLogScreen`.

## Context (read these, nothing else)
- `dev/tour/highlights.py` (pattern: `main`, one `section_*`, `tk.run_tui`)
- `dev/tour/tourkit.py` lines 49–130 (`Clock`, `freeze`), 221–260 (`Workspace`), 538–576 (`shot_tui`, `run_tui`)
- `dev/demos/p2_i1_demo.py` lines 140–210 and `dev/demos/p2_i3_demo.py` lines 495–530 (opening these screens headless)
- `dev/seed/demo_project/__main__.py` (`run`, `prepare`)
may explore: `packages/tl-tui/src/tl_tui/main.py` (`build_app` signature only)

## Allowed paths
- `dev/tour/wave1.py` (create)
- `tests/tools/test_tour_wave1.py` (create)
- `justfile` (only the `tour` recipe: accept `wave1`; and its comment line)
- `docs/reports/P2-SEED/T03.md`

## Steps
1. `seed_demo_project(ws)`: `ws.db` is the Workspace's SQLite file; call `run(as_target(str(ws.db)), objects=ws.root / "objects")`
   then set `TL_SCHEMA_DIR` to `str(OVERLAY)` (from `dev.seed.demo_project.overlay`) so the clients read the project's types.
   Do not seed twice (the generator refuses a used ledger). Seed before `tk.freeze()` effects matter: if the frozen clock
   and the project calendar (today 2026-11-06) disagree, set the Clock to 2026-11-06 09:00 after seeding and say so in the report.
2. One scenario per screen group, each a `tk.shot_tui` with needles that are real P200 text (read them from the screen
   in a first run): WBS (4–5 levels), CWP register (40+ rows, filter shown once), path of construction (v1 and v2), receipt
   log (rows without an MTR), stock, take-off lines (some short), movements. Name files `01-wbs` … `07-movements`.
   Actor `user:treyes` for materials screens, `user:lhartmann` for awp, admin `user:mokafor` only where needed.
3. `main(argv)`: `--out` default `docs/reports/tour/wave1`; print each file; exit 1 on `TourFailed` or a leak (`tk.report_leaks()`).
4. `justfile` `tour` recipe: add `wave1` beside `highlights`, with no other change.
5. Test: `tests/tools/test_tour_wave1.py` runs `main(["--out", str(tmp_path)])` once, asserts exit 0, ≥ 7 `.svg` files, and
   that `seed_demo_project` is the only seeding call (grep the module text for `init", "--dev"` absent).

## Acceptance
- `NODE_OPTIONS=--max-old-space-size=6144 just check` exit 0
- `just gate tests/tools/test_tour_wave1.py | tail -20 | tee .gate/summary.txt` ends `gate: PASS`
- `just tour wave1 /tmp/wave1-tour` runs; paste the list of files written in the report. Do not commit the SVGs.

## Report requirements
Standard report; paste the `gate:` line and the file list only. Name any screen that could not be opened and why.

## Escalation triggers
- A screen needs a TUI or schema change to open: stop, write *Blocked*.
- The tour needs a network or Postgres: stop.
- Run time over 10 minutes: report the per-section time, do not cut screens without asking.

## Blocked
(implementer writes here)

## Decision
(supervisor or orchestrator writes here)
