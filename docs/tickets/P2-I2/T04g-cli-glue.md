# P2-I2-T04g — Glue: CLI groups `awp iwp` and `constraint`, readiness hook line (STAGED)

Status: staged (dispatch after S4 is merged and T04d, T04e1, T04e2 are merged)
Tier: haiku
Kind: ticket
Review: full
Labels: cli, wiring, registry
Depends on: T04d, T04e1, T04e2, S4
Branch: `p2/i2-t04g-cli-glue`
Worktree: harness-created under `/home/user/wt/i2/t04g` (from `p2/i2` head)

## Goal
Make the new verbs reachable and subscribe the readiness engine. Three wiring edits, about 25 lines in all; no logic.

## Brief references (pasted)
> 1. `packages/tl-cli/src/tl_cli/awp.py`: add `iwp_app = typer.Typer(help="Interim work packages (IWPs).", no_args_is_help=True)`, `app.add_typer(iwp_app, name="iwp")`, then `awp_iwp_read.register(iwp_app)` and `awp_iwp_write.register(iwp_app)`
>    (reads first, as the file's comment says for the other groups); import both modules in the existing import line. If T04d2 (readiness CLI) is merged, its `register` joins the same way; if not, leave it out.
> 2. New `packages/tl-cli/src/tl_cli/constraint.py`: `app = typer.Typer(help="Constraints on records (core).", no_args_is_help=True)`, `constraint_read.register(app)` then `constraint_write.register(app)`; one line in
>    `packages/tl-cli/src/tl_cli/main.py` next to `app.add_typer(awp.app, name="awp")`: `app.add_typer(constraint.app, name="constraint")` and its import.
> 3. `packages/tl-modules/awp/src/tl_mod_awp/module.py`: the one hook line the S4 report (`docs/reports/P2-I2/S4.md`, "hook" section) gives for `readiness.hooks.on_event`, at the place the module registers its projectors. Copy the line from the report; do not design it.
> Also: `AWP_COMMANDS` already carries the four S3 commands (checked r6); `MCP_ACTIONS` belongs to T09b (tools do not exist yet) and the TUI palette to the screen tickets: neither is here.
> Consequential pins (rule 12, union form, listed in the report): the CLI help or command-tree snapshots under `packages/tl-cli/tests/expected/` or a command-count pin that breaks only because the two groups now exist; module pins
> (`tests/services/test_modules.py` and similar) that break only because the hook is registered.

## Context (read these, nothing else)
- `packages/tl-cli/src/tl_cli/awp.py`, `packages/tl-cli/src/tl_cli/main.py` (lines 120-195), `packages/tl-modules/awp/src/tl_mod_awp/module.py`, `docs/reports/P2-I2/{S4,T04d,T04e1,T04e2}.md`

## Allowed paths
- the three files above plus `packages/tl-cli/src/tl_cli/constraint.py` (create); consequential pins as stated; `dev/accept/P2-I2/T04g.py` (create), `docs/reports/P2-I2/T04g.md` (create)

## Acceptance
```
NODE_OPTIONS=--max-old-space-size=6144 just check
uv run python dev/accept/P2-I2/T04g.py
just gate packages/tl-cli/tests/test_cli_awp.py packages/tl-modules/awp/tests tests/services/test_modules.py
```
`T04g.py`: `tl awp iwp --help` lists ls show scope create ... ; `tl constraint --help` lists ls show groups raise assign clear withdraw; an end-to-end line on a SQLite ledger: create an IWP, raise a constraint, `constraint ls` shows it, clear it;
an event of a watched type reaches `readiness.hooks.on_event` (one `PASS` per check; final `T04g ok`).

## Tests to add
None (S5).

## Report requirements
Standard report, <= 60 lines, deviations first, list every pin touched. Commit subjects `P2-I2-T04g: ...`; trailer as in the other tickets. No model names in committed files.

## Escalation triggers
- Stop and report *Blocked* if the S4 report gives no hook line, or if more than the stated pins break, or the diff exceeds about 60 lines outside pins.

## Blocked
(implementer writes here)

## Decision
(supervisor or orchestrator writes here)
