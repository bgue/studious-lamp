# P1-I8 STATE  r=2 base=339104a C=C2 ck=1 gate=pass wt=/home/user/wt/p1-i8
Read first: AGENTS.md, FANOUT.md and README.md (this folder), LEARNINGS ids L-P1-I8-1..12 by `grep -n -A6`. Branch p1/i8, trunk 4bcfae2 merged at 3fb1e1c (docs, dev/gate.sh, .claude only).
Shards green at 10a8414 (pre-merge): schema+contract+services+webhooks+ci 1225; api 517; cli gov/load/lake/schema+legacy+doc silver 93; tui 1085. Not run: whole tl-cli (~2 h), demo, parity of the tree.
## BOARD
S1 p mrg f 2023370 classify
S2 p mrg f 0404c94 schemareg module
S4 p mrg f 3d007e5 lake silver, readable-set rule
S5 p mrg f 72559cd plumbing: views, routes, client, fakes
S6 p mrg f c65c7ab legacy framework, reserved prefixes
T03 t mrg f 07c7bb7 impact report
T08 t mrg l 3fb9c0a lake marts
T05a1 t mrg f 38049fa package report commands
T07a t mrg l 31e272f dms-register loader
T05a2 t mrg f 538cdff publish, adopt, drift (merge 0609333)
T07b t mrg l c45de16 tag-list loaders (merge 62a7142)
T05a3 t disp f 339104a waiver CLI; stub, wiring, 10-case test staged
S9 p disp f 339104a conformance dashboard (was T05b); spec only, no stub
T05a4 t stg f - crosswalk, export-git, import-git; nothing written yet
T04a t stg f - workbench TUI part 1; nothing written yet
T04b t stg f - workbench TUI part 2; after T04a
T09 t stg l - demo script; after all
T10 - orch - report; orchestrator
## DEC
D1-D12 2026-10-20 see FANOUT.md (packages, roles, pins, gates, waivers, load runs, bronze, class rules, security list, not built).
D13 2026-10-20 T05b became piece S9: it counts records as the viewer, an access path over cur_core_record. README renumbered (README S8 stays docs/demo wiring).
D14 2026-10-20 T05a3 stub carries the finished group and `_waiver_id`; wiring of `schema_waiver` into schema.py committed with the stub so no later branch edits those lines.
D15 2026-10-20 S9 may touch schema.py (two lines); T05a3 does not, so no overlap on merge.
## SEC (review at 9928c45, changes requested)
F1 HI fixed@66b4fbf,18ef13c orch re-check running
F2 HI fixed@a555198 orch re-check running; trial still inside the handler transaction (bounded by node cap), follow-up
F3 MD fixed@a555198 core sign-off pending: tl_api/effective.py, tl_core/util.py
F4 MD fixed@66b4fbf bronze class
F5 MD fixed@66b4fbf waiver expiry at submit
F6 MD fixed@66b4fbf impact names redacted for non-admins
F7 LO accepted
F8 LO fixed@66b4fbf report document
F9 LO open note: names in any future export (T05a4 export-git must not carry impact names or record text)
Core sign-offs waiting: tl_lake/sync.py readable-set (3d007e5), tl_core/services/reserved.py (c65c7ab), F3 files, Provider.trial outside the lock (tl_core/schema_provider.py).
## OPEN
Q1 mutation sentinel of T05a3 (provided test killing a mutant of the reference) not run by the supervisor; builder or reviewer decides needs orch raised r2
Q2 T05a4 crosswalk: what is crossed with what (company package against a standard? two versions?) not in README; decide the text before the ticket needs builder raised r2
## NEXT
1. Orchestrator merges T05a3 and S9 on pass; read each `.gate/summary.txt`, fix 2s/gr by re-spec.
2. T05a4: file-writing and file-reading commands (export-git writes package YAML to a directory, import-git drafts packages from one). Path safety, size caps, no impact names (F9). Likely a piece (S10) for the import half; export and crosswalk are tickets. Write stub, test and ticket; wire into schema.py in the same commit.
3. T04a, T04b: one `SchemaWorkbenchScreen` in tl_tui/widgets/schema_screen.py, pure text in schema_text.py, pilot assertions not snapshots. Keys taken: F5 F12 Ctrl+R Ctrl+E Ctrl+G. Client methods and fakes exist (S5). Stage screen stub plus provided pilot test; T04a tree/properties/lint/diff, T04b impact/sample/review/publish.
4. T09: dev/demos/P1-I8.sh, `just demo P1-I8` on both adapters; commands copied into the report. Needs every CLI item merged.
5. Dispatch pairs with disjoint Allowed paths. Suggest r3: T05a4 (+S10 if split) and T04a; r4: T04b, then T09.
6. After the last merge: 88; orchestrator runs whole-suite gate, demo, final security review of everything after 9928c45; final round writes docs/reports/P1-I8.md (≤80 lines) with Showcase and follow-ups (promote, MCP schema tools, report document, line list class, dashboard limits, roles, F2 trial in transaction, F9), learnings, READMEs and AGENTS of touched packages (schemareg, legacy, tl-cli), runbooks.
## REFS
docs/tickets/P1-I8/refs/tools/: mut.py.txt (`python mut.py FILE SPEC.json 'test cmd'`), mkticket.py.txt (`python3 mkticket.py.txt OUT.md SPEC`; spec needs `review`), t05a1/t05a2/t05a3_spec.py.txt (COMMON_LEARNINGS lives in t05a1; paths absolute under /home/user/wt/p1-i8).
refs/t05a3/: finished reference of the waiver CLI (schema_waiver.ref.py.txt), already green. provided/: provided tests of every ticket, t05a3 included.
Ticket format: 01-tiers §6 checklist; Allowed paths list the test copy, the source and `docs/reports/P1-I8/<id>.md`.
## TRAPS
One heavy pytest at a time, `--basetemp=/tmp/pt-<name>`, remove only that dir; never `/tmp/pytest-of-root`, never pkill. Several large packages in one pytest process: OOM (run per package; tl-api 13 min, tl-modules 24, tl-tui 8).
After editing a pyproject entry point: `uv sync --all-packages`. tl-mcp guard test errors at teardown with uncommitted files: commit first.
P123 pins a company version; use P999 for pin tests. Restricted documents/runs need `cf.use_viewer(...)` level 1; tests default to the lowest viewer.
Postgres conftest signs every command in as one admin: tests with a second account skip on Postgres.
Never touch /home/user/studious-lamp.
