# P2-I5-T12a — Close the four gaps the demo found (T12 blocked at clause 3)

Status: staged (next slice; T12 is retried after this merges)
Tier: sonnet
Kind: piece
Review: full
Labels: mcp, settings, cli, access
Depends on: T12 report `docs/reports/P2-I5/T12.md` on branch `p2/i5-t12-demo` @c6310e4
Branch: `p2/i5-t12a-demo-gaps`
Worktree: harness-created under `/home/user/wt/i5/t12a` (from `p2/i5` head)

## Goal
The merged code meets demo clauses 3, 9 and 10 of `docs/tickets/P2-I5/README.md` "Demo clauses". Four gaps:
1. **Clause 10, MCP proposals.** `propose_progress` and `propose_week_commitment` are registered in
   `tl_mod_awp.module.PROPOSABLE` but no MCP tool files them. Add both to `packages/tl-mcp/src/tl_mcp/` on the
   pattern of `propose_iwp_scope` (`iwp_tools.py` 172-200 and its `register_iwp_tools` entry), with the closed-list
   lines the MCP tool list tests pin. Accepting one runs the command as the accepting person (already wired by
   `proposals`).
2. **Clause 10, agent refusals.** Prove with a test that an agent principal is refused `ClearConstraint` as a waive
   and `CloseWeek` on the API and MCP paths, with a reason. If either is not refused at runtime today, refuse it in
   the authorizer path the other agent-excluded commands use (find it from `packages/tl-api/tests/test_auth_review.py`
   `AGENT_MAY_NOT`, which is a test-side table only). No new access word.
3. **Clause 9, personal landing.** `tui.landing` declares `scopes: [platform, user]`, but
   `tl_core/settings/layers.py` `allows_layer` lets only `ui.*` keys have a user layer, so
   `tl config set tui.landing default --user frank` is refused. Decision D31 (orchestrator, core gate): the user layer
   also takes `tui.*` keys (`USER_KEY_PREFIXES = ("ui.", "tui.")`, the refusal text names both). Add a test that a
   `tui.*` user-scoped key is settable at the user layer and that a non-UI user-scoped key is still refused.
4. **Clause 3, waived constraint on the package.** `tl awp iwp show` prints only `open constraints n`. Print one line
   per waived constraint of the IWP with who waived it and why (the read S4b gives the constraint read; reuse it, do
   not query events). Update the CLI snapshot or text test that pins `iwp show`.

## Context (read these, nothing else)
- `docs/reports/P2-I5/T12.md` (on `p2/i5-t12-demo`), `docs/reports/P2-I5/S4b.md`, `docs/reports/P2-I5/S4a.md`
- `packages/tl-mcp/src/tl_mcp/iwp_tools.py`, `packages/tl-modules/awp/src/tl_mod_awp/module.py` 76-93
- `packages/tl-core/src/tl_core/settings/layers.py` 15-100
- `packages/tl-cli/src/tl_cli/awp_iwp_read.py` 60-135

## Allowed paths
- `packages/tl-mcp/src/tl_mcp/**`, `packages/tl-mcp/tests/**`
- `packages/tl-core/src/tl_core/settings/layers.py`, `packages/tl-core/tests/**settings**`
- the authorizer file found in gap 2 and its tests (name it in the report)
- `packages/tl-cli/src/tl_cli/awp_iwp_read.py`, `packages/tl-cli/tests/**`
- `docs/reports/P2-I5/T12a.md`

## Acceptance
```
just check
just gate packages/tl-mcp/tests packages/tl-core/tests/settings packages/tl-cli/tests packages/tl-api/tests
```

## After merge
T12 is retried from its branch with one added note: clause 5's cost-code row needs the WBS -> CWP -> IWP chain in the
demo world (map the `=cmd` cost code on the WBS node with `WBSNode.CostCodesMapped`'s verb).

## Report requirements
Builder return <= 15 lines; report <= 60 lines. Commit subjects `P2-I5-T12a: ...`; trailer is the attribution lines
your harness requires then `Claude-Session: https://claude.ai/code/session_01MSkuXpRjf5XzVwbAVQNqK4`. No model names in
committed files.
