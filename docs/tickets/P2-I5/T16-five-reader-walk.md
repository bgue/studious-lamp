# P2-I5-T16 — Five-reader walk of every new route and tool

Status: staged (needs T11c, T11b, T04, S4b merged)
Tier: haiku
Kind: ticket
Review: full
Labels: tests, confidentiality, api, mcp, cli, tui
Depends on: T11c, T11b, T04, S4b
Branch: `p2/i5-t16-five-readers`
Worktree: harness-created under `/home/user/wt/i5/t16` (from `p2/i5` head)

## Goal
AGENTS.md: a new route, tool, feed or export that can carry record text needs a walking test as five kinds of reader. This is that test for everything I5 added to read: the API routes (T11a1, T11a2), the embedded and remote client methods (T11b), the MCP tools (T11c), the CLI verbs (T04, T04b, T01, S3's export) and the TUI client reads. It replaces the S6 tests piece.

## Brief references (pasted)
- The five readers (the module walk `packages/tl-modules/awp/tests/test_five_readers.py` and the API walk): `bob` (plain user), `ctl` (document controller), `boss` (admin, a controller: no agent, no privilege), `amy` (named on a privileged record), `bot` (agent; core words closed to agents, so a route or tool may answer 403 to it, never anything else but an answer or a 404).
- Hidden things to classify (a test-only `ConfidentialSource` over a table of ids and classes, as `test_confidentiality_walk.py` 690-735 does): one weekly plan (`restricted`), one IWP committed in an open plan (`restricted`, so its commitment row is dropped with the note), one IWP's scope item (`restricted`), and one IWP clearly `privileged` to `amy` only. Built with `WeekWorld` (`progress_world.py` 362-470) and `ProgressWorld`.
- Per surface, per reader, the rule is the same: (a) every answer is 200 or 404 (or 403 for `bot` on a closed word) and never 5xx or a traceback; (b) the serialized answers hold none of the ids, keys, titles or descriptions of what the reader may not read; (c) a hidden plan, IWP or item answers byte for byte as one that never existed (status, text, body), and a list total counts visible rows only; (d) `list_kpis` and the roll-up change for a reader exactly as a ledger without the hidden records would give (a second ledger or the visible subset recount, as `T03` provided `test_a_hidden_iwp_is_absent_and_the_rest_are_unchanged` does).
- Surfaces and where each walk lives (one file each):
  1. API: `packages/tl-api/tests/test_awp_week_walk.py`: every GET route added by T11a1 and T11a2 (list: `iwps/counts`, `iwps/{n}/progress`, `iwps/{n}/hash`, `progress/rollup`, `kpis`, `weeks`, `weeks/{week}`, `miss-reasons`, `look-ahead`) for each reader with that reader's token (`seeded.tokens`, fixtures imported from `test_confidentiality_walk`: `harness`, `seeded`); a count assertion proves the walk found nine routes; the route list is read from `harness.app.openapi()["paths"]` and the test fails when an awp GET route under `/awp/weeks`, `/awp/progress`, `/awp/kpis`, `/awp/iwps/counts`, `/hash` or `/look-ahead` is not in the walked list (L-P1-I3-11).
  2. Embedded and remote clients (the TUI reads): same file, `EmbeddedClient.for_target(db, actor=...)` and `ApiClient` over the test client per reader: `get_weekly_plan`, `list_weekly_plans`, `get_iwp_progress`, `list_iwp_counts`, `list_kpis`, `get_look_ahead` agree with each other for every reader (the T11b `PASS same`) and obey (a) to (d).
  3. MCP: `packages/tl-mcp/tests/test_mcp_week_walk.py` (harness of `test_confidentiality_walk.py` there): the five T11c tools as each reader (`bot` is the agent identity), (a) to (d); a tool name outside `MCP_ACTIONS` is refused.
  4. CLI: `packages/tl-cli/tests/test_awp_week_walk.py`: `week show|ls|ppc`, `iwp progress`, `export progress`, `roc show` as the dev owner and as the lowest viewer (no session, a non-dev ledger via `Cli`'s env without `TL_ENV=dev`): (a) to (c), no `Traceback`, no id.

## Context (read these, nothing else)
- `packages/tl-api/tests/test_confidentiality_walk.py` (1-70, 180-260, 690-830), `packages/tl-mcp/tests/test_confidentiality_walk.py` (the MCP readers), `packages/tl-modules/awp/tests/{test_five_readers.py (1-40), progress_world.py (362-470)}`, `packages/tl-cli/tests/test_awp_week.py` (the `Built` pattern)
- `docs/reports/P2-I5/{T11a1,T11a2,T11b,T11c,T04}.md`

## Allowed paths
- the three new test files above, `docs/reports/P2-I5/T16.md`; no source change (a leak is a finding: write it under Blocked with the reader, the route and the text, and stop)

## Acceptance
```
just check
just gate packages/tl-api/tests/test_awp_week_walk.py packages/tl-mcp/tests/test_mcp_week_walk.py packages/tl-cli/tests/test_awp_week_walk.py
```

## Tests to add
The files above. Each test names the reader in its parametrization id.

## Escalation triggers
- Any leak (hidden id or text in an answer, or a hidden record answering differently from a missing one): stop and report it as a security finding `F<n> HI|MD|LO file:line`; do not edit source.

## Report requirements
Standard report (`docs/templates/haiku-report.md`), <= 60 lines, deviations first; pins updated outside Allowed paths listed. Commit subjects `P2-I5-T16: ...`; trailer is the attribution lines your harness requires then `Claude-Session: https://claude.ai/code/session_01MSkuXpRjf5XzVwbAVQNqK4`. No model names in committed files.

## Blocked
(implementer writes here)

## Decision
(supervisor or orchestrator writes here)
