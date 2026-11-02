# P2-I1 STATE  r=6 base=c325f8b C=1 ck=0 gate=n/a wt=/home/user/wt/p2-i1
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
T03b t stg f - client methods; ticket written r6
T06 t stg f - MCP tools + propose_cwp; ticket written r6
T10c t stg f - view fields (allocated, package title/cwps, wbs cwps); r6
T03c t todo f - API reports route + CSV; after T10c (openapi.json)
T04c t todo f - cwp+package write verbs, rollup, worker; r7
T04d t todo f - wbs, cwa, path write verbs; r7
T05a t stg f - CWP register + awp_text.py (Textual-free); draft, after T03b T10c
T05b t stg f - WBS tree, CWA register + wbs_text, cwa_text; draft, after T05a
T05c t stg f - path, packages + path_text, package_text; draft, after T05a
T07 t todo l - sim AwpDesk, actor; after T03b, T06
T11 p todo f - tests + capped mutants + guards + five-reader walk; after all
T08 t todo f - demo; after T11
T09 t todo l - docs; after T04c, T04d, T05
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
1. Dispatch r6 as ONE workflow of 3 (disjoint paths): T03b, T06, T10c. Merge T10c first, then T03b, T06. Mark C2 when T03b merges (S4 S5 T10 T10b T03a T03b).
2. Setup in every worktree: `uv sync --all-packages`; `.accept/p2-i1.db` via `uv run python dev/accept/P2-I1/S4.py --keep .accept/p2-i1.db` when missing; never commit `.accept`.
3. r7 supervisor: complete T05a Interfaces from the tree (T05a-c are drafts with fixed contracts, D27); write T03c (route `/awp/reports/{name}` + CSV; regenerates openapi.json, so after T10c), T04c, T04d (CLI write verbs over AWP_COMMANDS rows: model, handler, access; helper like tl_cli/cost.py acting/require_command; `awp_write.register(app)` mounts are glue), T07.
4. r7 batch: T05a + T03c + T04c (T05b/c after T05a; T07 after T03b + T06). Glue left: nav entries and palette (T05: nav_tree.py, app.py), awp_write/awp_setup mounts.
5. T11 spec at C2 (list): F1 guard (T10F1); T10F2/F3 hidden fixture and five-reader walk of cwp_detail activities, path lookup, tree counts (S3F2 S3F3); S6 expectation via `tl link list` on the seed; D-c settle; 0-line clear; T02 second-reverse no-op (D17); rollup totals and by_cost_code with packages and rollup rows; requires-link path; T10c fields incl. a hidden CWP; S4 S5 T02 guard lists in their reports; loader counts (wbs 12 new 1 invalid, cwa new 5); no-textual import test per text module; ApiClient, embedded and fake answer the same CWP.
6. C2 -> C3 (T11 tests piece) -> C4 (demo P2-I1 sqlite + pg, tour once). Every ticket: `NODE_OPTIONS=--max-old-space-size=6144 just check` (background), acceptance script, no pytest, subject `P2-I1-<id>: ...`, trailer per dispatch note.
## REFS
Spec docs/build-spec/specs/m3-wbs-cwp.md; reports docs/reports/P2-I1/*.md; tickets docs/tickets/P2-I1/ (T03b T06 T10c ready; T05a T05b T05c drafts); acceptance scripts dev/accept/P2-I1/ (S5.py worker; T10b.py copy-the-seed; S4.py lines 404-490 packages, links, proposal); CLI pattern tl_cli/cost*.py, awp_read.py; routes tl_api/routes/awp.py; client pattern tl_api/client/schedule.py, tl_tui/embedded.py:1347; text pattern tl_tui/correspondence_text.py; walks test_confidentiality_walk.py (api :142, mcp :36).
## TRAPS
Worktree /home/user/wt/p2-i1 only; never /home/user/studious-lamp. `just check` takes > 120 s and needs NODE_OPTIONS=--max-old-space-size=6144: run in background. `uv sync` after editing a pyproject. dev/tests/ is outside testpaths. Never delete /tmp/pytest-of-root, never pkill. Record keys are per project across types (D9). The seed ledger has no rollup rows and no packages (scripts copy it and add, D25). No awp or cost record has a confidentiality class: hidden checks patch `views._hidden` (D22). Root `--db` goes before the group: `tl --db X awp ...`. Use `git diff --minimal` for openapi.json. Two tickets that regenerate openapi.json must not share a batch (T10c, T03c).
