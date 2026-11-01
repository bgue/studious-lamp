# P2-I1 STATE  r=5 base=8b811a4 C=1 ck=0 gate=n/a wt=/home/user/wt/p2-i1
## BOARD
S2 p mrg f 99ad743 schema awp merged; APPROVALS logged
S3 p mrg f f482aad awp package merged; rev pass
S4 p mrg f 1fa0f90 CWP, packages, RULES, tl_api glue; rev pass
S5 p mrg f d32e1be rollup run, projector, worker; rev pass
T02 p mrg f 518f6a1 targets awp_wbs, awp_cwa; rev pass
T01 t mrg l 3e3d88c loaders, samples; 2s subject only, accepted (D19)
T10 t mrg f 8b811a4 read views; rev pass; F1 MD -> T10b
S6 p stg f - expected-link fixture awp.yaml; spec written r5; gate orch
T10b t stg f - F1 fix total_hours; after T10
T03a t stg f - API read routes, counts, timeline; after T10
T04a t stg f - tl awp group + read verbs; after T10
T04b t stg f - reports.py + tl awp report; after T10, S5
T03b t todo f - client methods; after T03a
T03c t todo f - API reports route + CSV; after T04b, T03a
T04c t todo f - write verbs, rollup request, `tl awp worker`; after T04a
T05a t todo f - CWP register; after T03b
T05b t todo f - WBS tree, CWA register; after T05a
T05c t todo f - path, package logs; after T05a
T06 t todo f - MCP tools; after T03a
T07 t todo l - sim AwpDesk, actor; after T03b, T06
T11 p todo f - tests + capped mutants + guards + five-reader walk; after all
T08 t todo f - demo; after T11
T09 t todo l - docs; after T04c, T05
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
## SEC
F1 LO fixed@- S2 report 65>60 lines; waived
F2 LO fixed@adfbd1d S3 dropped redundant scope indexes
S3F1 MD fixed@e79b789 S4 D-a namespaced keys; T11 guard (node 1 and cost code 1 coexist, hidden record keeps answer)
S3F2 LO open path lookup hidden -> T11 five-reader walk
S3F3 LO open tree counts hidden -> T11 five-reader walk
S3F4 LO fixed@1fa0f90 S4 F4
T10F1 MD open fix->T10b: total_hours exposed hidden cost code's hours (views.py:469)
T10F2 MD open activity refs unfiltered (views.py:351, schedule resolver _LINKS_SQL): T11 five-reader walk with fixture; fix is a tl_mod_schedule change, orch decides
T10F3 LO open hidden-CWP check impossible (no class on awp records): T11 fixture
(review only if the owner asks. Sec rows: S3 S4 S5 T02 T03a T06)
## OPEN
(none: Q1 answered, D21; T10/T01 open questions answered, D19 D20)
## NEXT
1. Dispatch r5 batch, 3 slots: (a) S6 builder (spec S6; orch approves schema, APPROVALS line at merge); (b) workflow T10b then T03a (disjoint paths; merge T10b first); (c) workflow T04a + T04b (disjoint; T04b mounts later). Run after the weekly reset (2026-11-02 10:00 UTC).
2. Setup in every worktree: `uv sync --all-packages`; `.accept/p2-i1.db` via `uv run python dev/accept/P2-I1/S4.py --keep .accept/p2-i1.db` when missing; never commit `.accept`.
3. After merges, r6 supervisor glue (<= 50 lines): in `tl_cli/awp.py` add `awp_report.register(app)` (T04b); later `awp_write.register(app)` (T04c). Then write r6 batch: T03b, T06 (after T03a), T03c (after T04b), T04c (after T04a; style now in the tree).
4. r6 also: T05a after T03b; T07 after T03b + T06. C2 = S4 S5 T10 T10b T03a T03b: mark when T03b merges. WEB1 twins need C2.
5. T11 spec at C2 (list): F1 guard (T10F1); T10F2/F3 hidden fixture and five-reader walk of cwp_detail activities, path lookup, tree counts (S3F2, S3F3); S6 `tl links expected` on the seed; D-c settle; 0-line clear; T02 second-reverse no-op (D17); rollup totals and by_cost_code with packages/rollup rows in the seed; requires-link path; S4, S5, T02 guard lists in their reports; loader counts (wbs 12 new 1 invalid, cwa new 5).
6. Registry glue left: add_typer awp is in T04a; MCP_ACTIONS (T06), nav entry (T05). tl_api COMMANDS and errors done in S4; openapi.json is regenerated by T03a.
7. Every ticket: `NODE_OPTIONS=--max-old-space-size=6144 just check` (background, > 120 s), acceptance script, no pytest, subject `P2-I1-<id>: ...`, commit trailer per dispatch note.
## REFS
Spec docs/build-spec/specs/m3-wbs-cwp.md; wave plan phase2-wave-plan.md; reports docs/reports/P2-I1/{S2,S3,S4,S5,T01,T02,T10}.md; tickets docs/tickets/P2-I1/ (S6 T10b T03a T04a T04b new); acceptance scripts dev/accept/P2-I1/ (S5.py shows how to run the worker; T10.py opens the seed); CLI pattern tl_cli/cost*.py; routes pattern tl_api/routes/cost.py; walk candidates test_confidentiality_walk.py:142.
## TRAPS
Worktree /home/user/wt/p2-i1 only; never /home/user/studious-lamp. `just check` takes > 120 s and needs NODE_OPTIONS=--max-old-space-size=6144 (pyright heap): run in background. `uv sync` after editing a pyproject. dev/tests/ is outside testpaths. Never delete /tmp/pytest-of-root, never pkill. Record keys are per project across types (D9). The seed ledger has no rollup rows (jobs queued, not run): scripts copy it and run the worker (D25). No awp or cost record has a confidentiality class: hidden checks patch `views._hidden` (D22). Weekly capacity 92% at r5: dispatch waits for the reset. tl-mod-awp does not depend on tl-mod-cost (do not add; callers pass cost figures).
