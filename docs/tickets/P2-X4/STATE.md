# P2-X4 STATE  r=5 base=e1bd8d83 C=3 ck=0 gate=n/a wt=/home/user/wt/p2-x4
## BOARD
S1 p mrg f 9f0bc5ce hooks merged (C1)
S3 p mrg f 1afa1cfb MCP tools from hooks
T01 t mrg f 1ec89b00 CLI groups from hooks
S2 p mrg f ee6fa66e API table and routers (C2)
S4 p mrg f 4e39ff78 review P; APPROVALS
T02a t mrg f 479f41bb review P; amend 1
T02b t mrg f 338e5265 review P
S5 p mrg f 30e31f3d review P
S6 p mrg f b28bec8f SR-X4 fixes; APPROVALS
T04 t disp l - runbook new-module; spec T04-new-module-runbook.md
T05a t disp f - driver A clauses 1,2,6 (scaffold, failing hook)
T05b t mrg f 6208be85 review P
T05c t stg f - demo shell P2-X4.sh; waits T05a,T05b mrg
T06 t disp l - AGENTS rows, README line, DEFERRED rows; merge after T04,T05c
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
D13 2026-11-16 demo clauses 1 and 2 show the scaffold's route, tool and CLI group (no example command, D7); `/commands/ExtDemoAddNote` is shown under clause 2 and 3 on ext_demo; README demo text left as written
D14 2026-11-16 demo clause 4 uses the read tool `ext_demo_get_note` (closed until `mcp.ext_demo_get_note` is allowed, then reads): ExtDemoAddNote is `excluded:reserved`, so no proposal is filed; spec T05b
D15 2026-11-16 T05 split by file (checklist 4: >400 lines): T05a driver file A, T05b driver file B, T05c shell; shape tests provided (tests/services/test_demo_p2_x4_{drivers,script}.py, linted there)
D16 2026-11-16 T04, T05a, T05b, T06 have disjoint Allowed paths and run in parallel; T05c after T05a and T05b; T06 cites T04 and T05c files by fixed name, merge it last
## SEC
F1 LO open S1 non-str ref item gives TypeError not ModuleLoadError; folded into S4 (modules.py __post_init__, test 8)
F2 LO addressed-by-spec S2,S3 build tables once per app/server start (tests 5/6)
F3 LO addressed-by-spec S2 keeps router order (awp_progress, awp_weeks before awp; overlapping paths keep order; route_order.txt)
Sec rows for SR-X3: ref prefix rule (Q1 closed), closed-by-default tools (S3 test 3), name clash, failed module does not open others (S2 t5, S3 t4, T01).
## OPEN
Q1 ref rule: plan says refs refused outside the module's own package, but routers, tool registrars and CLI apps of the 10 in-tree modules live in tl_api.routes, tl_mcp, tl_cli (modules depend on tl-core only). S1 uses own package + per-kind surface prefix (routes tl_api.routes., tools tl_mcp., cli tl_cli.). Looser than Q1 text; alternatives: move surfaces into modules (adds fastapi/mcp/typer deps, big) or exact allowlist. needs orch raised r1
Q2 requisitions commands are not in tl_api.COMMANDS (docstring says API builds routes; code does not). S2 equality test excepts it; serving them is additive new routes. needs orch (decide before S2 spec) raised r1
Q3 error rows: ModuleSpec has no errors hook; module error rows stay hand-listed in tl_api/errors.py (X2 hot file). New module whose command raises its own error gets no row. Want an `errors` hook (core interface, APPROVALS) in S4 or later? S2 leaves errors.py alone. needs orch raised r2
Q4 opening a module tool to agents needs `mcp.<tool>` added to `MCP_ACTIONS` (tl_mcp/identity.py): a platform edit, so "no tl-mcp edit" holds for closed tools only; runbook says so, DEFERRED row C (T06); hook for tool actions = later core change. needs orch (accept wording or order a hook), not blocking raised r5
## DEC-ORCH
Q1 closed 2026-11-15 orch: own package always; surface prefixes only for an explicit in-tree set (IN_TREE_SURFACES)
Q2 closed 2026-11-15 orch: S2 serves REQUISITIONS_COMMANDS (additive); S4 walks them
Q3 closed 2026-11-15 orch: no errors hook now; new modules raise core error classes (rows exist); T04 guide says so; hook in DEFERRED
## NEXT
1. Orch: dispatch T05a, T05b (heavy: driver runs, SQLite) as one workflow; T04, T06 (docs, `just check` only) as a second. Worktrees /home/user/wt/x4/{t04,t05a,t05b,t06}. Merge T04 and T06 order free; T06 last.
2. After T05a and T05b merge: r6 supervisor stages T05c ready (spec T05c-demo-script.md: check modes as merged) and dispatches it; C4 = T05c merged, demo green on both adapters.
3. DONE round (88) notes for the r6/r7 supervisor, written from this STATE:
   - Report: docs/reports/P2-X4.md (≤ 80 lines, throughline-docs), STATUS.md line, APPROVALS already holds S1, S4 lines.
   - AGENTS row: T06 (two rows). Package README line: T06. Deferred rows: T06 (A I4B scaffold lines, B P2-IP refs, C tool actions).
   - Learnings to record (≤ 6 lines each, by id): (a) COMMANDS and its router are made at import; tests reload `tl_api.commands` inside `use_modules` and restore COMMAND_BODIES, `intent._REGISTERED`; `create_schema` inside `use_modules` (S5); (b) fake module for hook tests: in-tree name or own `tl_mod_<name>` refs, else ModuleLoadError; fake tools need `guarded` (S3); (c) ticket without Context section makes the author guess the reading list (T02b); (d) `just check` can exit 247 at pyright under memory pressure: rerun `uv run pyright` alone (T02b); (e) template text is pasted and linted for a short and a 20-character name, never retyped (T02a, T02b).
   - Whole gate per directory (tl-api OOM: name files, never test_commands.py alone with others): `just check`; `just gate` whole suite (orch, 4 parts); `just gate-pg` on packages/tl-core/tests, packages/tl-api/tests, packages/tl-mcp/tests, tests/services (touched dirs; tl-cli tests are sqlite only). Then `just demo P2-X4` on both adapters (`just dev up` first).
   - SR-X4 (one fresh security review, ≤ 450 k tokens, `F<n> <HI|MD|LO> file:line`): scope = commit range `11621381..<p2/x4 head>` (11621381 is trunk as last merged at cf752722; 38 commits, 84 files, X4 only: tl-core modules.py, tl-api commands/app/routes tables, tl-mcp server.py, tl-cli main.py and scaffold, tl-modules module.py hooks, tests/ext_demo, tests/tools, tests/services). Sec rows: ref prefix rule (Q1, IN_TREE_SURFACES), closed-by-default tools (S3 test 3), name clash fail-fast, a failed module opens no other (S2 t5, S3 t4, T01), hidden equals missing on ext_demo (route, tool, CLI), F1-F3 above.
4. After X4 reaches trunk (other increments, not X4 files): P2-I4B scaffold lines to hooks; P2-IP refs in own packages (both now DEFERRED rows via T06).
5. Open for S4 follow-up (report): marks file to row meta when a dispatcher reads marks (D6); StartExtraction eligible? needs orch, not blocking.
## REFS
Specs (r5): docs/tickets/P2-X4/{T04-new-module-runbook,T05a-demo-driver-scaffold,T05b-demo-driver-ext-demo,T05c-demo-script,T06-agents-rows}.md. Merged: S1-S5, T01, T02a, T02b (reports docs/reports/P2-X4/).
Provided (r5): provided/test_demo_p2_x4_drivers.py (T05a, T05b) and test_demo_p2_x4_script.py (T05c), to tests/services/; ruff format, ruff check, pyright clean at that path (red until the drivers and script exist).
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
