# P2-X4 STATE  r=2 base=9f0bc5ce C=1 ck=0 gate=n/a wt=/home/user/wt/p2-x4
## BOARD
S1 p mrg f 9f0bc5ce hooks merged (C1); 432 P; APPROVALS done
S3 p mrg f 1afa1cfb MCP tools from hooks; 182 P
T01 t mrg f 1ec89b00 CLI groups from hooks; 134 P
S2 p stg f - API table+routers; HOLD: X2 C2 on trunk, then p2/x4 merges trunk
S4 p todo f - waits S2,S3; runs alone
T02 t todo f - scaffold hooks; waits S2,S3,T01
T03 t todo f - fixture ext_demo; waits S4
T04 t todo l - runbook new-module
T05 t todo f - demo driver
T06 t todo l - AGENTS rows
## DEC
D1 2026-11-15 core row type `ModuleCommand` in tl_core/modules.py: CommandSpec lives in tl_api, core cannot import it; S2 maps rows to CommandSpec (+meta); spec S1
D2 2026-11-15 hook names: `commands`, `read_routers`, `tools`, `cli_groups` (plural: awp has 3 routers, corr has 4 CLI groups); plan said singular
D3 2026-11-15 hook failure per module (fixed message, `hook_failures()`), others still load (demo 6); name clash and malformed refs stay fail-fast
D4 2026-11-15 11 installed modules, not 8 (legacy has no commands); S1 declares for all that have the surface
D5 2026-11-15 `meta` empty now; ADR-0029 dec. 7 key `delegation` read by S4; missing means excluded
## SEC
F1 LO open S1 non-str item in a ref list gives TypeError not ModuleLoadError (modules.py); not in S3/S2/T01 paths; fold into S4 spec (core fix there) or leave
F2 LO addressed-by-spec S2,S3 build tables once per app/server start (tests 5/6)
F3 LO addressed-by-spec S2 keeps router order (awp_progress, awp_weeks before awp; overlapping paths keep order; route_order.txt)
Sec rows for SR-X3: ref prefix rule (Q1 closed), closed-by-default tools (S3 test 3), name clash, failed module does not open others (S2 t5, S3 t4, T01).
## OPEN
Q1 ref rule: plan says refs refused outside the module's own package, but routers, tool registrars and CLI apps of the 10 in-tree modules live in tl_api.routes, tl_mcp, tl_cli (modules depend on tl-core only). S1 uses own package + per-kind surface prefix (routes tl_api.routes., tools tl_mcp., cli tl_cli.). Looser than Q1 text; alternatives: move surfaces into modules (adds fastapi/mcp/typer deps, big) or exact allowlist. needs orch raised r1
Q2 requisitions commands are not in tl_api.COMMANDS (docstring says API builds routes; code does not). S2 equality test excepts it; serving them is additive new routes. needs orch (decide before S2 spec) raised r1
Q3 error rows: ModuleSpec has no errors hook; module error rows stay hand-listed in tl_api/errors.py (X2 hot file). New module whose command raises its own error gets no row. Want an `errors` hook (core interface, APPROVALS) in S4 or later? S2 leaves errors.py alone. needs orch raised r2
## DEC-ORCH
Q1 closed 2026-11-15 orch: own package always; surface prefixes only for an explicit in-tree set (IN_TREE_SURFACES)
Q2 closed 2026-11-15 orch: S2 serves REQUISITIONS_COMMANDS (additive); S4 walks them
Q3 closed 2026-11-15 orch: no errors hook now; new modules raise core error classes (rows exist); T04 guide says so; hook in DEFERRED
## NEXT
1. Orch: dispatch S3 (p2/x4-s3-mcp-tools) and T01 (p2/x4-t01-cli-groups) now; disjoint paths (tl_mcp vs tl_cli); full review each. Answer Q3.
2. Orch: when X2 C2 is merged to trunk, merge trunk into p2/x4, then dispatch S2 (spec staged, branch p2/x4-s2-api-table, wt /home/user/wt/x4/s2).
3. C2 = S2, S3, T01 merged. Round 3: S4 alone (reads ModuleCommand.meta delegation; may carry F1); then T02, T03; T04-T06; DONE round.
4. Worktrees: /home/user/wt/x4/s3, /t01, /s2 (lowercase id).
## REFS
Specs: docs/tickets/P2-X4/{S3-mcp-tools,T01-cli-groups,S2-api-table}.md. Baselines captured by the builders BEFORE editing (OLD_TOOL_NAMES, OLD_GROUPS, OLD_COMMANDS, tests/expected/route_order.txt).
T01 group-name rule: tl_cli.<m>:app -> <m>; tl_cli.<m>:<x>_app -> <x>.
Provided test: docs/tickets/P2-X4/provided/test_module_hooks.py (red until S1; copied to tests/services/test_module_hooks.py).
Seams: tl_api/commands.py:101-110,172-232; app.py:325-349; tl_mcp/server.py:38-53,140-151; tl_cli/main.py:136-204; modules.py ModuleSpec, _discover, load_modules, use_modules.
ADR-0029 dec. 1, 4, 7 and its trace table (§ "X4 S1 CommandSpec", "X4 S4 checks money fields and marks").
## TRAPS
P2-X2 on p2/x2: S1 rewrites agent_scope.py, proposals.py wiring; S2 adds a setting and QueueFullError in tl_api/errors.py. X4 S1 avoids all three; X4 S2 (tl_api) must not touch errors.py beyond its own error rows, and rebases after X2 C2.
Gate: name test files, not dirs (tl-api OOM); NODE_OPTIONS=--max-old-space-size=6144 for just check. One X2 builder alive: 3 slots = X4 S1 + X2 + one ticket workflow.
