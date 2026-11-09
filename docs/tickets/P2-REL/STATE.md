# P2-REL STATE  r=1 base=8c5fc67 C=C0 ck=- gate=n/a wt=/home/user/wt/p2-rel
## BOARD
S1 p stg f - installable wheels; schema_root locator; data in wheels
S2 p stg f - real server mode; bind policy; plain-http refusal; human gate
T01 t stg l - version 0.1.0; --version flags; needs S1
T02 t stg f - /health version; TUI minor warning; needs S2
T03 t stg f - release-build, check_wheels; needs S1 T01
T04 t stg l - starter bundle; needs T03; WAVE2
T05 t stg f - smoke.sh clean install, both paths; needs S2 T03 T04; WAVE2
T06 t stg l - runbook terminal-release; needs T05; WAVE2
T07 t stg l - CI release-smoke job; owner may cut; needs T05
## DEC
D1 2026-11-07 CLI stays an operator tool, no remote mode; remote CLI to DEFERRED; README Q-REL2
D2 2026-11-07 two pieces not one: wheel data lookup (S1) and prod bind/auth rules (S2) are core and security, not Haiku
D3 2026-11-07 supported = Linux, macOS, WSL2; Python 3.12; Postgres 16 shared; same major.minor; README table
D4 2026-11-07 7 tickets under 10: no PLANCHK; cut order T07 then T02
D5 2026-11-07 starter = tarball (SQLite P200 ledger, overlay schema, START.txt), loopback only; real server starts empty
## SEC
none yet (rows Sec-1..Sec-7 in README; S2 carries Sec-1..4, T03/T04 Sec-6, T05 Sec-5)
## OPEN
Q1 R-1 supported definition; default in README table needs owner (or default applies) raised README
Q2 Q-REL1 release location (default: wheel dir plus SHA256SUMS, find-links) needs owner raised README
Q3 Q-REL3 first version (default 0.1.0) needs owner raised README
Q4 S2 is an auth-path piece: human gate before merge needs orch raised S2
Q5 does TL_ENV=demo work with the object store? T04 checks, falls back to dev needs builder raised T04
## NEXT
1. Orchestrator: after wave 2 close dispatch batch 1: S1 and S2 (disjoint paths, 2 slots)
2. After S1 merged: T01 and T03; after S2 merged: T02 (batch 2, one workflow of 2-3)
3. Wave 2 merged on trunk: then T04, T05, then T06 (T07 if kept)
4. Orchestrator interface lines: S1 tl_schema.resources.schema_root; S2 check_bind env arg, prod_like, TL_ALLOW_PLAIN_HTTP; T02 /health version field + OpenAPI regen
5. DONE: whole-suite gate, gate-pg on touched dirs, demo clauses 1-5 of README, security review scoped to Sec rows
## REFS
Plan and tables: docs/tickets/P2-REL/README.md. Specs: S1-installable-wheels.md, S2-real-server-mode.md, T01..T07.
Facts: schema paths parents[4|5] in tl_schema registry/linkml_render/generate, tl_core auth/access_words, auth/module_roles, settings/registry;
check_bind in tl_api/settings.py; TUI remote in tl_tui/main.py and remote.py; no CLI remote mode.
## TRAPS
none yet. Branch worktrees: /home/user/wt/p2-rel-<id>. No test suite was run this round.
