# P2-I5-S7 — SR3 fixes: pack attach clearance, weekly sign-off hash, walk seeds a week

Status: ready
Tier: sonnet
Kind: piece
Review: full
Labels: security, confidentiality, tui, tests
Branch: `p2/i5-s7-sr3-fixes`
Worktree: harness-created under `/home/user/wt/i5/s7` (from `p2/i5` head)

## Goal
Close the three SR3 findings on P2-I5 (wave review, 2026-11-12). Each fix comes with a test that fails before it.

1. **F1 MD** `packages/tl-cli/src/tl_cli/awp_pack.py:53,66-69`. `tl awp iwp pack N --attach` builds the pack at the
   session viewer's clearance and stores it in the IWP's `pack` file slot; file reads are gated only by the IWP's own
   class (`tl_core/files/queries.py:80`). So a reader cleared for the IWP but not for a restricted drawing or MTO
   item downloads their keys and titles. Fix (orchestrator decision): with `--attach`, build the pack as a viewer at
   the IWP's own class (the lowest clearance that can read the IWP), so the stored file holds only what every reader of
   the IWP may see; without `--attach` the pack stays at the session viewer's clearance. Test: a world with an
   internal IWP and a restricted drawing in its scope; a restricted session runs `--attach`; the stored HTML does not
   contain the drawing's key or title, and the non-attached `--out` file does.
2. **F2 LO** `packages/tl-tui/src/tl_tui/widgets/weekly_screen.py:339,348`. Sign off and Issue fetch the record hash
   when the key is pressed, so an edit between reading the panel and pressing the key is signed without a stale
   refusal. Fix: keep the hash fetched when the panel is shown and send that one. Test: show the panel, change the IWP
   through a command, press the key: the stale-hash refusal appears and nothing is signed.
3. **F3 LO** `packages/tl-api/tests/test_confidentiality_walk.py:164`. The walk asks for week `2026-W01` with no plan
   seeded, so the weekly-plan route and tool answer 404 to all five readers and never meet a hidden commitment
   (AGENTS.md rule: the walk must see hidden records). Fix: seed a weekly plan for that week holding a commitment on
   an IWP that some walk readers may not see, in the walk's seed, so the route and the MCP tool are walked with a
   hidden row present; the expectations follow the existing table (the reader who may not see it gets the same
   answer as for a missing row, and the "some commitments not shown" note is allowed by spec S4a).

## Context (read these, nothing else up front)
- The three files above and their tests; `packages/tl-core/src/tl_core/files/queries.py` (70-95);
  `packages/tl-modules/awp/src/tl_mod_awp/pack.py` (how the viewer reaches the queries); `docs/reports/P2-I5/{T07a,T06a,T11a1}.md`

## Allowed paths
- `packages/tl-cli/src/tl_cli/awp_pack.py`, `packages/tl-cli/tests/**`
- `packages/tl-tui/src/tl_tui/widgets/weekly_screen.py`, `packages/tl-tui/tests/**`
- `packages/tl-api/tests/**`, `packages/tl-mcp/tests/**`
- `docs/reports/P2-I5/S7.md`
- Not `schema/`, not other `src/`; a needed core change goes under Blocked.

## Acceptance
```
NODE_OPTIONS=--max-old-space-size=6144 just check
just gate packages/tl-cli/tests packages/tl-tui/tests
just gate packages/tl-api/tests/test_confidentiality_walk.py packages/tl-mcp/tests
```
One pytest session at a time (the box is shared). Mutation: one sentinel plus at most 3 targeted mutants on the F1
clearance choice and the F2 hash, reported in 3 lines.

## Report requirements
Builder return <= 15 lines; report <= 60 lines, one line per finding with root cause and fix. Commit subjects
`P2-I5-S7: ...`; the commit body ends with the trailer lines `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`
and `Claude-Session: https://claude.ai/code/session_01MSkuXpRjf5XzVwbAVQNqK4`. No model names in committed files.

## Blocked
(builder writes here)

## Decision
(orchestrator writes here)
