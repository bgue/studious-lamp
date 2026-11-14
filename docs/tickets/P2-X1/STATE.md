# P2-X1 STATE  r=2 base=7a0b140b C=0 ck=0 gate=n/a wt=/home/user/wt/p2-x1
## BOARD
S1 p mrg f 4b42fa5 store+helper; mrg 77e9b51; review P 3 LO
T04 t mrg f 77a1d8c openapi diff; +became-required test
T01 t mrg f b7d64e4 header on /commands; 270 P
T03 t mrg f 9eb471c five MCP tools take key; 38 P
T02 t stg f - client key on retry; waits T01
T05 t stg f - baseline + just step; waits T04; Q1 rule in text; keep errors.py rows in step
T06 t stg l - api-compat.md; waits T04; carries Q1 rule
T07 t stg f - walking tests; waits S1 T01 T03
T08 t stg f - demo driver; waits T02 T03 T05
T09 t stg l - runbook + AGENTS rows; waits T08
## DEC
D1 2026-11-13 purge job deferred; setting kept, rows retained (plan, DEFERRED row)
D2 2026-11-13 T04 limited to diff_openapi; wiring in `just check` is T05
D4 2026-11-13 header Idempotency-Key and body field both allowed; differ -> 422 invalid_idempotency_key (T01)
D5 2026-11-13 T03 covers write_tools.py five tools; module tools (punch, requisition, awp, thread, correspondence, derivation, materials, schedule, iwp) = T03b later; API has no agent create route, only accept/reject
D3 2026-11-13 proposal rule and action paths keep key None; only agent `propose` takes a key
## SEC
none yet; SR-X1 at DONE: S1, T01, T03, T07 plus I6 B2, T02
## OPEN
Q3 proposals.submit runs budget and precheck before propose's replay: a keyed retry may be refused instead of replaying (T03 author). Needs a test in T07 and, if real, a fix piece | needs orch | raised T03
Q1 answered 2026-11-13 owner: baseline refreshed only as a release step; a breaking change between releases needs an APPROVALS line naming what breaks and a note in api-compat.md; removals are deprecated for at least one release first. T05 and T06 carry this rule.
## NEXT
1. Orchestrator: worktrees /home/user/wt/x1/t01, /t03; run T01 and T03 (disjoint); T04 attempt 2 finishes.
2. r3 after T04 merged: write T05 (Q1 rule, errors table in step with OpenAPI), T06; T02 once T01 merged.
3. Decide T03b (module tools) vs fold into T07 scope; T07 needs S1 T01 T03.
4. Then T08, T09; DONE round after SR-X1.
## REFS
T01 t mrg f b7d64e4 header on /commands; 270 P
Provided test packages/tl-schema/tests/test_compat_openapi.py; stub diff_openapi in tl_schema/compat.py.
Seams: commands.py:46, proposals.py:499,573,636, tl_api/commands.py:359,:503.
## TRAPS
Heavy test slots tight; trunk whole-suite run holds one slot: narrow gate paths only. tl-api/tl-schema whole dir OOM (exit 137); tl-schema test_offline_classes.py ~3.5 GB (DEFERRED): name schema files, not the dir. No platform.yaml file; settings live in tl_core/settings/registry.py.
