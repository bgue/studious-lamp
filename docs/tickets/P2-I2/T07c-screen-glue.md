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

## Brief (D33; names checked in the merged tree)
1. `IwpScreen(client, project, number)` (`widgets/iwp_register.py`, the modal one-IWP page; it already holds `client`, `project`, `number`): add `Binding("r", "readiness", ...)` pushing `ReadinessScreen(self.client, self.project, self.number)` (`widgets/readiness_screen.py`) and `Binding("c", "constraints", ...)` pushing `ConstraintScreen(self.client, self.project, subject_key=self.number)` (`widgets/constraint_screen.py`; subject_key is the IWP key as the per-record log takes it). Extend `KEY_HINTS` with `r Readiness  c Constraints`. Do NOT touch `IwpRegisterScreen` bindings: its `r` is the Ready state filter (T07b). Local imports inside the action methods (as `app._push_awp`).
2. Palette: `packages/tl-tui/src/tl_tui/commands.py` gets `AppCommand` rows (same shape as `cwps`, key `""`) named `iwps` (IWP log, `IwpRegisterScreen(client, project)`), `constraints` (`ConstraintScreen(client, project)`), `backlog` (`BacklogScreen(client, project)`, T08 is merged; it also holds the sizing view on `z`). In `app.py` add the three classes to the `screens` dict of `_push_awp` (import them there) and three one-line `action_iwps`, `action_constraints`, `action_backlog` methods beside `action_cwas`.
3. Nothing in `tl_tui/embedded.py`; no screen logic.

## Context (read these, nothing else)
- `docs/reports/P2-I2/{T04b,T07a,T07b,T04c2}.md`, `packages/tl-tui/src/tl_tui/widgets/iwp_register.py`, `packages/tl-tui/src/tl_tui/app.py` (`_push_awp` only), `packages/tl-tui/src/tl_tui/commands.py`

## Allowed paths
- `packages/tl-tui/src/tl_tui/widgets/iwp_register.py` (IwpScreen only), `packages/tl-tui/src/tl_tui/commands.py`, `packages/tl-tui/src/tl_tui/app.py` (the `_push_awp` table and the three actions), consequential pins (union form, listed; `packages/tl-tui/tests/test_palette.py`, `test_awp_nav.py`), `dev/accept/P2-I2/T07c.py`, `docs/reports/P2-I2/T07c.md`

## Acceptance
```
NODE_OPTIONS=--max-old-space-size=6144 just check
uv run python dev/accept/P2-I2/T07c.py
just gate packages/tl-tui/tests/test_palette.py packages/tl-tui/tests/test_awp_nav.py
```
`T07c.py` (headless Textual pilot, as the T07b script): open `IwpScreen` for the PIP IWP (not the first IWP, which has no constraints), `r` shows the readiness screen with check names, Esc back, `c` shows the constraint log filtered to the IWP, palette lists `iwps`, `constraints`, `backlog`; `T07c ok`.

## Report requirements
Standard, <= 60 lines, deviations first, pins listed. Commits `P2-I2-T07c: ...`, trailer as other tickets.

## Escalation triggers
- Stop if a screen constructor needs a change in T04b/T07a/T07b files beyond the key binding, or the diff passes ~60 lines.

## Blocked
(implementer writes here)

## Decision
(supervisor or orchestrator writes here)
