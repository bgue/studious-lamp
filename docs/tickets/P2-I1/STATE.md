# P2-I1 STATE  r=10 base=1b93a13 C=2 ck=0 gate=n/a wt=/home/user/wt/p2-i1
## BOARD
S2 p mrg f 99ad743 schema awp merged; APPROVALS logged
S3 p mrg f f482aad awp package merged; rev pass
S4 p mrg f 1fa0f90 CWP, packages, RULES, tl_api glue; rev pass
S5 p mrg f d32e1be rollup run, projector, worker; rev pass
T02 p mrg f 518f6a1 targets awp_wbs, awp_cwa; rev pass
T01 t mrg l 3e3d88c loaders, samples; 2s subject only, accepted (D19)
T10 t mrg f 8b811a4 read views; rev pass
S6 p mrg f 5fa0905 expected link awp.yaml; APPROVALS line c325f8b
T10b t mrg f f73b5e6 F1 closed (total over visible lines)
T03a t mrg f dfc6217 eight GET routes, counts, timeline
T04a t mrg f 0ba277f tl awp reads; tl-mod-awp dep added by orch
T04b t mrg f 00565d1 reports + tl awp report; mounted r6 (glue)
T03b t mrg f 86e2662 client methods; C2; short subject kept (D35)
T06 t mrg f 2420368 MCP tools + propose_cwp; pins; APPROVALS aeac490
T05g t stg f - PathVersion.reason_code; ticket ready r10
T05h t todo f - nav + palette entries for the five awp screens; spec after T05c
T10c t mrg f dca4731 view fields; 2 att; second _hidden pass dropped
T03c t mrg f 24b64bc API reports route + CSV
T04c t mrg f 1645726 cwp+package verbs; subject T04c: kept (D37)
T04d t mrg f a6e9002 wbs, cwa, path verbs; rev pass; mounted r9 (glue)
T05a t mrg f 1c6aed5 awp_text + details/awp
T05b t mrg f a90661e WBS tree + wbs_text; rev pass; Qs D47
T05c t stg f 4995e85 blk r9; re-spec r10 (D49-D50); after T05g
T05d t mrg f 979cba2 CWP register screen; rev pass
T05e t mrg f ff9d980 CWA register; 2 att; subject kept (D51)
T05f t mrg f e6b59f5 packages log; 2 att; subject kept (D51)
T07 t mrg l 8d9b344 sim AwpDesk, planner; 2s subject only (D51)
T04e t mrg f dbf684c rollup + worker; mounted r10 (glue dc72b6a)
T11 p stg f - tests, 5 mutants, walk; spec ready + r10 notes; after T05g T05c
T08 t todo f - demo; after T11 and T05h
T09 t todo l - docs; after T05c merged
## DEC
D1 2026-11-01 round 1 file names: S2 S3 S4 S5 T01..T11 as spec §10 ids; table in README.md
D2 2026-11-01 no model names in committed files; trailer = harness trailer, not discussed
D3 2026-11-01 first batch S2 alone (all else depends on S2)
D4 2026-11-01 owner policy: tests at T11 (C3), tour once at C4, no security review; Sec rows recorded not run
D5 2026-11-01 access words and awp.* keys already on trunk (access-words.yaml lines 10-19)
D6 2026-11-01 Q1 feed: 8 awp no-card events in POLICY_EVENT_TYPES (cards.py), done in S3
D7 2026-11-01 r2 batch S3 alone (deps)
D8 2026-11-01 T02 is a piece, not Haiku: data-conversion job (01-tiers §3 table), compensation rule undecided (§6.2, §6.5); id kept
D9 2026-11-01 orch D-a: keys namespaced per type (`awp.wbs@code`, `awp.cwa@code`, S4 adds ewp/pwp); resolve_code takes bare code; closes S3 F1; in S4
D10 2026-11-01 orch D-b..D-e: 0-line map clears (S4); settle re-check of ledger head (S5); tl_api glue AwpError rows + AWP_COMMANDS (S4); reason_code vs PathReason list (S4)
D11 2026-11-01 seams: projectors/cwp.py (S4) and projectors/rollup.py (S5) so module.py is mine only (st commit 4722827)
D12 2026-11-01 `tl awp worker` CLI is T04's; S5 leaves tl_mod_awp.worker.build_worker/requeue_orphans (spec §4 entry reworded)
D13 2026-11-01 every ticket acceptance runs just check with NODE_OPTIONS=--max-old-space-size=6144 (pyright heap)
D14 2026-11-01 weekly capacity near stop line: r3 batch is S4 S5 T02 only; T10/T01 wait for r4
D15 2026-11-01 r4 T10 views omit link count, file count, timeline (need a unit of work): T03a adds them from links_of and record_history
D16 2026-11-01 r4 S4 open 2-4 accepted: AllocateCwpToWbs has no clear (spec); CommandResult.key = typed code; offline_drafts {} for awp.CWP until P3-I5
D17 2026-11-01 r4 T02 F1 accepted (subject); F2 second-reverse no-op check goes to T11 test_targets.py; path-defining run stays irreversible
D18 2026-11-01 r4 C2 NOT reached: S4 S5 T02 merged but T10 T03a T03b open. Batch r4 = T10 + T01 (T03a/T04 need T10)
D19 2026-11-01 r5 T01 2s accepted (only the commit subject; fixed cacec9f); CWA sample plans new 5 = 4 areas + path (T01 open Q)
D20 2026-11-01 r5 T10 open Q1-3 accepted: hidden refs omitted not named; package_list(kind=) EWP|PWP (routes validate, 422); by_cost_code keyed by cost code's code
D21 2026-11-01 r5 Q1 answered yes: S6 piece = schema/fixtures/links/awp.yaml (copy of cwp.yaml expectation); gate orch P2-Q10, APPROVALS line at merge; T11 tests `tl links expected`
D22 2026-11-01 r5 F1 fix = ticket T10b (views.py _rollup only): hidden cost code -> total = visible lines + unallocated; script patches views._hidden (no awp or cost record has a class)
D23 2026-11-01 r5 T04 split by file: T04a reads+group (awp.py, awp_read.py, main.py), T04b reports (module reports.py takes cost hours as arg; module does not depend on cost), T04c (r6) write verbs+rollup+worker; each `register(app)`; report mount lines = supervisor glue
D24 2026-11-01 r5 T03a has no reports route; T03c (r6, after T04b) adds `/awp/reports/{name}` and CSV
D25 2026-11-01 r5 acceptance scripts get rollup rows by queueing and running the worker on a COPY of the seed (requeue_orphans + build_worker.runner.run_until_idle); seed itself stays rollup-empty
D26 2026-11-02 r6 views lack what logs show (CWP Allocated, package Subject/CWPs, WBS CWPs): T10c adds defaulted fields; WBS Cost codes table has no Name (no view has it), % = hours/total
D27 2026-11-02 r6 WEB1 twins: each screen's text is a Textual-free tl_tui/<x>_text.py (awp_text wbs_text cwa_text path_text package_text) returning cells and layout.Page; contracts fixed in T05a-c; web imports via tl_web/present.py; check = import with sys.modules["textual"]=None
D28 2026-11-02 r6 T04a/T04b choices accepted: unknown wbs code exits 1; no path prints the line, exit 0; list headers print 0; difference = awp minus cost; union of codes; empty csv ""
D29 2026-11-02 r6 CWA register data = list_cwas + get_path + list_cwps summed in cwa_text (no new view); T04 split: T04c cwp/package/rollup/worker, T04d wbs/cwa/path
D30 2026-11-02 r6 T03a timeline note literal reading and null wbs total without rollup rows accepted; T11 covers
D31 2026-11-02 r6 S6.py uses `tl link list` (no `tl links expected`); T11 test uses it, no new command
D32 2026-11-02 r7 T05a split for the §6 size check: T05a = awp_text + details/awp (+ cwp_rows, additive to the D27 contract); T05d = the screen. Allocation table has no Title column (view has none); Schedule cells from ActivityLink.resolution. T05b/T05c/T05e/T05f need T05a only (pattern widgets/tag_register.py)
D33 2026-11-02 r7 T03c: GET /awp/reports/{name}?format=json|csv; JSON ReportView(name, columns, rows of format_value text); unknown name 404; cost hours copied from tl_cli/awp_report._cost_figures
D34 2026-11-02 r7 T04c verbs by CWP/package number (id via views, version via get_record_by_id for ReleaseCwp); rollup + worker moved to T04d for diff size
D35 2026-11-02 r7 C2 reached (S4 S5 T10 T10b T10c T03a T03b merged). T10c f0f0d9d and T03b 4d2594c keep their short subjects (no history rewrite)
D36 2026-11-02 r7 Haiku size check: T05b (WBS+CWA) and T05c (path+packages) are over 400 lines / 5 files; r8 splits each by area (T05b WBS, T05e CWA, T05c path, T05f packages), contracts unchanged
D37 2026-11-02 r8 T04c blk accepted: subject `T04c:` on 1645726 stays; allocate needs leaf nodes (ticket error, script uses 1.1.1 and 1.2.1); `move --reason` on an action without a reason is refused (confirmed); T04c glue mounted in tl_cli/awp.py
D38 2026-11-02 r8 T05a open Qs answered: empty Timeline heading + "No events recorded" kept; budget/discipline in summary and Scope kept; contractor stays in Scope; discipline label from the code list when loaded, else the code
D39 2026-11-02 r8 T06 path_of_construction null for no path/unknown version kept (the view's None); T11 pins it
D40 2026-11-02 r8 T04d = wbs, cwa, path verbs (9, awp_write2.py); rollup + worker split to T04e (awp_run.py) for the size check; both import awp_write helpers
D41 2026-11-02 r8 T05 split done by area: T05b WBS, T05e CWA, T05c path, T05f packages; D27 contracts unchanged; tickets forbid edits to layout.py/awp_text.py/nav (parallel conflicts; DROP_FIRST names are glue)
D42 2026-11-02 r8 T07 stays draft: desk is reads only (areas, cwps), CWPs come from rec.propose("propose_cwp") + the approver; open: sim project has no awp data, FakeClient propose_cwp, ROLE_NAMES pins
D43 2026-11-02 r9 T07 fact 1: sim project gets awp data by hand (`tl awp cwa define`, `path define --project sim-<run>` as operator, like schedule-weeks.yaml); no setup hook, no core sim change; T08 does it
D44 2026-11-02 r9 T07 fact 2: FakeWorld/FakeClient learn propose_cwp (area_codes, cwp_rows; accept creates a row) so the real actor pair runs in unit tests
D45 2026-11-02 r9 T07 fact 3: planner is an AGENT (only agent:sim-assistant has MCP, HttpConnector._mcp_for), identity = ASSISTANT; ROLE_NAMES unchanged so test_scenario/test_orchestrator pins stay; ACTOR_NAMES = ..., assistant, workface_planner, approver; AwpDesk has areas() only (cwps() dropped, YAGNI)
D46 2026-11-02 r9 batch = T04e T05c T05e (disjoint paths); T05f + T07 next (5-file check for T07 = 5 source files, script and report not counted); T11 spec written (T11-tests.md), gate = just gate on the touched dirs + gate-pg awp
D47 2026-11-02 r9 T05b Qs accepted as built (cost-code cell N . P% of total_hours; Parent of N = direct children; Leaf . Retired; no DROP_FIRST, Subject shortens); T05d: Budget h left-aligned, summary composed in screen; T04d: mutually exclusive option pairs and `path define` no-step refusals accepted, empty `revise` pinned at T11; all in T11-tests.md
D48 2026-11-02 r9 glue done: tl_cli/awp.py mounts awp_write2.register(app) (2 lines); awp_run (T04e) next
D49 2026-11-03 r10 T05c blocked on views: PathVersion gets reason_code (T05g, first non-null step reason of v>1, None for v1); path_page takes previous: PathView (one get_path per version change), labels; no per-row call
D50 2026-11-03 r10 T05c answers: compare keys on cwa code, None skipped; sections CWPs (selected step), Steps changed, Versions; Budget h "—" without a budget; PathReason from labels.code_labels via load_labels(("awp.CWP",)); `v` toggles steps/compare rows
D51 2026-11-03 r10 board: T04e T05e T05f T07 merged; old subjects T04e: T05e: T05f: T07: stay (no rewrite); T05e Active/Retired, Enter no-op, CWA_DROP in cwa_text, T05f column order Type/Status, T07 McpUnavailableError and None-cwa skip accepted; T07 report error (HttpSimClient has _project property, client.py:444) noted in T11
D52 2026-11-03 r10 the five awp screens have NO entry key or palette command (no app action, commands.py, keymap.py): the tour cannot reach them; T05h (after T05c) adds palette commands + app actions + keymap rows, owner wants a screenshot of every screen
## SEC
F1 LO fixed@- S2 report 65>60 lines; waived
F2 LO fixed@adfbd1d S3 dropped redundant scope indexes
S3F1 MD fixed@e79b789 S4 D-a namespaced keys; T11 guard (node 1 and cost code 1 coexist, hidden record keeps answer)
S3F2 LO open path lookup hidden -> T11 five-reader walk
S3F3 LO open tree counts hidden -> T11 five-reader walk
S3F4 LO fixed@1fa0f90 S4 F4
T10F1 MD fixed@f73b5e6 T10b; T11 guard: total_hours exposed hidden cost code hours
T10F2 MD open activity refs unfiltered (views.py:351, schedule resolver _LINKS_SQL): T11 five-reader walk with fixture; fix is a tl_mod_schedule change, orch decides
T10F3 LO open hidden-CWP check impossible (no class on awp records): T11 fixture
(review only if the owner asks. Sec rows: S3 S4 S5 T02 T03a T06)
## OPEN
(none)
## NEXT
1. r10 DISPATCH (orchestrator): T05g docs/tickets/P2-I1/T05g-path-version-reason.md p2/i1-t05g-reason t f, alone (worktree /home/user/wt/i1/t05g). Setup `uv sync --all-packages`; `NODE_OPTIONS=--max-old-space-size=6144 just check`; ticket script; no pytest. Then merge into p2/i1.
2. After T05g merged: in /home/user/wt/i1/t05c run `git merge p2/i1` (clean, only the old blocked report is on the branch), then DISPATCH T05c (ticket re-specced, branch p2/i1-t05c-path, t f). T05c is the last screen.
3. r11 (fresh supervisor, after T05c merges): write T05h (nav: palette AppCommands in commands.py, app actions in app.py, keymap.py rows, nav pins; Haiku-size check first; 5 screens: CWPs, WBS, CWAs, Path, Packages; project scope only, "needs a project" notice like action_tags) and DISPATCH T05h + T11 together (disjoint: tl-tui src vs tl-tui/tests + other test dirs). T11 gate = just gate on the touched dirs + gate-pg awp; findings to D-records, src defects become Haiku fix tickets.
4. C3 reached when T05c T05h T11 merged. C4: T08 demo (dev/demos/P2-I1.sh, p2_i1_demo.py; sim project awp data by hand, D43; `tl sim assert` once), `just demo P2-I1` sqlite then pg, tour once (screens below), T09 docs (throughline-docs skill). Increment report <= 80 lines from STATE.
5. Screens (screenshot list for the owner). Merged: CWP register (widgets/cwp_register.py, keys d discipline, s state, c by CWA, / filter, F5), WBS tree (wbs_screen.py; 1-8 depth, 0 all, u unallocated), CWA register (cwa_register.py; r retired), External packages log (package_log.py; t type, c constraint sources), CWP detail panel (details/awp). To come: Path of construction (path_screen.py; [ ] version, v compare). Entry keys today: NONE (D52); after T05h: palette commands (name them in T05h; no new function key unless free).
6. Capacity: weekly use is near the owner's stop line; this STATE.md plus the tickets dispatch without re-reading anything else.
## REFS
Spec docs/build-spec/specs/m3-wbs-cwp.md; tickets in docs/tickets/P2-I1/: ready T05g-path-version-reason, T05c-path (after T05g), T11-tests (piece); reports docs/reports/P2-I1/*.md; tickets docs/tickets/P2-I1/ (T03b T06 T10c done); acceptance scripts dev/accept/P2-I1/ (S5.py worker; T10b.py copy-the-seed; S4.py lines 404-490 packages, links, proposal); CLI pattern tl_cli/cost*.py, awp_read.py; routes tl_api/routes/awp.py; client pattern tl_api/client/schedule.py, tl_tui/embedded.py:1347; text pattern tl_tui/correspondence_text.py; walks test_confidentiality_walk.py (api :142, mcp :36).
## TRAPS
Worktree /home/user/wt/p2-i1 only; never /home/user/studious-lamp. `just check` takes > 120 s and needs NODE_OPTIONS=--max-old-space-size=6144: run in background. `uv sync` after editing a pyproject. dev/tests/ is outside testpaths. Never delete /tmp/pytest-of-root, never pkill. Record keys are per project across types (D9). The seed ledger has no rollup rows and no packages (scripts copy it and add, D25). No awp or cost record has a confidentiality class: hidden checks patch `views._hidden` (D22). Root `--db` goes before the group: `tl --db X awp ...`. Use `git diff --minimal` for openapi.json. Two tickets that regenerate openapi.json must not share a batch (T10c, T03c). `.accept/` is not in .gitignore: never `git add -A`. `python -c` via uv prints a UV_NATIVE_TLS warning: harmless.
