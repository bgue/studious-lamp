# P2-X1 STATE  r=3 base=7a0b140b C=2 ck=0 gate=n/a wt=/home/user/wt/p2-x1
## BOARD
S1 p mrg f 4b42fa5 store+helper; mrg 77e9b51; review P 3 LO
T04 t mrg f 77a1d8c openapi diff; +became-required test
T01 t mrg f b7d64e4 header on /commands; 270 P
T03 t mrg f 9eb471c five MCP tools take key; 38 P
T02 t stg f - client key on retry; T01 mrg; r4 (base.py _send, POST /commands/ only)
T05 t mrg f f92108d baseline 1.5 MB stripped + check step
T06 t mrg l 3cd8853 api-compat.md with Q1 rule
T07 t mrg f 49a80b8 walk 5 readers + Q3 x3 green; hash drops expected_version; APPROVALS
S2 p mrg f ac97d72 replay before budget+precheck; APPROVALS; pg at DONE
T08 t stg f - demo driver; waits T02 T05; T03 mrg
T09 t stg l - runbook + AGENTS rows; waits T08
## DEC
D6 2026-11-14 T03b not ticketed: demo item 3 uses create_record via MCP (T03); module tools stay key-less, DEFERRED line in r4
D1 2026-11-13 purge job deferred; setting kept, rows retained (plan, DEFERRED row)
D2 2026-11-13 T04 limited to diff_openapi; wiring in `just check` is T05
D4 2026-11-13 header Idempotency-Key and body field both allowed; differ -> 422 invalid_idempotency_key (T01)
D5 2026-11-13 T03 covers write_tools.py five tools; module tools (punch, requisition, awp, thread, correspondence, derivation, materials, schedule, iwp) = T03b later; API has no agent create route, only accept/reject
D3 2026-11-13 proposal rule and action paths keep key None; only agent `propose` takes a key
## SEC
none yet; SR-X1 at DONE: S1, T01, T03, T07 plus I6 B2, T02
## OPEN
Q3 closed by S2 (T07 att2 must turn its two Q3 tests green)
Q1 answered 2026-11-13 owner: baseline refreshed only as a release step; breaking change between releases needs an APPROVALS line naming what breaks and a note in api-compat.md; removals deprecated one release first. T05 and T06 carry it.
## NEXT
1. Orch: run T05 T06 T07 (disjoint paths; x1/t05 t06 t07); T07 may return Q3 RED: relay it, S2 piece follows.
2. r4: write T02 (client key on retry: base.py _send; POST /commands/ gets a generated key, one retry on reset/timeout with the same key; caller key kept) once slot free; T08 after T02 and T05.
3. T09 after T08. Add DEFERRED.md lines (purge job, T03b) in r4 if the file exists.
4. DONE round after SR-X1 (S1 T01 T03 T07 T02, I6 B2).
## REFS
Provided test packages/tl-schema/tests/test_compat_openapi.py; stub diff_openapi in tl_schema/compat.py.
Seams: commands.py:46, proposals.py:499,573,636, tl_api/commands.py:359,:503.
## TRAPS
Heavy test slots tight; trunk whole-suite run holds one slot: narrow gate paths only. tl-api/tl-schema whole dir OOM (exit 137); tl-schema test_offline_classes.py ~3.5 GB (DEFERRED): name schema files, not the dir. No platform.yaml file; settings live in tl_core/settings/registry.py.
