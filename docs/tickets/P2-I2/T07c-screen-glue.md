# P2-I2-T07c — Glue: IWP screen keys to readiness and constraint log, nav, palette (STAGED)

Status: staged (dispatch when T04b, T07a, T07b are merged; refine names from their reports)
Tier: haiku
Kind: ticket
Review: full
Labels: tui, wiring
Depends on: T04b, T07a, T07b
Branch: `p2/i2-t07c-screen-glue`
Worktree: harness-created under `/home/user/wt/i2/t07c`

## Goal
Make the three new screens reachable. Wiring only, <= 60 lines outside pins: no screen logic (L-P2-WEB1-1).

## Brief (D33)
1. IWP screen (`widgets/iwp_register.py`, T07b): `r` pushes the readiness screen for the IWP (T07a class and constructor from its report), `c` pushes the constraint log filtered to the IWP's key (T04b per-record log, constructor from its report). Add both to that screen's `KEY_HINTS`; the IWP log row Enter still opens the IWP screen.
2. Palette and nav: one entry each for IWP log, constraint review (T04b) and, if T08 is merged, the sizing screen; same registry the CWP log uses (`tl_tui` palette and `nav` tables; find them from `widgets/cwp_register.py` usage); pins of the palette count in union form.
3. Nothing in `tl_tui/embedded.py` beyond a `Protocol` method already added by T04c2/T04b/T07a/T07b.

## Context (read these, nothing else)
- `docs/reports/P2-I2/{T04b,T07a,T07b,T04c2}.md`, `packages/tl-tui/src/tl_tui/widgets/iwp_register.py`, `packages/tl-tui/src/tl_tui/app.py` (palette and nav tables only, grep `cwp`)

## Allowed paths
- `packages/tl-tui/src/tl_tui/widgets/iwp_register.py`, the palette and nav table files the grep names (one line each), consequential pins (union form, listed), `dev/accept/P2-I2/T07c.py`, `docs/reports/P2-I2/T07c.md`

## Acceptance
```
NODE_OPTIONS=--max-old-space-size=6144 just check
uv run python dev/accept/P2-I2/T07c.py
just gate packages/tl-tui/tests/test_palette.py packages/tl-tui/tests/test_nav.py
```
`T07c.py` (headless Textual pilot, as the T07b script): open the IWP screen, `r` shows the readiness screen with check names, Esc back, `c` shows the constraint log filtered to the IWP, palette lists the three entries; `T07c ok`.

## Report requirements
Standard, <= 60 lines, deviations first, pins listed. Commits `P2-I2-T07c: ...`, trailer as other tickets.

## Escalation triggers
- Stop if a screen constructor needs a change in T04b/T07a/T07b files beyond the key binding, or the diff passes ~60 lines.

## Blocked
(implementer writes here)

## Decision
(supervisor or orchestrator writes here)
