# P1-I8 STATE  r=3 base=573a7bb C=C2 ck=0 gate=n/a wt=/home/user/wt/p1-i8
Read first: AGENTS.md, FANOUT.md and README.md (this folder), LEARNINGS ids L-P1-I8-1..12 by `grep -n -A6`. Branch p1/i8; trunk 4bcfae2 merged at 3fb1e1c; trunk is now 8425e86 (tools only: .claude, dev), not merged here yet.
Shards green at 10a8414 (pre-merge): schema+contract+services+webhooks+ci 1225; api 517; cli gov/load/lake/schema+legacy+doc silver 93; tui 1085. Not run: whole tl-cli (~2 h), demo, parity of the tree.
r3 wrote tickets, stubs, provided tests and wiring for T05a4a/b/c, T04a/b, T09a/b. Every provided test of T05a4a/b/c, T04a/b passed (SQLite, or no DB for TUI) against a finished reference kept in refs/ before it was committed; the stubs in the tree fail them. `just check` clean at 573a7bb. No suite or mutation run by the supervisor.
## BOARD
S1 p mrg f 2023370 classify
S2 p mrg f 0404c94 schemareg module
S4 p mrg f 3d007e5 lake silver, readable-set rule
S5 p mrg f 72559cd plumbing: views, routes, client, fakes
S6 p mrg f c65c7ab legacy framework, reserved prefixes
S9 p disp f cdfb5ab fx; 2a 67/69, 2 waived counted apart; full review running
T03 t mrg f 07c7bb7 impact report
T08 t mrg l 3fb9c0a lake marts
T05a1 t mrg f 38049fa package report commands
T07a t mrg l 31e272f dms-register loader
T05a2 t mrg f 538cdff publish, adopt, drift
T07b t mrg l c45de16 tag-list loaders
T05a3 t mrg f 89c1e20 waiver CLI (merge 0232706)
T05a4a t disp l 573a7bb crosswalk; schema_crosswalk.py
T05a4b t disp f 573a7bb export-git; schema_export.py
T04a t disp f 573a7bb workbench screen, text; Ctrl+O
T05a4c t stg f 573a7bb import-git; stub, 10-case test ready
T04b t stg f 573a7bb review screen, text; stub, 17-case test ready
T09a t stg l - demo clauses 1-4 (schema); verify spellings at dispatch
T09b t stg l - demo clauses 5-7 (loader, marts, exit chain); after T09a
T10 - orch - report; orchestrator
## DEC
D1-D12 2026-10-20 see FANOUT.md (packages, roles, pins, gates, waivers, load runs, bronze, class rules, security list, not built).
D13 2026-10-20 T05b became piece S9: it counts records as the viewer, an access path over cur_core_record.
D14 2026-10-20 T05a3 stub carried the finished group and `_waiver_id`; wiring committed with the stub so no later branch edits those lines.
D15 2026-10-20 S9 may touch schema.py (two lines); T05a3 did not.
D16 2026-10-20 S9 blk decided by orch: the two cases are waived and counted apart; fx@cdfb5ab g0 2a 67/69 ck0; S9 branch not touched by the supervisor.
D17 2026-10-20 Q1 (orch): no mutation sentinel for CLI tickets; the provided test is the guard.
D18 2026-10-20 Q2 (orch): crosswalk is brief 6.3: project values of extensible and project_defined lists map to company values or `other`; `tl schema crosswalk --project P [--list L] [--json]`; unmapped ones are flagged.
D19 2026-10-20 T05a4 split in three, each with its own file and one wiring line in schema.py (committed): a crosswalk (schema_crosswalk.py), b export-git (schema_export.py), c import-git (schema_import.py). No builder piece: the import calls the finished draft handler and only reads files (path rules are complete in the stub).
D20 2026-10-20 crosswalk reads the effective schema of the project through `analysis.provider()`. On an extensible list a value with a crosswalk is the project's own, one without is the company's; on a project_defined list all are the project's, unmapped = no crosswalk. An unmapped value of an extensible list cannot exist (the schema does not compose: existing lint). Exit 0 always; a malformed project id is `error:`.
D21 2026-10-20 export-git is admin only (writes host files), writes only the drafted text of Published and Deprecated versions, never a report or impact (F9 by construction), refuses a changed file or a link before writing anything, and writes through a temp file. import-git is any signed-in person's (as `package draft`): checks every file first (regular files only, at most 200, size cap, name = package@version.yaml, other text = problem), drafts nothing when a problem exists, drafts only (never analyse/submit/publish); a version in force in the schema directory is `skipped`.
D22 2026-10-20 Workbench opens with Ctrl+O (free; F1-F12, Ctrl+P/R/E/G taken). T04a (tree, properties, lint, diff) and T04b (classification, impact, sample, submit/approve/send back/publish with the word typed) are independent: `v` in the workbench opens `SchemaReviewScreen(client, scope, actor, ref)`, whose stub is in the tree; each provided test mounts its own screen. Binding, keymap entry and palette command committed with the stubs. No property editor in this increment (a package is drafted from a file).
D23 2026-10-20 T09 split in a (shell script, clauses 1-4) and b (clauses 5-7, appends); both staged: they call every finished command, so they are written against `--help` at dispatch.
## SEC (review at 9928c45, changes requested)
F1 HI fixed@66b4fbf,18ef13c recheck P (orch)
F2 HI fixed@a555198 recheck P (orch); trial still inside the handler transaction (bounded by node cap), follow-up
F3 MD fixed@a555198 core sign-off P
F4 MD fixed@66b4fbf recheck P
F5 MD fixed@66b4fbf recheck P
F6 MD fixed@66b4fbf recheck P
F7 LO accepted
F8 LO fixed@66b4fbf report document
F9 LO closed by design in T05a4b (the export holds the package text only); a test pins the file set
Core sign-offs: all P (readable-set, reserved.py, F3 files). Provider.trial outside the lock (tl_core/schema_provider.py): not listed as P, confirm at the final security pass.
## OPEN
Q3 exit chain (T09b clause 7): no single demo holds PDF -> derived -> published -> feed -> webhook receiver; T09b copies steps of P1-I3.sh and P1-I7.sh and needs an event to hang a rule on. If a link is missing the ticket stops with Blocked; needs orch raised r3
## NEXT
1. Orchestrator merges T05a4a, T05a4b, T04a on pass; read each `.gate/summary.txt`; 2s/gr by re-spec. Merge trunk 8425e86 into p1/i8 when convenient (tools only).
2. r4: dispatch T05a4c and T04b (stubs, tests and tickets are committed; disjoint paths). Check S9 merged for the T09a clause on `tl schema conformance`.
3. r4 or r5, after every CLI and TUI item has merged: finalize T09a (spellings by `tl ... --help`, mart names by `tl lake mart ls`, conformance spelling), dispatch T09a, then T09b; T09b needs Q3 answered.
4. After the last merge: 88; orchestrator runs the whole-suite gate, demo and the final security review of everything after 9928c45 (new: file reads in import-git, file writes in export-git, Ctrl+O screens).
5. Final round writes docs/reports/P1-I8.md (<=80 lines) from this file with Showcase and follow-ups: promote, MCP schema tools, report document, line list class, dashboard limits, roles, F2 trial in transaction, value-list/crosswalk editor and property editor in the workbench, crosswalk as a view for the TUI/API. Also learnings, READMEs and AGENTS of touched packages (schemareg, legacy, tl-cli, tl-tui key table: Ctrl+O), runbooks (workbench, loaders, git export).
6. Candidate learnings (the final round writes them): validate a provided test against a finished reference before staging it (r3 found a reload that overwrote its own error text); `app.pop_screen()` does not run a push_screen callback, `screen.dismiss(None)` does; monkeypatch the module that owns the name (pyright reportPrivateImportUsage); a ruff `noqa` stub header is lines 1-2, so a `sed 1s` clobbers it.
## REFS
docs/tickets/P1-I8/refs/tools/: mut.py.txt, mkticket.py.txt (`python3 mkticket.py.txt OUT.md SPEC`; spec needs `review`), mkstub.py.txt (cuts function bodies of a reference into STEPS stubs), t05a1/t05a2/t05a3/t05a4a/t05a4b/t05a4c/t04a/t04b spec files (COMMON_LEARNINGS in t05a1; paths absolute under /home/user/wt/p1-i8).
refs/<ticket>/: finished reference of each r3 ticket (t05a3 too). provided/: provided tests of every ticket (T05a4a-c, T04a-b included).
Ticket format: 01-tiers §6 checklist; Allowed paths list the test copy, the source and `docs/reports/P1-I8/<id>.md`.
## TRAPS
One heavy pytest at a time, `--basetemp=/tmp/pt-<name>`, remove only that dir; never `/tmp/pytest-of-root`, never pkill. Several large packages in one pytest process: OOM (run per package; tl-api 13 min, tl-modules 24, tl-tui 8).
After editing a pyproject entry point: `uv sync --all-packages`. tl-mcp guard test errors at teardown with uncommitted files: commit first.
P123 pins a company version; use P999 for pin tests. Restricted documents/runs need `cf.use_viewer(...)` level 1; tests default to the lowest viewer.
Postgres conftest signs every command in as one admin: tests with a second account skip on Postgres. T05a4a/b/c tests were run on SQLite only by the supervisor; the tickets run both adapters.
A TUI hint line is one row (a second line is allowed): the provided tests pin 80 columns. DataTable cells are `Text(...)`. Screen attributes must not be `offset` or `_id`.
Never touch /home/user/studious-lamp.
