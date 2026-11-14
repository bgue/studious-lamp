# P2-X1 STATE  r=4 base=7a0b140b C=3 ck=0 gate=n/a wt=/home/user/wt/p2-x1
## BOARD
S1 p mrg f 4b42fa5 store+helper; mrg 77e9b51; review P 3 LO
T04 t mrg f 77a1d8c openapi diff; +became-required test
T01 t mrg f b7d64e4 header on /commands; 270 P
T03 t mrg f 9eb471c five MCP tools take key; 38 P
T02 t mrg f 3701a08 client key + one retry on reset/timeout; 38 P
T05 t mrg f f92108d baseline 1.5 MB stripped + check step
T06 t mrg l 3cd8853 api-compat.md with Q1 rule
T07 t mrg f 49a80b8 walk 5 readers + Q3 x3 green; hash drops expected_version; APPROVALS
S2 p mrg f ac97d72 replay before budget+precheck; APPROVALS; pg at DONE
T08 t mrg f 99d2021 demo 6 clauses sq+pg OK
T09 t stg l - runbook + AGENTS rows; ready (T08 mrg)
## DEC
D6 2026-11-14 T03b not ticketed: demo item 3 uses create_record via MCP (T03); module tools key-less; DEFERRED row added r4
D1 2026-11-13 purge job deferred; setting kept, rows retained (DEFERRED row added r4)
D2 2026-11-13 T04 limited to diff_openapi; wiring in `just check` is T05
D4 2026-11-13 header Idempotency-Key and body field both allowed; differ -> 422 invalid_idempotency_key (T01)
D5 2026-11-13 T03 covers write_tools.py five tools; module tools (punch, requisition, awp, thread, correspondence, derivation, materials, schedule, iwp) = T03b later; API has no agent create route, only accept/reject
D3 2026-11-13 proposal rule and action paths keep key None; only agent `propose` takes a key
## SEC
none yet; SR-X1 at DONE: S1, T01, T03, T07 plus I6 B2, T02
## OPEN
Q3 closed: S2 + orchestrator hash fix; T07 Q3 x3 green
Q1 answered 2026-11-13 owner: baseline refreshed only as a release step; breaking change between releases needs an APPROVALS line naming what breaks and a note in api-compat.md; removals deprecated one release first. T05 and T06 carry it.
## NEXT
1. Orch: run T02 and T08 (x1/t02, x1/t08; disjoint). T08 gate = demo on sqlite and postgres, one at a time.
2. After T08 mrg: T09 (ticket staged, lite). T02 and T08 merged = C3.
3. Then DONE round: SR-X1 on S1 T01 T03 T07 T02 (+I6 B2), whole gate, gate-pg on touched dirs, demo, APPROVALS check.
4. Watch: T08 may find an agent HTTP key route missing (clause 3); it reports, MCP half shown.
## REFS
Provided tests: packages/tl-schema/tests/test_compat_openapi.py (T04, green); T02 copy at docs/tickets/P2-X1/provided/test_client_idempotency.py (in tree, red until T02).
Seams: commands.py:46, proposals.py:499,573,636, tl_api/commands.py:359,:503. Client key lives in the body (`idempotency_key`); T02 adds it in `_send`.
Compat: `python -m tl_api.openapi --compat`; baseline docs/reference/openapi.baseline.json; paths are module constants (absolute replaces repo root).
## TRAPS
Heavy test slots tight; trunk whole-suite run holds one slot: narrow gate paths only. tl-api/tl-schema whole dir OOM (exit 137); tl-schema test_offline_classes.py ~3.5 GB (DEFERRED): name schema files, not the dir. No platform.yaml file; settings live in tl_core/settings/registry.py.
