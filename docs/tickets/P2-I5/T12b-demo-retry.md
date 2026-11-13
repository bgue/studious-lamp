# P2-I5-T12b — Finish the P2-I5 demo (retry of T12 after T12a)

Status: ready (T12a merged into `p2/i5` @997bb280)
Tier: haiku
Kind: ticket
Review: full
Labels: demo, tests
Depends on: T12 (branch `p2/i5-t12-demo` @c6310e4f, blocked at clause 3), T12a (merged)
Branch: `p2/i5-t12b-demo`
Worktree: harness-created under `/home/user/wt/i5/t12b` (from `p2/i5` head)

## Goal
The same Goal and clause list as `docs/tickets/P2-I5/T12-demo.md` (read it whole; it is the spec): `just demo P2-I5`
prints `PASS clause N` for N in 1 2 3 4 5 6 9 10 on SQLite, then on Postgres, and no `DEMO FAILED`.

## Start here (do this first)
1. `git cherry-pick c6310e4f` (the T12 demo script, driver and report; new files, no conflict expected).
2. Read `docs/reports/P2-I5/T12.md` (what passed, deviations, the five open questions) and
   `docs/reports/P2-I5/T12a.md` (what T12a added for questions 1 to 3).
3. Continue from clause 3. Clauses 1 and 2 already pass; do not rewrite them.

## What changed since T12 blocked (orchestrator decisions)
- Q1 clause 3: `tl awp iwp show` now prints one line per waived constraint with who waived it and why (T12a gap 4;
  read the exact text from `packages/tl-cli/tests/test_awp_iwp_show_waived.py`).
- Q2 clause 9: D31, the user layer takes `tui.*` keys, so `tl config set tui.landing default --user frank` works.
- Q3 clause 10: MCP tools `propose_progress` and `propose_week_commitment` exist (`packages/tl-mcp/src/tl_mcp/iwp_tools.py`).
  "Refused, excluded with reasons" is shown by: an agent session calling the API for `ClearConstraint` and `CloseWeek`
  is refused `agent_must_propose` (see `test_api_proposals.py::test_an_agent_is_refused_a_waive_and_a_week_close_with_the_reason`),
  and no MCP tool exists for either (the tool list does not name them). Run the T16 files plus
  `packages/tl-mcp/tests/test_mcp_propose_awp.py` from the demo as the ticket says.
- Q4 clause 5: the cost-code row needs the WBS -> CWP -> IWP chain in the demo world. Copy the minimum of
  `dev/demos/P2-I1.sh` 148-175 (cost import, `tl load` of `wbs-sample.csv` with the awp-wbs loader) and the CWA / path /
  CWP allocate / release steps that follow in that file, so the IWP the demo progresses sits under a CWP allocated from a
  WBS leaf that carries the `=cmd` cost code. Map the `=cmd` cost code on that WBS node with the verb behind
  `WBSNode.CostCodesMapped` (`tl awp wbs map <code> --cost-code <cc>`, P2-I1.sh line 268 shows the form). If the IWPs
  already in the world cannot be put under that CWP, create the demo's IWPs from it instead.
- Q5: run both backends (Postgres is up on localhost:5432).

## Allowed paths
- `dev/demos/P2-I5.sh`, `dev/demos/p2_i5_demo.py`
- `docs/reports/P2-I5/T12.md` (append a "Retry (T12b)" section; <= 25 added lines)
- no source change (a missing verb or a wrong text is a finding under Blocked, with the clause and the command)

## Acceptance
```
just check
just demo P2-I5
```

## Report requirements
Append to `docs/reports/P2-I5/T12.md`: the PASS lines per backend and any new deviations. Builder return <= 15 lines.
Commit subjects `P2-I5-T12b: ...`; trailer is the attribution lines your harness requires then
`Claude-Session: https://claude.ai/code/session_01MSkuXpRjf5XzVwbAVQNqK4`. No model names in committed files,
including the report (do not discuss trailers or models there).

## Blocked
(implementer writes here)

## Decision
(orchestrator writes here)
