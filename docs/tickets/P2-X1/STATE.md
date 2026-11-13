# P2-X1 STATE  r=1 base=237a1a6b C=0 ck=0 gate=n/a wt=/home/user/wt/p2-x1
## BOARD
S1 p disp f - idempotency store, helper, call sites; gated 95
T04 t disp f - openapi diff; test + stub committed
T01 t stg f - route header; waits S1 helper signature merged
T03 t stg f - MCP tool arg; waits S1
T02 t stg f - client key on retry; waits T01
T05 t stg f - baseline + just step; waits T04; owner approves refresh rule
T06 t stg l - api-compat.md; waits T04
T07 t stg f - walking tests; waits S1 T01 T03
T08 t stg f - demo driver; waits T02 T03 T05
T09 t stg l - runbook + AGENTS rows; waits T08
## DEC
D1 2026-11-13 purge job deferred; setting kept, rows retained (plan, DEFERRED row)
D2 2026-11-13 T04 limited to diff_openapi; wiring in `just check` is T05
D3 2026-11-13 proposal rule and action paths keep key None; only agent `propose` takes a key
## SEC
none yet; SR-X1 at DONE: S1, T01, T03, T07 plus I6 B2, T02
## OPEN
Q1 answered 2026-11-13 owner: baseline refreshed only as a release step; a breaking change between releases needs an APPROVALS line naming what breaks and a note in api-compat.md; removals are deprecated for at least one release first. T05 and T06 carry this rule.
## NEXT
1. Orchestrator: create worktrees /home/user/wt/x1/s1, /home/user/wt/x1/t04; run S1 and T04.
2. APPROVALS line for table + setting before S1 merge.
3. r2: read S1 report for the check/record signatures; write T01, T03, then T05, T06.
4. Then T02, T07, T08, T09; DONE round after SR-X1.
## REFS
Provided test packages/tl-schema/tests/test_compat_openapi.py; stub diff_openapi in tl_schema/compat.py.
Seams: commands.py:46, proposals.py:499,573,636, tl_api/commands.py:359,:503.
## TRAPS
Heavy test slots tight (P2-I6 workflow live): narrow gate paths only. No platform.yaml file; settings live in tl_core/settings/registry.py.
