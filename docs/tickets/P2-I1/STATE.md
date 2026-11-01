# P2-I1 STATE  r=3 base=1b93a13 C=1 ck=0 gate=n/a wt=/home/user/wt/p2-i1
## BOARD
S2 p mrg f 99ad743 schema awp merged; APPROVALS logged
S3 p mrg f f482aad awp package merged; APPROVALS logged; rev pass; F1 MD to S4
S4 p stg f - CWP, packages, RULES, D-a/b/d/e, F4; spec r3
S5 p stg f - rollup run, projector, worker fn, D-c; spec r3
T02 p stg f - load targets (now a piece, D8); spec r3
T01 t todo l - samples, mappings, loaders; after T02
T10 t todo f - read views; after S4
T03a t todo f - API routes; after T10
T03b t todo f - client methods; after T03a
T04 t todo f - CLI, reports, awp worker cmd; after S5, T10
T05a t todo f - CWP register; after T03b
T05b t todo f - WBS tree, CWA register; after T05a
T05c t todo f - path, package logs; after T05a
T06 t todo f - MCP tools; after T03a
T07 t todo l - sim AwpDesk, actor; after T03b, T06
T11 p todo f - tests + capped mutants + F1 guard + five-reader walk; after all
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
## SEC
F1 LO fixed@- S2 report 65>60 lines; waived
F2 LO fixed@adfbd1d S3 dropped redundant scope indexes
S3F1 MD open S3 key-taken check read cur_core_record without ADR-0016 filter -> S4 D-a (guard for T11)
S3F2 LO open path lookup hidden -> T11 five-reader walk
S3F3 LO open tree counts hidden -> T11 five-reader walk
S3F4 LO open missing cost-code link not re-added -> S4 F4
(review only if the owner asks. Sec rows: S3 S4 S5 T02 T03a T06)
## OPEN
(none)
## NEXT
1. Orchestrator dispatches S4, S5, T02 (disjoint paths; 3 builders = 3 slots). Merge order free; conflicts only in uv.lock (regenerate).
2. r4 (after S4 mrg): T10; (after T02 mrg) T01 as a lite ticket. T04 after S5 and T10.
3. S4 leaves .accept/p2-i1.db (WBS, 4 CWAs, path v1, 6 CWPs); T10, T04, T07 run against it.
4. Registry glue left for C2 (supervisor, <= 50 lines): add_typer (T04), MCP_ACTIONS (T06), nav entry (T05). tl_api COMMANDS and errors are in S4.
5. Every ticket: acceptance script dev/accept/P2-I1/<id>.py, no pytest; `NODE_OPTIONS=--max-old-space-size=6144 just check` first.
6. T11 spec at C2: add the F1 guard (node 1 and cost code 1 coexist, hidden record does not change the answer), five-reader walk of path lookup and tree counts (S3F2, S3F3), D-c settle, 0-line clear.
7. Twin web tickets (CWP/CWA registers, WBS tree, path, packages) belong to WEB1 after C2.
## REFS
Spec docs/build-spec/specs/m3-wbs-cwp.md; wave plan phase2-wave-plan.md; reports docs/reports/P2-I1/S2.md S3.md; W0 acceptance dev/accept/P2-W0/*.py (script style); load target contract packages/tl-modules/legacy/src/tl_mod_legacy/targets.py:133.
## TRAPS
Worktree /home/user/wt/p2-i1 only; never /home/user/studious-lamp. `just check` takes >120 s and needs NODE_OPTIONS=--max-old-space-size=6144 (pyright heap): run in background. `uv sync` after editing a pyproject. dev/tests/ is outside testpaths. Never delete /tmp/pytest-of-root, never pkill. Record keys are per project across types (core), hence D9.
