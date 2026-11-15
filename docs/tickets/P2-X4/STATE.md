# P2-X4 STATE  r=1 base=a933413 C=0 ck=0 gate=n/a wt=/home/user/wt/p2-x4
## BOARD
S1 p disp f - hooks+ModuleCommand; spec S1-module-hooks.md; test provided
S2 p todo f - waits S1; API table from load_modules()
S3 p todo f - waits S1; MCP tools, closed allow list
T01 t todo f - waits S1; CLI group loop
S4 p todo f - waits S2,S3; runs alone
T02 t todo f - scaffold hooks
T03 t todo f - fixture ext_demo
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
none yet. Sec rows for SR-X3: ref prefix rule (Q1), closed-by-default tools (S3), name clash, failed module does not open others.
## OPEN
Q1 ref rule: plan says refs refused outside the module's own package, but routers, tool registrars and CLI apps of the 10 in-tree modules live in tl_api.routes, tl_mcp, tl_cli (modules depend on tl-core only). S1 uses own package + per-kind surface prefix (routes tl_api.routes., tools tl_mcp., cli tl_cli.). Looser than Q1 text; alternatives: move surfaces into modules (adds fastapi/mcp/typer deps, big) or exact allowlist. needs orch raised r1
Q2 requisitions commands are not in tl_api.COMMANDS (docstring says API builds routes; code does not). S2 equality test excepts it; serving them is additive new routes. needs orch (decide before S2 spec) raised r1
## NEXT
1. Orch: APPROVALS line for ModuleSpec hooks and ModuleCommand.meta (12 §5), answer Q1 (hold S1 dispatch if the prefix rule is rejected).
2. Run S1 (workflow, full review); merge to p2/x4 = C1.
3. Round 2: S2, S3 specs (disjoint: tl_api vs tl_mcp), T01 ticket; ADR-0029 trace row needs `delegation` key read in S4 only.
4. Round 3: S4 alone, T02, T03; then T04-T06; DONE round: report, SR-X3 range <wave-3 base>..<head>.
## REFS
Provided test: docs/tickets/P2-X4/provided/test_module_hooks.py (red until S1; copied to tests/services/test_module_hooks.py).
Seams: tl_api/commands.py:101-110,172-232; app.py:325-349; tl_mcp/server.py:38-53,140-151; tl_cli/main.py:136-204; modules.py ModuleSpec, _discover, load_modules, use_modules.
ADR-0029 dec. 1, 4, 7 and its trace table (§ "X4 S1 CommandSpec", "X4 S4 checks money fields and marks").
## TRAPS
P2-X2 on p2/x2: S1 rewrites agent_scope.py, proposals.py wiring; S2 adds a setting and QueueFullError in tl_api/errors.py. X4 S1 avoids all three; X4 S2 (tl_api) must not touch errors.py beyond its own error rows, and rebases after X2 C2.
Gate: name test files, not dirs (tl-api OOM); NODE_OPTIONS=--max-old-space-size=6144 for just check. One X2 builder alive: 3 slots = X4 S1 + X2 + one ticket workflow.
