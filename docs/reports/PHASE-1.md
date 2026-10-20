# Phase 1 report: information backbone

Purpose: the record of what Phase 1 built, where it deviated, where each gate stands and what is left for a human or for engineering. Written 2026-10-20 by the orchestrator's exit job from the increment reports P1-I0 to P1-I8, `STATUS.md`, `APPROVALS.md` and `RISKS.md`; final trunk numbers are for trunk 9797bb8 (P1-I8 merged, `certifi` bumped). Companions: `docs/reports/RISKS.md` (register after Phase 1), `docs/adr/0020-phase1-risk-register.md`, `docs/reports/STATUS.md`, `docs/reports/APPROVALS.md`, `docs/build-spec/07-phase1-plan.md`.

**Screenshot tour:** [PHASE-1-TOUR.md](PHASE-1-TOUR.md) (real screenshots; standard activity, novel approach and unique value per capability; regenerate with `uv run python dev/tour/phase1.py`). Shared page: https://claude.ai/artifact/CdAi8C1ZS3fwAJzcSMGo1i. The tour covers P1-I3 to P1-I8.

## 1. Outcome

Exit criterion (brief §16, `07-phase1-plan.md`): receive a PDF schedule or list, derive validated CSV/XLSX, publish into target records with full traceability; the chain is visible in the feed and pushed to subscribers. Status by clause:

| Exit clause | Status | Evidence |
|---|---|---|
| Receive a PDF or list | Met for lists and file properties; **PDF content extraction is a stub by owner decision** (ADR-0008 decision 8: page count, title and author are read, text is not) | `just demo P1-I3` clause 2; `packages/tl-extract`; XER schedules are read in full (P1-I4) |
| Derive a validated CSV/XLSX | Met | Demo P1-I3 clauses 3 and 4: validation names row and field; a fixed file is a new pass with a diff; hostile files are bounded (envelope, ADR-0014) |
| Publish into target records with full traceability | Met | Demo P1-I3 clause 5: 40 tags with provenance `src.doc.ISD-001@A` and a `derived from` link; compensation takes the batch back by recorded ids; the ledger only grows |
| The chain is visible in the feed | Met | Feed cards exist for issue, answer and assess events (P1-I6); the exit chain (PDF, derived, published, feed card) is clause 7 of `just demo P1-I8`, 7/7 on SQLite and Postgres |
| The chain is pushed to subscribers | Met | Signed webhooks since Phase 0; in clause 7 the exit chain subscribes to the derived-publish events (no rule needed) and a signed webhook is verified by a loopback receiver |

The rest of the Phase 1 scope (07 header): M1 document control (P1-I2, I3), M2 standards and tags (P1-I1), M10 correspondence with the General, Document-control, Technical/RFI and Commercial domains (P1-I5, I6), M11 cost and schedule snapshots (P1-I4), threads and the integration layer (P1-I7) are built and each demonstrated by a script on SQLite and Postgres. The schema workbench, legacy loaders and lake marts are built in P1-I8 (section 2). Nothing is deployable: real accounts exist, but Entra ID, secrets at rest, key custody and a front-door rate limiter are open (section 6).

## 2. What was built, by increment

- **P1-I0 Identity, admin, Postgres for the services** (`P1-I0.md`, `-A.md`, `-B.md`; ADR-0008, ADR-0009). Accounts, scrypt passwords, opaque sessions, lockout, two roles, admin-issued agent tokens, an identity seam for Entra; the API, TUI, MCP, simulator and every `tl` group run on SQLite or Postgres through one backend factory. About 16 tickets, 5 demo clauses, parity 3,161.
- **P1-I1 M2 standards, numbering, Tag/TagClass** (`P1-I1.md`; ADR-0010). The module seam (record row plus typed side table, entry point `throughline.modules`); standards registry and code lists; tag numbers parsed into segments; class-driven mandatory psets; bulk import with preview. 14 tickets, 7 clauses.
- **P1-I2 M1 document control** (`P1-I2.md`; ADR-0011, ADR-0012). Documents, class-ordered revisions, renditions, pinned and floating links with class-aware stale pins, re-pin with diff, transmittals, review cycles, DMS register import. 20 tickets, 9 clauses.
- **P1-I2b Document controller role** (`P1-I2b.md`; ADR-0013, owner request). A third role for the controlling acts, never for agents; typed, fail-closed action list. Supervisor-built, 7 clauses.
- **P1-I3 Derivation pipeline and extractors** (`P1-I3.md`, `P1-I3-B.md`; ADR-0014). Extractor plugins (`tabular`, `pdf`, `ocr`) in a resource envelope; `DocumentSchema` validation; diff; create-only correlated publication with compensation; job queue (SQLite table, Postgres `SKIP LOCKED`). Two workstreams, 8 clauses.
- **P1-I4 Cost and XER schedule snapshots** (`P1-I4.md`; ADR-0015). Cost-code mirror with period snapshots; bounded XER reader; immutable snapshots with compare (date shifts, float erosion, critical path); activity links by stable id; lake schedule tables and float-trend mart; planner actor. 12 tickets, 10 clauses.
- **P1-SEC1 Workflow roles from the account** (`STATUS.md`; ADR-0013 addendum). Roles in a workflow transition derive from the authenticated account, never from a request.
- **P1-I5 Correspondence core, clocks, confidentiality** (`P1-I5.md`; ADR-0016). Items, threads, parties, clauses, response clocks on a project calendar, email in, General and Document-control domains; confidentiality classes enforced on every read path (API, MCP, CLI, TUI, webhooks, lake, export) with walking tests. 11 tickets, 8 clauses.
- **P1-I6 Technical/RFI and Commercial domains** (`P1-I6.md`; ADR-0019). RFI with impact flags; Commercial items with exact money and time bars; propose-only escalation rule on the I7 engine; evidence trail by day; domain feed policy. 11 tickets (all first attempt), 9 clauses.
- **P1-I7 Integration layer and record threads** (`P1-I7-A.md`, `P1-I7-B.md`; ADR-0017, ADR-0018). Actions, rules (dry run, depth limits, kill switch), signed inbound endpoints with restricted JSONata mapping, enrichment with three acceptance policies; threads with eleven slash verbs (seven have targets), preview token, propose-only for agents. Two workstreams.
- **P1-I8 Schema workbench, legacy loaders, lake marts, exit** (`P1-I8.md`, ticket reports in `docs/reports/P1-I8/`; builds on ADR-0010 and ADR-0014 to ADR-0017). Process v2 from round 2. Schema registry module `schemareg` (`SchemaPackage` lifecycle Draft to Retired, `Adoption` pins, `Waiver`, a ledger source feeding the effective schema); classification engine and impact report; `tl schema` governance commands (package, adopt, waiver, crosswalk, conformance, export-git, import-git); workbench TUI on `Ctrl+O` with a review screen; conformance dashboard that counts waived records apart. Legacy module `legacy` (`LoadRun`, `tl load`) with extract, bronze, profile, plan, load, reconcile and compensate, and three loaders (`dms-register`, `instrument-index`, `equipment-list`; no line-list loader, owner decision: piping lines are not a tag class). Lake: documents silver, marts `mart_document_status|turnaround|issues` and `mart_schedule_history`, none of which holds a row the lowest reader may not read. Builder pieces S1 to S6, S9, S10 and 14 Haiku tickets, all merged; 7-clause exit demo.

## 3. Gates on the final trunk

Commands from `docs/build-spec/04-gates.md` §1. The third column holds the latest numbers the increment reports give (branch or merged tree); the orchestrator fills the last column after the final merge.

| Gate | Command | Last number seen | Final trunk |
|---|---|---|---|
| Lint, format, types | `just check` | green on every increment tree and trunk merge | clean (trunk 9797bb8) |
| Codegen drift | inside `just check` | green (OpenAPI and catalog regenerated, never hand-edited) | clean (inside `just check`) |
| Licences | inside `just check` | green; new: `pypdf` BSD, `jsonata-python` Apache-2.0, `PyJWT` MIT, zxcvbn word data MIT | licences ok |
| Tests | `just test` (from trunk 70ddd59 `just gate`) | P1-I5 10,048 passed (1 h 15); P1-I6 11,648 in four parts (about 2 h); timing tests fail under load and pass alone | Whole suite run as the P1-I8 DONE gate on 79f2bcf in four parts: 6048 + 3467 + 1227 + 1405 passed. One stale palette snapshot (Ctrl+O) refreshed in 4e1bba8; one load-flaky inbound-worker test (`test_int_inbound_worker`) passes alone and in the rerun |
| Parity | `just test-parity` / `just gate-pg <dirs>` | last whole run P1-I2: 4,314 (1 h 55); since then touched directories only (P1-I6: 1,139); the whole run exceeds the 2 h background limit | `just gate-pg` on the dirs P1-I8 touched (79f2bcf): 756 passed, 5 skipped. The whole parity suite is run by the owner locally at the exit commit; result recorded in `STATUS.md` |
| Projection determinism | `uv run pytest tests/property -k projection` | inside `tests/`; not reported separately | 3 passed, 1 deselected |
| TUI snapshots | `just test-tui` | P1-I7: 1,043 passed (34 snapshots) | Not reported separately; the snapshot that went stale (palette, `Ctrl+O`) was refreshed in 4e1bba8 |
| Contract tests | `uv run pytest tests/contract` | inside `tests/`; green | 139 passed |
| Schema classification | `tl schema classify --base origin/main` | not built before Phase 1; R12 | Exists in part: the engine (`tl_schema.classify`, packages and LinkML) and `tl schema package classify REF` / `analyse` are on trunk, and submit refuses breaking and forbidden packages. The repository form `tl schema classify --base <git ref>` (`classify_linkml`) is not wired to a command or a job; R12 stays open for it |
| Secret scan, dependency audit | `just scan-secrets`, `just audit-deps` | not reported per increment | Secret scan: 0 findings. Dependency audit: PYSEC-2026-4320 in `certifi` found at exit, fixed by bumping to 2026.10.19, then no known vulnerabilities |
| CI workflow | GitHub Actions | deferred by the owner (ADR-0008 decision 9); H6 stays open | not run |
| Increment demos | `just demo P1-I0` ... `P1-I7` | all pass on SQLite and Postgres (5, 7, 9, 7, 8, 10, 8, 9 clauses; I7 and I7B with the thread chain) | Not re-run as a set at the exit; each passed at its increment close (`STATUS.md`). P1-I8 is the exit demo below |
| Exit demo | `just demo P1-I8` | 7 clauses (schema 1 to 4; load, reconcile, compensate 5; lake marts and XER 6; exit chain 7) | 7/7 on SQLite and Postgres, exit 0 (79f2bcf) |

## 4. Deviations and what slipped

| Deviation | Where decided | Consequence |
|---|---|---|
| **Increments added:** P1-I0 (auth and Postgres services), P1-I2b (controller role), P1-SEC1 | ADR-0008, ADR-0013, `STATUS.md` | Phase 1 has ten increments plus a fix, not eight |
| **P1-I6 landed after P1-I7**; its escalation rule runs on the I7 engine | `P1-I6.md` | The plan's "rules stub" was never built |
| **Extraction is a stub:** no PDF text, no OCR, no model call; the enricher is deterministic | ADR-0008 decision 8 | R4 is now measured on a pipeline, not on accuracy |
| **Permissions are three roles plus access words**, no per-record lists, no project roles | ADR-0008 decision 3, ADR-0011, ADR-0013 | Simulated people hold `user` only; they cannot issue or sign off, so demos need named operators |
| **Dispatch verbs:** `/assign /due /hold /release` and `/raise rfi` (before I6) answer `dispatch_unavailable` | ADR-0018 | Targets arrive with the modules that own them |
| **TUI keys moved:** correspondence on F5, schedules F12, RFI and Commercial Ctrl+G, integration Ctrl+R and Ctrl+E | `P1-I5.md`, `P1-I6.md`, `P1-I7-A.md` | Every function key is taken |
| **Whole parity suite not run since P1-I2**; touched directories only | `P1-I3.md`, `P1-I4.md` | The owner runs the whole suite locally at the exit commit; result recorded in `STATUS.md` |
| **GitHub Actions deferred**; no workflow run exists | ADR-0008 decision 9 | X12 unchanged |
| **Supervisors built most core pieces**, and several planned tickets were taken over | increment reports (L-P1-I3-5) | Cost 11.8 B input tokens (process v2, section 7) |
| **Lake mirrors only schedule tables** from modules; module-table marts and legacy loaders | `P1-I4.md`, ADR-0010 condition (view `v_<module>_<class>` built in I2) | Closed in P1-I8: documents silver and four marts (documents status, turnaround, issues; schedule history) are built for the lowest reader, and three legacy loaders exist. No line-list loader (owner decision) |
| **Illustrative Commercial figures** (14-day time bar) approved under delegation, not by the commercial lead | `APPROVALS.md` | Confirm per contract (section 6) |

## 5. Security

One fresh-context review (or more) per increment, scoped to the supervisor-tier pieces and every remote door. Counts are taken from the reports and `STATUS.md`; where a pass lists "findings" without a severity split, the table counts only what is rated, so MD and LO are lower bounds. All were fixed with a test that fails without the fix; none was open at an increment close.

| Increment | Passes | HI | MD | LO | Notable |
|---|---|---|---|---|---|
| P1-I0 | 4 (A) + 2 (B) | 2 | 8 | 6 | auth core; `--actor` impersonation; backend URL leaks |
| P1-I1 | 1 + re-review | 1 | 2 | 3 | generic `UpdateRecord` reached registry records |
| P1-I2 | 3 + import path | 0 | 10 | 20 | generic commands, client-set link source, no permission model |
| P1-I2b | 1 | 0 | 0 | 4 | fail-closed action list |
| P1-I3 | A: 3, B: 4 | 7 | 11 | 8+ | hostile PDF and XLSX (cost and memory), unbounded XML tree, regex memory |
| P1-I4 | 3 | 0 | 11 | 3+ | forged `svc:` source, case-folded columns, JSON text as one string, lake mixing projects |
| P1-SEC1 | 1 | 0 | 1 | 3 | workflow `actor_roles` was a client claim |
| P1-I5 | 19 fixes | 1 | 4 (+1 MD/LO) | 2 | webhook leaked a hidden stream; sweep, lock-out, EML bounds |
| P1-I6 | 3 | 0 | 3 | 7 | Commercial access, feed cards tagged by record, export file mode |
| P1-I7 | A: 2 + re-check, B: 1, confidentiality: 1 | 3 | 11+ | 15+ | enrichment layer writable through `CreateRecord`, `/remind` leaked a hidden id, preview token replay |
| P1-I8 | 2 reviews + re-check | 2 | 5 | 5+ | `LoadRun` files leaked restricted rows, YAML alias bomb, forged effective-at, export temp file followed a link; residual LO `TagTarget` |
| **Total (I0 to I8)** | | **16** | **66+** | **76+** | |

P1-I8 counts come from `P1-I8.md`: first review 2 HI and 4 MD, final review 1 MD, five rated LO (F7, F8, F9 and the final F2, F3) plus one accepted, unrated item and the TagTarget residual; the `STATUS.md` line counts LO differently (2 fixed, 1 residual), so LO stays a lower bound. All totals are lower bounds wherever a row ends in `+`.

Pattern: every new door (file reader, route, tool, worker, export) produced a finding the first time, as in Phase 0 (X4). The recurring classes are in `RISKS.md` X24 to X28 and `phase2-risks.md` R-P2-3, R-P2-8.

## 6. Human gates

All gates below were crossed by the orchestrator under the delegation of ADR-0008 decision 6 and recorded in `APPROVALS.md` (69 entries; 42 mention Phase 1, including 17 schema merges or changes and 3 dependency or data approvals). Owner decisions made directly: ADR-0008 (scope, auth model, delegation, stubs), ADR-0012 (class-aware stale pins), ADR-0013 (document controller role), the MPL-2.0 allow-list (Phase 0), process v2 and building tools A1 to A3 before Phase 2 (2026-10-20).

**Pending for the owner or a named human:**
- Review the delegated approvals in `APPROVALS.md` (H8), including ADR-0009, ADR-0016, ADR-0017, and the Commercial workflow and time-bar definitions of ADR-0019 (commercial lead).
- Entra ID (OIDC) and project-level roles (Q5, Q6); a front-door rate limiter on `/auth/*` is a release gate (ADR-0009 section 15); penetration test.
- Secrets at rest (H3, X10), key custody and retention classes (H5, Q8), `tl migrate` T99 (H1), dropping the old feed index on existing databases (H2).
- The first CI run (H6; Actions deferred).
- Phase 2 owner questions P2-Q1 to P2-Q13 (section 9).
- The two P1-I8 schema merges in `APPROVALS.md` (`schemareg` with its `SchemaPackage` lifecycle, `Adoption` and `Waiver`; `legacy` with `LoadRun`) and the P1-I8 role choices (steward and data manager are admins; export is admin only). No new dependency was added.
- The whole parity suite at the exit commit, run by the owner locally (section 3).

## 7. Process changes during the phase

Phase 1 began on the Phase 0 relay process (long-lived supervisors resumed for 8 to 12 rounds). Measured on 124 agent transcripts, supervisors used 93% of all input tokens (11.8 B) through context times calls (about 430 k tokens on 1,200 to 2,400 calls per increment); usage limits stalled the run five times at 5 to 9 concurrent agents. On 2026-10-20 the owner adopted process v2 (`docs/build-spec/process-v2.md`; rules in the `subagent-throughput-process` skill): short-lived supervisors seeded from `STATE.md`, builder pieces for core code, Haiku-first tickets, one deterministic test gate (`just gate`, `just gate-pg`) with capped mutation and one security review per wave, three heavy slots, a planner-tier plan check before big plans, and Code 92 for agent-to-agent messages. The target is 3 to 5 times fewer input tokens; P1-I8 is the first increment run partly under it (from round 2: builder pieces S1 to S10 and Haiku tickets with a deterministic gate; its token cost was not measured in this report), and Phase 2 is the first plan written for it. Tools A1 to A3 (`dev/state.sh`, `dev/review-pack.sh`, `dev/relay-lint`) are built as Haiku tickets before Phase 2 wave 1.

## 8. Follow-ups

Named for this report: `tl schema promote` (promote a reviewed package out of the workbench; not shipped in P1-I8, it needs read-time aliases in the effective schema, brief §27.5); MCP schema tools for agents (read, validate and diff packages; the dev MCP server lacks LinkML change validation); the escalation-rule condition on answer data (a rule's `when`/`condition` reads the envelope and psets, not a module table, so it proposes for every answered RFI); the `expected_version` 0 convention (D14: 0 is treated as not given in 19 older sites; change to `is not None` module-wide); the `TagTarget` class (source: the P1-I8 first security review, LO residual: tags carry no confidentiality class, so `TagTarget` ignores the run's class; see `P1-I8.md`); update `phase2-risks.md` R-P2-3 (fixed by P1-SEC1).

**Security and identity.** Front-door rate limiter; Entra and project roles; separation of duties for issuing; a failure reason a controller can read for module commands; controller-level automation over restricted records (Phase 2 question); a model-based enricher needs its own ADR; extractor sandbox (seccomp or namespaces) beyond the envelope; Postgres pool unmeasured under load; LISTEN/NOTIFY not wired.

**Extraction and documents.** Real PDF text and OCR providers; type the `ContentRecorded` payload (schema change); updates through publication (create-only today); escape `=+-@` cells when exporting text to spreadsheets; a "newer revision in review" marker beside a healthy pin; revisions with files and issue dates from legacy registers (the `dms-register` loader loads documents, not revisions with files); a line-list class and loader (piping lines are not a tag class today); register the reconciliation report as a document (today a file of the run).

**Schedule, cost, commercial.** Re-pin a link to another snapshot in the TUI; a cost role other than admin; `TASKRSRC` and baselines are in the raw bundle only; moving a cost code is refused; a finer Commercial role and a commercial-manager simulator actor; outgoing mail transport behind the issue stub; schedule the clock sweep on the integration runner; thread-by-number for hyphenated project ids; targets for `/assign /due /hold /release`.

**Simulator and tests.** Let simulated people hold a controller role (dev-token roles from the account); wall-clock limits that scale with load for the timing tests; whole parity run on dedicated time.

**Carried from Phase 0 (still open).** Link-count filters over 150 ms at 100k records (X23); Postgres statement-bound rebuild (R1, X6); one write lock (X8); upgrade path and event upcasting (X15); locked-pset clearing (Q14).

**Docs and memory.** Curated at the exit: `docs/memory/LEARNINGS.md` keeps 42 active entries (210 lines) and 168 moved to `docs/memory/archive/phase-1.md` with stable ids (`grep -rn -A6 <id> docs/memory/archive/`). Next curation at the Phase 2 exit.

## 9. Next: Phase 2

Phase 2 (execution planning and materials) is planned in `docs/build-spec/08-phase2-plan.md` (v0.3, process v2) with ranked risks in `docs/build-spec/phase2-risks.md`. It cannot start wave 0 until the owner answers `docs/build-spec/phase2-owner-questions.md` (P2-Q1 to P2-Q13: rules of credit, IWP sign-off role, materials authority, ERP stubs, inventory as events or records, simulator roles, delegation of gates). Before wave 1: build A1 to A3, run the planner-tier plan check on the Phase 2 plan, and freeze the wave-0 contracts.
