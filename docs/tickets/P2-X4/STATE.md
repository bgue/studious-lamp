# P2-X4 STATE  r=4 base=e1bd8d83 C=2 ck=0 gate=n/a wt=/home/user/wt/p2-x4
## BOARD
S1 p mrg f 9f0bc5ce hooks merged (C1)
S3 p mrg f 1afa1cfb MCP tools from hooks
T01 t mrg f 1ec89b00 CLI groups from hooks
S2 p mrg f ee6fa66e API table and routers (C2)
S4 p mrg f 4e39ff78 review P; APPROVALS
T02a t mrg f 479f41bb review P; amend 1
T02b t stg f - ready r4: templates pasted, provided test surfaces; waits dispatch
S5 p mrg f 30e31f3d review P
T04 t stg l - runbook new-module; waits T02b
T05 t stg f - demo driver; waits T02b,S5
T06 t stg l - AGENTS rows; waits T05
## DEC
D1 2026-11-15 core row type `ModuleCommand` in tl_core/modules.py: CommandSpec lives in tl_api, core cannot import it; S2 maps rows to CommandSpec (+meta); spec S1
D2 2026-11-15 hook names: `commands`, `read_routers`, `tools`, `cli_groups` (plural: awp has 3 routers, corr has 4 CLI groups); plan said singular
D3 2026-11-15 hook failure per module (fixed message, `hook_failures()`), others still load (demo 6); name clash and malformed refs stay fail-fast
D4 2026-11-15 11 installed modules, not 8 (legacy has no commands); S1 declares for all that have the surface
D5 2026-11-15 `meta` empty now; ADR-0029 dec. 7 key `delegation` read by S4; missing means excluded
D6 2026-11-16 delegation marks: meta is empty on all 205 rows and S4 may not edit modules, so marks live in tests/tools/delegation_marks.toml (row meta wins); runtime still treats missing as excluded; spec S4
D7 2026-11-16 scaffold carries no example command (an access-worded handler is core work); ext_demo (T03) is the worked command; scaffold shows route, tool, CLI group; spec T02a, T02b
D8 2026-11-16 T02 split: scaffold had no ModuleSpec or entry point at all, so T02a (spec, commands hook, entry point) then T02b (three surfaces, own-package refs; CLI ref `<pkg>.cli:<name>_app` so _group_name gives `<name>`)
D9 2026-11-16 legacy ratchet: pre-ADR-0027-d4 commands neither proposable nor excluded are listed once in tests/tools/proposable_undecided.txt; may shrink, never grow; new-module commands must be decided; spec S4
D10 2026-11-16 drift test scans the four registries by ast; pre-hook lines of integration branches go in tests/tools/prehook_lines.toml (starts empty); spec S4
D11 2026-11-16 T03 became piece S5: ext_demo has an access-worded command and a confidential read of record text (core list, ticket-tier checklist 5 and 7 fail); spec S5-ext-demo.md; lives in tests/ext_demo, own tests in services, tl-api, tl-mcp test dirs (harnesses are per package)
D12 2026-11-16 T02b text pasted and checked (ruff format+check, pyright, 2 names incl. 20 chars); generated test count 3 to 5 (module), 5 to 7 (record-type, projector pins); deps are bare names as in tl-api, tl-mcp, tl-cli
## SEC
F1 LO open S1 non-str ref item gives TypeError not ModuleLoadError; folded into S4 (modules.py __post_init__, test 8)
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
1. Orch: dispatch T02b (p2/x4-t02b-scaffold-surfaces, wt /home/user/wt/x4/t02b, review full) and S5 (p2/x4-s5-ext-demo, wt /home/user/wt/x4/s5, builder, full review); disjoint (tl-cli templates vs tests/ext_demo and three test dirs). Gates one at a time each; never two heavy at once.
2. r5: T04 (lite), T05 (full) as ticket files, text pasted from merged T02b and S5 reports; T06 after T05. C3 = S4, T02a, T02b, S5 merged.
3. After X4 reaches trunk (follow-ups in other increments, not X4 files): P2-I4B ticket moves tl_mod_scaffold SCAFFOLD_COMMANDS (commands.py pre-hook line), routes/scaffold.py and its app.py line into
   tl_mod_scaffold module.py hooks (`commands`, `read_routers`); `scaffold` must join IN_TREE_SURFACES (core edit, gated) or its router moves into its own package; add its lines to prehook_lines.toml until then.
4. P2-IP (QR, INSP, PTW S2 specs): new modules are not in IN_TREE_SURFACES, so every hook ref must sit in the module's own package (`tl_mod_<m>.routes:router`, `.tools:register_tools`, `.cli:<m>_app`),
   commands rows are ModuleCommand-like (model, handler, access, optional meta with `delegation`), their commands need a mark in row meta, and each needs a proposable row or an exclusion entry.
5. Worktrees: /home/user/wt/x4/{t02b,s5} (lowercase id; created by the orchestrator at dispatch).
6. Open for S4 follow-up (report): should the marks file move to row meta when a dispatcher reads marks (D6)? StartExtraction stays eligible? needs orch, not blocking.
## REFS
Specs: docs/tickets/P2-X4/{T02b-scaffold-surfaces,S5-ext-demo,T04-T06-staged}.md (merged: S1,S2,S3,S4,T01,T02a; reports in docs/reports/P2-X4/).
Provided (r4): provided/test_new_module_surfaces.py (T02b; copy to packages/tl-cli/tests/; checked ruff format, ruff check, pyright there).
Provided (merged): provided/test_new_module_spec.py (T02a). Baselines: OLD_TOOL_NAMES, OLD_GROUPS, tests/expected/route_order.txt.
T01 group-name rule: tl_cli.<m>:app -> <m>; tl_cli.<m>:<x>_app -> <x>.
Provided test: docs/tickets/P2-X4/provided/test_module_hooks.py (red until S1; copied to tests/services/test_module_hooks.py).
Seams: tl_api/commands.py:101-110,172-232; app.py:325-349; tl_mcp/server.py:38-53,140-151; tl_cli/main.py:136-204; modules.py ModuleSpec, _discover, load_modules, use_modules.
ADR-0029 dec. 1, 4, 7 and its trace table (§ "X4 S1 CommandSpec", "X4 S4 checks money fields and marks").
## TRAPS
P2-X2 on p2/x2: S1 rewrites agent_scope.py, proposals.py wiring; S2 adds a setting and QueueFullError in tl_api/errors.py. X4 S1 avoids all three; X4 S2 (tl_api) must not touch errors.py beyond its own error rows, and rebases after X2 C2.
Gate: name test files, not dirs (tl-api OOM); NODE_OPTIONS=--max-old-space-size=6144 for just check. One X2 builder alive: 3 slots = X4 S1 + X2 + one ticket workflow.
Trunk merged (X2 in). Gate per named file or small group; S4 gates run one at a time, tl-api and tl-mcp groups separately (test_commands.py alone is 7-9 GB). Statement-count tests ignore BEGIN/COMMIT/ROLLBACK.
Provided tests and templates are linted where they land: ruff format/check and pyright at the target path before the commit; the tool and CLI templates were also run for a 20-character name.
Box OOMs on combined heavy runs: S5 and T02b gates sequential, small groups; tl-api test_commands.py alone is 7-9 GB, keep it out of every X4 gate. Runner kills runs over ~10 min: builders run long gates in background.
Template import order: ruff sorts `import <pkg>` before `from tl_core...` in generated tests (one section); a hand-written order fails ruff_clean, so paste, do not retype.
