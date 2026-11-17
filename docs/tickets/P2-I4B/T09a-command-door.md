# P2-I4B-T09a — Scaffold commands in the API command door (pre-hook form)

Status: ready (dispatch now; runs beside T09b1)
Tier: haiku
Kind: ticket
Review: full
Labels: api, access
Depends on: S1 (merged)
Branch: `p2/i4b-t09a-command-door`
Worktree: `/home/user/wt/i4b/t09a` (from `p2/i4b` head)

## Goal
The nine scaffold commands are accepted at `POST /commands/<Name>`, so the demo, the simulator actor and the TUI can write. X4 (module hooks) is not on trunk, so this is the pre-hook form the quality module used
(`*_module_specs("quality", PUNCH_COMMANDS)`): one splat line over `tl_mod_scaffold.module.SCAFFOLD_COMMANDS` (model, handler, access word; it has the shape of `PUNCH_COMMANDS`). When X4's `commands` hook lands, that one line moves into
`module.py` (a later round). No word, handler or model changes here. The module's `spec()` is not touched.

## Brief references (pasted)
> Words as built (S1 report): `scaffold.view` read; `scaffold.register`, `.design`, `.erect`, `.inspect`, `.release`, `.modify`, `.dismantle`, `.remove` user words; `scaffold.tag.green` controller.
> Pattern: P2-PUNCH T03 (`docs/reports/P2-PUNCH/T03.md`, deviation 6): the pins that move are `packages/tl-api/tests/test_commands.py` (count and the controller-word set), `test_api_document_controller.py` (module word sets), `test_api_proposals.py` (commands an agent is refused). Update each in union form (add the scaffold names; never remove or loosen a line).
> Authorization is closed for agents: a new command is refused to an agent token until someone allows it; do not allow anything.

## Context (read these, nothing else)
- `packages/tl-api/src/tl_api/commands.py` (imports near line 108; the `COMMANDS` tuple end), `packages/tl-modules/scaffold/src/tl_mod_scaffold/module.py` (`SCAFFOLD_COMMANDS` only)
- `docs/reports/P2-PUNCH/T03.md`, `docs/reports/P2-I4B/S1.md` (Words as built)

## Allowed paths
- `packages/tl-api/src/tl_api/commands.py` (one import, one splat line)
- consequential pins (rule 12, union form, listed): `packages/tl-api/tests/test_commands.py`, `test_api_document_controller.py`, `test_api_proposals.py`; any other API pin that counts commands, found by the gate below
- `packages/tl-api/tests/test_api_scaffold_commands.py` (create)
- `docs/reference/openapi.json` (regenerate with `uv run python -m tl_api.openapi`; T09b1 regenerates it too: a conflict in this file only is resolved by regenerating)
- `docs/reports/P2-I4B/T09a.md` (create)

## Acceptance
```
uv sync --all-packages
just check
just gate packages/tl-api/tests/test_api_scaffold_commands.py packages/tl-api/tests/test_commands.py packages/tl-api/tests/test_api_document_controller.py packages/tl-api/tests/test_api_proposals.py packages/tl-api/tests/test_openapi_baseline.py
```

## Tests to add
`packages/tl-api/tests/test_api_scaffold_commands.py` (pattern: `test_api_punch.py` lines 1-150 for the harness, tokens and a ledger built by commands; the scaffold module's `tests/scaffold_world.py` loaded by path as `test_api_punch.py` loads `punch_world.py`):
the nine names are in `COMMANDS` each once with its module's access word; a request raised and approved through the requisitions world, then `RegisterScaffold` through the door by a person with the word is 200 and the scaffold reads back through the register view; the same by a person without `scaffold.register` is 403 with no event written; `TagScaffoldGreen` by a plain user is 403 and by the controller 200; an agent token is refused `RegisterScaffold`; a body carrying a reserved field (`actor`, `source`) is refused as the other doors refuse it (copy that case from `test_api_punch.py::test_the_door_refuses_a_raised_by_field`).

## Escalation triggers
- A pin cannot be updated in union form; the first gate run shows a failure outside the three named pins and openapi (write which under Blocked); `SCAFFOLD_COMMANDS` lacks a field `_module_specs` reads.

## Report requirements
Standard report (`docs/templates/haiku-report.md`), <= 60 lines, deviations first, <= 5 decisive lines per command; pins updated outside Allowed paths (rule 12) listed. Commit subjects `P2-I4B-T09a: ...`; the commit body ends with the trailer lines your harness requires followed by `Claude-Session: https://claude.ai/code/session_01MSkuXpRjf5XzVwbAVQNqK4`. No model names in committed files. Do not run the whole suite.

## Blocked
(implementer writes here)

## Decision
(supervisor or orchestrator writes here)
