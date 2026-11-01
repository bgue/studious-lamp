# P2-I1 STATE  r=4 base=47f4e76 C=1 ck=0 gate=n/a wt=/home/user/wt/p2-i1
## BOARD
S2 p mrg f 99ad743 schema awp merged; APPROVALS logged
S3 p mrg f f482aad awp package merged; rev pass
S4 p mrg f 1fa0f90 CWP, packages, RULES, tl_api glue; rev pass; F1 fixed via T02
S5 p mrg f d32e1be rollup run, projector, worker; rev pass
T02 p mrg f 518f6a1 targets awp_wbs, awp_cwa; rev pass
T10 t disp f - read views (r4); after S4
T01 t disp l - samples, mappings, loaders (r4); after T02
T03a t todo f - API routes + link/file counts, timeline (D15); after T10
T03b t todo f - client methods; after T03a
T04 t todo f - CLI, reports, awp worker cmd; after T10 (S5 mrg)
T05a t todo f - CWP register; after T03b
T05b t todo f - WBS tree, CWA register; after T05a
T05c t todo f - path, package logs; after T05a
T06 t todo f - MCP tools; after T03a
T07 t todo l - sim AwpDesk, actor; after T03b, T06
T11 p todo f - tests + capped mutants + guards + five-reader walk; after all
T08 t todo f - demo; after T11
T09 t todo l - docs; after T04, T05
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

## SEC
F1 LO fixed@- S2 report 65>60 lines; waived
F2 LO fixed@adfbd1d S3 dropped redundant scope indexes
S3F1 MD fixed@e79b789 S4 D-a namespaced keys; T11 guard (node 1 and cost code 1 coexist, hidden record keeps answer)
S3F2 LO open path lookup hidden -> T11 five-reader walk
S3F3 LO open tree counts hidden -> T11 five-reader walk
S3F4 LO fixed@1fa0f90 S4 F4
(review only if the owner asks. Sec rows: S3 S4 S5 T02 T03a T06)
## OPEN
Q1 `tl links expected` shows no CWP miss at Released: `default_expected_links()` reads only schema/fixtures/links/; the awp.CWP requires-EWPRef expectation is in schema/modules/awp/cwp.yaml. Needs a schema-labelled file schema/fixtures/links/awp.yaml (not Haiku, 01-tiers 6.6). Proposal: piece S6 (tiny, Gate: orch per P2-Q10, APPROVALS line) + T11 test of `tl links expected` on the seed; alternative: default_expected_links also reads module schema (tl_core change, larger). needs orch raised S4
## NEXT
1. Orchestrator dispatches T10 and T01 (disjoint paths; ticket-batch-v2). Each starts with S4.py --keep to build .accept/p2-i1.db in its own worktree.
2. Answer Q1: yes -> r5 writes S6 spec (schema/fixtures/links/awp.yaml); no -> waive, T11 documents the gap.
3. r5 (after T10 mrg): T03a (routes + counts + timeline, walk entries), T04 (CLI + reports + `tl awp worker`). Then T03b, T06, T05a.. per spec 10.
4. C2 = S4 S5 T10 T03a T03b: mark when T03b merges; WEB1 twins (CWP/CWA registers, WBS tree, external packages) need C2 routes and client methods: NOT ready.
5. Registry glue for C2 (supervisor, <= 50 lines): add_typer (T04), MCP_ACTIONS (T06), nav entry (T05). tl_api COMMANDS and errors done in S4.
6. T11 spec at C2: F1 guard, five-reader walk of path lookup and tree counts (S3F2, S3F3), D-c settle, 0-line clear, T02 F2 second-reverse no-op, S4 guard list (S4 report), S5 guard list (S5 report), T02 guard list.
7. Every ticket: setup `uv sync --all-packages`; `NODE_OPTIONS=--max-old-space-size=6144 just check`; acceptance script; no pytest; subject `P2-I1-<id>: ...`.
## REFS
Spec docs/build-spec/specs/m3-wbs-cwp.md; wave plan phase2-wave-plan.md; reports docs/reports/P2-I1/S2.md S3.md S4.md S5.md T02.md; tickets docs/tickets/P2-I1/T10-read-views.md T01-samples-loaders.md; W0 acceptance dev/accept/P2-W0/*.py (script style); load target contract packages/tl-modules/legacy/src/tl_mod_legacy/targets.py:133.
## TRAPS
Worktree /home/user/wt/p2-i1 only; never /home/user/studious-lamp. `just check` takes >120 s and needs NODE_OPTIONS=--max-old-space-size=6144 (pyright heap): run in background. `uv sync` after editing a pyproject. dev/tests/ is outside testpaths. Never delete /tmp/pytest-of-root, never pkill. Record keys are per project across types (core), hence D9.
