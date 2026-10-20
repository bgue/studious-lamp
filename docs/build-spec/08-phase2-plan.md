# Build spec 08 — Phase 2 plan: Execution planning and materials

Brief: §16 Phase 2. M3 field work packaging (COAA WFP), M4 materials, M9 requisitions and work orders; lake gold
marts; simulator scenarios. Six increments. Ticket IDs `P2-I<n>-T<nn>`.

Status: v0.3, revised 2026-10-20 for process v2 (`process-v2.md`; rules in the `subagent-throughput-process`
skill): builder pieces instead of supervisor-built code, Haiku tickets wherever the interface is in the tree, waves
sized for 3 slots, one security review per wave, `STATE.md` checkpoints per increment, and a plan check before
wave 1. v0.2 (2026-10-17) was revised against what Phase 1 built; Phase 1 is now complete on the trunk (P1-I6 done).
Companions: `phase2-owner-questions.md` (decisions the owner makes before the phase starts; untouched by v0.3),
`phase2-contracts-draft.md` (the shared contracts of the fanouts, DRAFT until the orchestrator freezes them),
`phase2-risks.md` (ranked risks and open technical questions).

Tier letters in the tables: **H** Haiku ticket (`review: lite` or `full` set in the ticket), **B** builder piece
(one-shot Sonnet from a piece spec, always `full` review, orchestrator or human sign-off per `04-gates.md` §3),
**O** orchestrator. There is no supervisor-built code in this plan; the supervisor's own commits per round are
registry lines, `just gen`, held tests and `STATE.md`.

**Phase exit (§16):** issue an IWP with a readiness check covering documents, materials, and scaffold, on a simulated
project, on SQLite and Postgres.
**Human gates:** every `schema/modules/**` and `schema/fixtures/**` merge; the `awp.*` keys in
`schema/settings/platform.yaml`; new roles and every access-level table (ADR-0013 mechanism); the rules-of-credit
company package (brief Q16); the IWP release and sign-off definition (`awp.release.signoff_roles`); any new
dependency (PDF rendering, QR). Whether these are delegated to the orchestrator as ADR-0008 decision 6 did for
Phase 1 is owner question P2-Q10.

---

## 0. What Phase 2 builds on (the seams, as built)

Every M3, M4 and M9 record is a module record on the ADR-0010 seam. The table names the mechanism each increment
uses, so no supervisor re-invents it. Names are those in the code; `p1/i4` names are marked.

| Seam | As built | Phase 2 use |
|---|---|---|
| Module records | `tl_core.modules.ModuleSpec` (record types, projectors, `bound_psets`, `numbering_patterns`, `generic_commands`, `generic_guards`, `proposable`); one `cur_core_record` row plus one typed row per record; `create_module_record` (`composed_key=True` for keys the module builds; `@` is the reserved key character); entry point `throughline.modules`; generated flat views `v_<module>_<class>` | New modules `awp` (M3), `materials` (M4), `requisitions` and `scaffold` (M9), each with `schema/modules/<m>/module.yaml`, a `module.py` with `spec()` and an entry point. Default allow-list closed: each type lists the generic commands it takes and a guard per state-dependent one |
| Module commands and access | `tl_api.commands.CommandSpec(model, handler, access)` with `Access = Literal["admin","controller","company","user"]`; `action_for` gives `admin.command.<Name>` or `control.command.<Name>`; `controller_actions()` builds the explicit set the `RoleAuthorizer` opens to a `document_controller`; CLI gates `require_admin`, `require_controller`, `require_session` (`tl_cli.session`) | Every Phase 2 controlling act (release and sign-off, issue, close-out, inventory adjust and scrap, requisition approval) is a module command with an access word. Which roles exist is P2-Q2 and P2-Q3 |
| Roles | `admin`, `document_controller`, `user` (`tl_core.auth.types.ROLES`, stored alphabetically; add a role by extending `ROLES` once, L-P1-I2b-5). Agents hold `user` only and are refused every `admin.*` and `control.*` action | A new AWP role, if the owner wants one, follows ADR-0013: a `Literal` access word, an action prefix, an explicit action set built from the typed command table, the accounts screen key. Supervisor-built, human gate |
| Agents propose only | `ProposableCommand(tool, model, handler, access)` on the spec; `proposable_tools()` merges them into the proposal table; `accept_proposal(..., holds=)` requires the accepting person to hold the command's access (ADR-0014 §8); `MCP_ACTIONS` is a closed list | Each increment declares its proposable commands (raise a constraint, request material, propose a reservation) and adds read tools only; a new tool is closed until listed (L-P1-I4-17) |
| Workflow engine | Definitions in `schema/fixtures/workflows/<module>-<class>.yaml`; guards `required_psets`, `conformance`, `required_links`, `expected_links`, `roles`; `tl:expects_link` (brief §7.1) in `schema/core/annotations.yaml`; module handlers move state with `handle_transition_workflow(..., by_module=True)` | IWP, CWP, Scaffold, Requisition and WorkOrder workflows are fixtures. **The `roles` guard reads `TransitionWorkflow.actor_roles`, a client-settable body field (`request_model` strips `actor` only); it is a caller claim, not a permission.** Sign-off is therefore a module command gated by access, never a `roles` guard (see §1 I2 and `phase2-risks.md` R-P2-3) |
| Job queue and runner | `job_queue` operational table (`schema/core/jobs.yaml`); `tl_core.jobs.JobRunner(open_uow, kinds=[JobKind...])` with `started/prepare/run/settle/failed/expired`; `SqliteJobQueue`, `PostgresJobQueue` in `tl_adapters.queue`; lease 300 s, 3 attempts, retry 30 s × attempt; each worker CLI lists its kinds by hand (`tl derive worker`, `tl xer worker`) | Readiness evaluation (`awp.readiness`), the allocation and progress rollups (`awp.rollup`), scaffold inspection due lists and the lake second pass are job kinds, each in bounded runs that derive their work from state (L-P1-I4-12). One `tl awp worker` runs the Phase 2 kinds; a shared worker that loads kinds from the modules is a follow-up contract |
| Envelope for untrusted files | `tl_core.derivation.envelope.run_in_envelope` (spawned child, scrubbed environment, `RLIMIT_AS` 1 GiB, CPU and 60 s wall clock, JSON over a pipe, nothing unpickled); readers refuse, never cut; fixed messages | The item-library CSV, the MTO import, the actual-hours CSV and any template file a person uploads are read inside it, with the P1-I3B and P1-I4 bounds pattern (total and weighted bounds, ASCII digits, no NUL or direction marks: `tl_core/text.py` on `p1/i4`) |
| Derivation pipeline (P1-I3, ADR-0014) | `DocumentSchema`, `DerivedDocument`, `ProcessingJob`; `PublishMapping` is data; publication writes only through module commands, create-only, one correlation id with the reserved `derive:` prefix, `record_ids` recorded for exact compensation; `start_extraction` and `propose_import` are proposals | MTO lines (I3 T05) are published from a derived document through `materials` commands with a `PublishMapping` target kind `mto`: no new import path. Compensation reverses recorded ids |
| Reserved identifiers | `tl_core.services.reserved` (`derive:` correlation prefix; sources `import:derived-`, `compensation:`); `RESERVED_RELATION = "supersedes"`; system link sources `rule`, `enricher`, `import`, `mapping` need `by_module`; the check is in the body model every command route builds (L-P1-I3-10) | Phase 2 adds prefixes for its server-made batches (rollup, readiness, progress export) to the same list; every constraint a rule or a check raises is written with `by_module` and source `rule` |
| Links | Thirteen relations in `tl_core.links.vocabulary`; a module cannot add one (L-P1-I4-4): the type of the target says the meaning; link counts and `linked(...)` filters in the query language; pins and the class-aware stale rule (ADR-0012) | IWP scope is `belongs_to` / `contains`; a constraint `blocks` its IWP; a material request `requires`; a document pin on an IWP is `references` pinned to a revision (stale pins are the documents check); activities and cost codes by `references` plus the target type |
| Cost and schedule (P1-I4, ADR-0015, `p1/i4`) | `cost.CostCode` (measure matrix), `cost.CostSnapshot`, `cur_cost_snapshot_value`; `ImportCostSnapshot` is admin; `schedule.Schedule`, `ScheduleSnapshot` (job `schedule.build`, typed rows in `sched_*` operational tables), `schedule.ActivityRef` made by `LinkActivity`; `tl_mod_schedule.resolver.resolve_activity`, `links_to_activities`, `orphaned_links`; `tl_mod_schedule.lookahead.look_ahead(conn, snapshot, weeks, scope=)`; `tl_mod_schedule.reports.unscheduled_records` takes the record type (the IWP-vs-activity report waits for `awp.IWP`); lake second pass `tl_lake.xer`, mart `mart_float_trend` | CWP and IWP link to activities with `LinkActivity`; the `LookAhead` of I5 joins `look_ahead` with `cur_awp_readiness`; WBS nodes link cost codes by `references` to `cost.CostCode`; the progress rollup writes earned quantities per cost code for the export, never into `cur_cost_costcode` (the mirror stays the cost system's) |
| Settings | Platform keys live in `schema/settings/platform.yaml`; `register_definitions` serves extension types only (`<namespace>.<TypeName>` owners; `platform` refused), so a module cannot register keys today | The `awp.*` keys of brief §30.5 go into `platform.yaml` (a gated change). A `ModuleSpec.settings` hook is an alternative that needs an ADR (P2-Q9) |
| Numbering | `tl_core.numbering.allocator.allocate_key` inside the creating transaction; patterns from `ModuleSpec.numbering_patterns`, loaded from a standards edition (`co.acme.<x>@<v>.yaml`, `tl standards load`); `reserve_range` is not built | `co.acme.awp@1.0.0.yaml` carries the CWP, IWP, constraint, requisition, work order and scaffold patterns and code lists (disciplines exist; add constraint types, requisition kinds, tag colours, location kinds). Offline reserved ranges stay Phase 3 |
| Simulator | `tl_sim.scenario.ROLE_NAMES` (people `user:sim-*`, `user` role only), `INJECT_EVENTS = ("material_late", "design_revision", "post")` (today `material_late` posts an announcement), actors in `tl_sim/actors/`, `Scenario.operators` (`p1/i4`: the acts simulated people may not do, excused in `sim_assert`, at most 8) | Actors `workface_planner`, `materials_coordinator`, `scaffold_supervisor`, `foreman`; `material_late` becomes a real late receipt; release, sign-off and issue run as an operator unless P2-Q6 gives simulated people a role |
| Demos | `dev/demos/<id>.sh` with `TL_DEMO_BACKENDS` (default `sqlite postgres`), a throw-away Postgres database dropped afterwards, one `PASS` line per clause, a Python driver `p<n>_i<m>_demo.py`; `just demo <id>` | Every Phase 2 demo below follows `dev/demos/P1-I3.sh` |
| TUI | `tl_tui.client.ClientInterface` (Protocol), `embedded.py`, `remote.py` and the fake; `app.py` bindings F1 to F12 are all taken (`F12` schedules on `p1/i4`); no business logic in screens | Phase 2 screens open from the navigation panel and the palette, not from function keys. Each increment adds its client methods in one supervisor piece before the screen tickets go out (the P1-I4 S9 pattern) |

### What Phase 1 did differently from what the v0.1 plan assumed

| v0.1 assumption | Phase 1 reality | Change in this plan |
|---|---|---|
| "sign-off by two roles" from `awp.release.signoff_roles` through workflow roles | Three roles exist; the workflow `roles` guard is a caller claim; controlling acts are module commands with an access word | I2 sign-off is a module command `SignOffIWP` (access per P2-Q2) recording distinct signers; the setting names roles that exist |
| `cur_readiness` as a projection updated inline | Projections are functions of events; cross-module state (stale pins, reservations, scaffold tags) is read, not projected; heavy derived state is async (brief §5.4) | Readiness is a job kind that appends `IWP.ReadinessEvaluated` (the check states, small) and `cur_awp_readiness` is projected from that event; rebuild stays deterministic and the lake gets history for free |
| Stubs returning `n/a` for materials and scaffold checks inside the readiness engine | Plugins are found by entry point and the host never imports them (P1-I3 extractors, ADR-0010 modules) | Checks are plugins under `throughline.readiness_checks`; `materials` (I3) and `scaffold` (I4) ship theirs; the awp module ships documents, RFIs, permits, labour, predecessors, model slice (the last three return `n_a` with a note until their modules exist) |
| `InventoryTransaction` as a record type (one `cur_core_record` row and a feed card per movement) | 17 statements per new record on Postgres (L-P0-I8D-1); feed noise (R7); links need both ends as records | Movements are events on the stock-lot stream with typed references, projected into `cur_materials_movement`; the brief's cross-references become typed columns. P2-Q5 confirms (a deviation from brief §9 M4 that needs an ADR) |
| MTO import "from derived documents (Phase 1 pipeline)" as its own importer | Publication is a `PublishMapping` with a `target_kind` and a module command per kind, create-only, compensable | I3 T05 adds `target_kind: mto` and `PublishDerivedMto` (`controller`); nothing else |
| `/dispatch material-request` and `/hold` from threads, constraint source `rule`, `IWP.Ready` webhook | Threads and dispatch (P1-I7 WS-B), the rules engine (P1-I7 WS-A) and the RFI record (P1-I6) are still to come at the time of writing; `IWP.Ready` is already in the brief's default webhook list, the catalog is generated from `tl:event_type` classes | Each is consumed through the interface `07-phase1-plan.md` names and verified at phase start (§0.1). A missing one degrades to a stub with the source `manual` and a test that pins the degradation |
| Lake marts written against silver tables of module types | Module tables are not yet mirrored in silver (P1-I1 follow-up; P1-I8 T08 builds the marts framework); `tl_lake.xer` shows the second-pass pattern | I6 T02 marts read the generated `v_<module>_<class>` views and the readiness events; if P1-I8 T08 is not on the trunk, I6 builds on the `xer_marts.py` pattern and says so |
| Toolcrib screen in I4 | Toolcrib is M4 (brief §9 M4 "Toolcrib mode") over inventory commands | Stays in I4-B (wave 4) as a screen ticket over I3 commands (no new module); it waits for I3 T09c |
| Six sequential increments | I1 and I3 share no module, no schema file and no record type | I1 ∥ I3 and I4 ∥ I5 (§0.2) |

### 0.1 Phase 1 pieces Phase 2 consumes and must verify at phase start

| Consumed | Provider (plan) | If missing at phase start |
|---|---|---|
| RFI record type and its answered state (readiness check "RFIs answered") | P1-I6 T01, T02 (`correspondence` Technical domain) | The check returns `n_a` with a note; the check name is reserved |
| Thread dispatch parser (`/hold`, `/dispatch material-request`) | P1-I7 WS-B T10 | Constraint source `thread_hold` and the MR dispatch wait; demo clause marked deferred |
| Rules engine (constraint source `rule`, the "RFI flags impact → propose constraint" rule) | P1-I7 WS-A T03 | Constraints from rules wait; the manual and check sources carry the demo |
| Inbound endpoints (subcontractor progress by webhook, I5 T10) | P1-I7 WS-A T04 | I5 T10 ships the command and the CSV path only |
| Lake marts framework and silver mirrors of module tables | P1-I8 T08 | I6 T02 uses the `tl_lake.xer` second-pass pattern on the generated views |
| `#hold` hashtag proposal (constraint from a feed post) | P0-I6 (exists: hashtag proposals) | — |
| Cost codes, activity links, look-ahead | P1-I4 (on the trunk since 2026-10-19) | — |

### 0.2 Parallelism plan (3 slots)

The owner wants speed and no usage-limit stalls. The hard cap is **3 slots** (skill rule 6): a supervisor round, a
builder, a security review, a plan check and a ticket workflow are one slot each, and a workflow holds 2–3 items.
Two streams in a wave therefore *alternate*: while stream X's workflow of 2 runs, stream Y gets one supervisor or
builder round; a workflow of 3 runs only while the other stream is idle. Parallel streams buy wall clock, not
throughput, so a wave has at most two streams, chosen so they share no module directory, no schema file and no record
type, with the shared registries (§0.3) owned by one named stream per wave. Each stream has its own branch and
`STATE.md` (`docs/tickets/<INC>/STATE.md`; a fanout's workstreams use `STATE-A.md` and `STATE-B.md`).

| Wave | Streams (alternating rounds) | Why it is safe | Registry owner (merges last) | Security review at wave end | Needs before start |
|---|---|---|---|---|---|
| 0 | Orchestrator alone: plan check of this plan (skill rule 8, findings under §7), freeze `phase2-contracts-draft.md`; one builder piece **W0-B1**: the contract files of `phase2-contracts-draft.md` §1–§5 and §7 as frozen skeletons with their tests, the `awp.*`, `materials.*` and `scaffold.*` keys in `platform.yaml` (one gated change), and the R-P2-3 fix (the API derives `actor_roles` from the principal and refuses a body that carries it, walked over the published API, L-P1-I3-10); owner answers recorded in a Phase 2 decisions ADR (next free number) | — | — | folded into SR1 | P2-Q1 to P2-Q13 answered; the tool tickets of skill Appendix A1–A3 merged (after the Phase 1 exit) |
| 1 | **I1** (awp part 1) ∥ **I3** (materials) | Different modules (`awp`, `materials`), different fixture files; I3 T07 consumes the frozen readiness contract, not awp code | I3 | **SR1**: W0-B1, I1 and I3 `Sec` rows, range `trunk@wave0..` | Wave 0 |
| 2 | **I2** fanout: WS-A (IWP, constraints, sign-off) ∥ WS-B (readiness engine, checks, screens) | WS-B codes against the frozen `ReadinessCheck` contract and the `iwp_facts` reader WS-A commits at C1 | WS-A | **SR2**: I2 `Sec` rows | I1 on trunk; I3 may still be running (its check is found by entry point) |
| 3 | **I4-A** (`requisitions`: engine, four request types, work orders) ∥ **I5** (weekly cycle, rules of credit, progress, pack, closeout) | Different modules; I5 only reads readiness and constraints | I5 merges last | **SR3**: I4-A and I5 `Sec` rows | I2 and I3 on trunk |
| 4 | **I4-B** (`scaffold`, its two checks, toolcrib) ∥ **I6 prep** (T02 marts, T03 report audit as Haiku tickets under the I6 `STATE.md`) | Scaffold consumes the frozen §3 contract and I4-A's merged base; the marts read generated views and readiness events only | I4-B | **SR4**: I4-B `Sec` rows, marts guard | I4-A on trunk; I5 may still be finishing |
| 5 | **I6** (scenario, injections, exit demo) alone; the full parity suite and the capped-mutation sweep of the phase on dedicated time; phase exit | Integrates everything | — | **SR5**: scenario and injection pieces; then the phase-exit review of open `SEC` lines | I4-B and I5 on trunk |

Critical path: I1 → I2 → I4-A → I4-B → I6 (five waves; one more than v0.2 because I4's two workstreams no longer run
beside I5). I5 T01 (the rules-of-credit package) can be drafted in wave 1 because it is a human-gated fixture, not code.
Estimated cost per increment under process v2 (`process-v2.md` §2): 0.15–0.3 B input tokens, against 0.7–1.1 B in Phase 1.

### 0.3 Shared registries that conflict (one owner per wave; the later-merging side regenerates, never hand-merges)

| Registry | File(s) | Rule |
|---|---|---|
| API command table and error rows | `packages/tl-api/src/tl_api/commands.py` (`COMMANDS`), `tl_api/errors.py`, `routes/__init__.py`, generated `docs/reference/openapi.json` | Each module contributes one `<MODULE>_COMMANDS` tuple in its own package; the registry owner adds the one splat line and re-runs `uv run python -m tl_api.openapi` |
| Pinned lists in tests | `packages/tl-schema/tests/test_ddl.py`, `test_generate.py` (table name lists), `tests/webhooks/scenario.py` (`MODULE_STREAMS`), `tests/services/test_modules.py`, `packages/tl-api/tests/test_commands.py`, `test_auth_review.py` (`AGENT_MAY_NOT`), `test_api_proposals.py` (refusal count), `packages/tl-mcp/tests/test_mcp_server.py`, `test_mcp_write_tools.py`, `packages/tl-cli/tests/test_cli_controller_gates.py` | Regenerate the lists with a script (L-P1-I2-6); run `pytest packages/tl-schema packages/tl-api/tests/test_auth_review.py packages/tl-api/tests/test_commands.py tests/contract tests/services/test_modules.py packages/tl-mcp` after every registry change |
| CLI groups | `packages/tl-cli/src/tl_cli/main.py` (`add_typer`) | One group per module (`tl awp`, `tl mat`, `tl req`, `tl scaffold`); one line each |
| TUI client, bindings, key map | `tl_tui/client.py` (`ClientInterface`), `embedded.py`, `remote.py`, the fake, `app.py`, `keymap.py`, palette snapshot | Client methods are added in one supervisor piece per increment before the screen tickets; no new F-keys |
| MCP action and tool lists | `tl_mcp/identity.py` (`MCP_ACTIONS`), `tools.py` and the per-module `<module>_tools.py`, `write_tools.py` | Closed list; add with the tool, run `pytest packages/tl-mcp` before the commit (L-P1-I4-17) |
| Workspace and lock | root `pyproject.toml` (workspace members, module entry points), `uv.lock` | New packages are added by the registry owner; conflicts resolved by `uv lock`, never by hand (FANOUT P1-I3 D8) |
| Fixture packages | `schema/fixtures/standards/co.acme.*`, `schema/fixtures/workflows/*`, `schema/fixtures/co.acme.engineering@3.2.0.yaml` (psets) | One standards edition per module (`co.acme.awp@1.0.0.yaml`, `co.acme.materials@1.0.0.yaml`, `co.acme.requisitions@1.0.0.yaml`); a pset a module needs goes in the module's own package, never in the shared engineering package (L-P1-I3-1) |
| Platform settings | `schema/settings/platform.yaml` | All `awp.*`, `materials.*` and `scaffold.*` keys land in wave 0 (one gated change) |
| Simulator roster | `tl_sim/scenario.py` (`ROLE_NAMES`, `INJECT_EVENTS`), `actors/registry.py` | Added in I6 only; earlier increments ship their actor module under `actors/` and a scenario file, and I6 registers them |
| Generated artefacts | `packages/tl-schema/src/tl_schema/generated/**` | Never merged by hand: the later side runs `just gen` and commits |
| Memory and status | `docs/memory/LEARNINGS.md` (`merge=union`), `docs/reports/STATUS.md` (orchestrator only) | Append only |

### 0.4 Tier rule applied to every increment (process v2)

**Builder pieces (B)**, by `01-tiers.md` §3 and L-P1-I3-5 (a piece other pieces cannot be tested without is built,
not stubbed): every LinkML schema and fixture pattern; every module's `ModuleSpec`, projectors, allow-list and
guards; every command with an access word other than `user`, and every `user` command that moves state; every job
kind; every parser of an uploaded file; every piece that writes money or quantities (movements, adjustments,
rollups, exports); engines. A builder piece also leaves behind the **references** of the Haiku tickets that depend on
it: the reference implementation, the provided test mutation-checked with the sentinel plus ≤ 5 targeted mutants
(L-P1-I4-6, L-P1-I4-16, capped per skill rule 4), the stub, and the test linted in place (L-P1-I3-12). At most 5
pieces per stream; a sixth is a sign the stream should be split.

**Haiku tickets (H)**, once the interface is in the tree: read views and report functions with a provided test; API
read routes and `ApiClient` methods over committed command models; TUI client methods for one increment's reads,
with the fakes changed in the same commit (L-P1-I5-5); one TUI screen from a sketch with a provided test that
mounts only its own screen (L-P1-I3-6); CLI read groups; MCP read tools; readiness-check plugins against the frozen
contract with a provided test; `user`-access mirror commands from a pasted model; simulator actors over an existing
desk; fixture files from a table; Jinja2 templates and renderers over committed read views; demo drivers from a
clause list (`dev/demos/P1-I3.sh` pattern); docs. `review: lite` for pure functions, fixtures, templates, reports
and docs; `full` for anything that touches a route, access, an adapter, a screen, a parser or a job.

**Supervisor glue** per round, ≤ 50 lines: the one `<MODULE>_COMMANDS` splat line, `MCP_ACTIONS` and tool-list
entries that register an already-reviewed command, `add_typer` lines, `just gen` output, held tests restored.

The `01-tiers.md` §6 checklist was run on every H row below: ≤ 6 context files, interfaces in the tree before
dispatch (the B pieces it depends on), a provided test, ≤ 400 lines in ≤ 5 files, no row of the supervisor-tier
table, no `schema/**`, verifiable from the diff and the gate summary.

**Checkpoints** (skill "STATE.md format"), the same four in every increment and named in each section: **C1** schema,
fixtures and module spec merged (the base for the first ticket batch); **C2** write commands, routes, client methods
and registrations merged (screens, tools and reports can go); **C3** every ticket merged or abandoned; **C4** DONE
(full gate, security review, demo, report). `STATE.md` records `C=<k>` in its header; the orchestrator's `STATUS.md`
line names the checkpoint reached when an increment stops early.

**Security review once per wave** (skill rule 4; column `Sec` below marks the pieces): one fresh-context review at
the wave's DONE while the full gate runs, scoped to the wave's `Sec` rows and the commit range since the wave's
base, covering new routes and their access words, every allow-list and guard, every upload slot and parser, every
job claim and settle, every agent tool and proposable command, every reserved identifier, every place a quantity or
an amount is written. Findings become builder pieces or Haiku tickets; one re-check reads the fix commits.

---

## Increment 1 — GC WBS, cost-code mapping, path of construction, CWA, CWP

**Goal:** the `awp` module exists on the seam with its first six record types, its standards edition, its settings
keys, and the allocation rollup from CWP budgets to WBS nodes to cost codes.
**Demo** (`just demo P2-I1`, SQLite and Postgres, one `PASS` per clause): (1) an admin loads `co.acme.awp@1.0.0`
(patterns, code lists); loading twice changes nothing; (2) a WBS of 12 nodes is imported from a CSV preview and
applied, each node linked to a `cost.CostCode` by `references`, with allocation percentages that sum to 100 per
node; a row that sums to 101 is refused in the preview; (3) a path of construction of 4 CWAs is defined and
re-sequenced, both versions readable; (4) 6 CWPs are created with numbers from the pattern (`P123-CWP-PIP-0001`),
linked to CWAs (`belongs_to`), WBS nodes with allocation, two `EWPRef` mirrors with forecast dates and the
`constraint_source` flag, and to activities of the `p1/i4` demo schedule with `LinkActivity`; (5) the rollup job
runs and `tl awp report wbs-vs-cost` shows budget hours per cost code; a second CWP budget moves the figures and
the ledger holds both runs; (6) a user cannot define the path or change allocations (admin acts); an agent's
`propose_cwp` waits for a person; (7) the API, the TUI (CWP register, WBS tree) and the MCP read tools show the
same CWP.
**Seams:** ADR-0010 module; `LinkActivity`; `cost.CostCode` by `references`; `allocate_key`; the job runner;
`platform.yaml` keys.
**Fanout:** no. Wave 1, alternating with I3. `STATE.md`: `docs/tickets/P2-I1/STATE.md`.
**Builder pieces (3):** B1 schema and fixture patterns (T02 and T01's pattern part); B2 module spec, projectors,
allow-lists and guards, the write commands with their access words (T03), the WBS CSV reader in the envelope with
preview and apply, and the references and provided tests of T04, T07a and T07c; B3 the allocation rollup job (T05).
The `platform.yaml` keys land in wave 0 (W0-B1). Registrations are supervisor glue.
**Checkpoints:** C1 = B1, B2 merged; C2 = B3, T07a merged; C3 = T04, T06a–b, T07b–c, T08a merged; C4 = T08b
demo green on both adapters, SR1 closed.

| ID | Title | Tier | Depends | Sec |
|---|---|---|---|---|
| T01 | Fixtures: `co.acme.awp@1.0.0.yaml` code lists (constraint types, CWA sequence reasons), sample WBS and CWA CSVs (the patterns `CWP`, `IWP`, `CON` are B1) | H lite | B1 | — |
| T02 | LinkML `schema/modules/awp/`: `WBSNode`, `PathOfConstruction`, `CWA`, `CWP`, `EWPRef`, `PWPRef`; CWP workflow fixture (Planned → In development → Released for IWP development → Executing → Complete → Closed) | B1 | — | schema |
| T03 | Commands `DefineWbsNode`, `MapWbsToCostCode` (allocation %, sums to 100), `DefinePathOfConstruction`, `ResequencePath`, `DefineCwa`, `CreateCwp`, `UpdateCwp`, `LinkCwpScope`; access: WBS and path are `admin` (cost control, P2-Q12), CWP and CWA `user`; projectors; WBS CSV import preview and apply | B2 | B1 | routes, access, parser |
| T04 | `EWPRef` / `PWPRef` mirror commands (`RecordExternalPackage`, `UpdateExternalPackageDates`, `user`) from the pasted models, with the `constraint_source` flag; read views | H full | B2 | — |
| T05 | Allocation rollup: job kind `awp.rollup` (bounded runs, state-derived), `CWP.BudgetRolledUp` event, `cur_awp_wbs_rollup`; export view by cost code | B3 | B2 | job, money |
| T06a | TUI: CWP and CWA registers (grid over the client) | H full | T07a | — |
| T06b | TUI: WBS tree and path-of-construction sequence editor (calls `ResequencePath`) | H full | T07a | — |
| T07a | API read routes for WBS, path, CWA, CWP from the B2 command models, their `ApiClient` and TUI client methods (fakes in the same commit), tests | H full | B2 | routes (read) |
| T07b | MCP read tools `list_cwps`, `get_cwp`, `wbs_tree`, `path_of_construction` (registration is glue) | H full | T07a | agent (read) |
| T07c | Reports `cwp_status`, `wbs_vs_cost_code` (`tl awp report`) | H lite | B3 | — |
| T08a | Simulator `workface_planner` actor desk (creates CWPs from a template) | H lite | T07c | — |
| T08b | `dev/demos/P2-I1.sh` from the clause list above (`P1-I3.sh` pattern; both adapters) | H full | T08a | — |

---

## Increment 2 — IWP, constraints, readiness, release sign-off

**Goal:** an IWP with scope, pinned documents, constraints with need-by dates and owners, a readiness engine of
plug-in checks, release by sign-off, issue to a foreman, and the `IWP.Ready` webhook.
**Demo** (`just demo P2-I2`): (1) an IWP is built from 24 scope items (generic `awp.ScopeItem` records, P2-Q7),
8 more and 3 tags, all `contains` links, numbered `P123-IWP-PIP-0042`; (2) two drawings are pinned; issuing a new
IFC revision of one makes the documents check `blocked` with the stale pin as `resolve_via`; (3) constraints are
raised by hand and by the materials check (if I3 is merged) with need-by = planned start − `awp.iwp.ready_lead_weeks`;
the review screen groups them by owner and type; (4) the readiness screen shows 5/7 with the blocked checks named;
re-pinning and clearing the constraints turns it 7/7 and `IWP.Ready` is delivered to a loopback receiver;
(5) sign-off needs two distinct signers with the access of P2-Q2; a user's sign-off is refused; the second signer
cannot be the first; a `SignOffIwp` with a wrong record hash is refused; (6) issue to a foreman moves the IWP to
Issued and the expected link `permit-to-work` (`tl:expects_link`, `n_a` until a permit record exists) is reported
as missing, not blocking (P2-Q8); (7) an oversize IWP (hours over `awp.iwp.size_hours`) warns and the split tool
makes two; (8) an agent proposes a constraint and a person accepts it; (9) the same state over the API, the TUI and
MCP; the readiness history is in the ledger and the dashboard tile shows backlog weeks per foreman.
**Seams:** `generic_guards` (an Issued IWP takes no scope change), `expects_link`, `by_module` for check-raised
constraints (source `rule`), job kind `awp.readiness`, `IWP.ReadinessEvaluated` event, the readiness entry point,
webhooks (`IWP.Ready` is in the catalog from the module's `tl:event_type` class).
**Fanout (orchestrator):** WS-A IWP, constraints, sign-off (owner of the merge); WS-B readiness engine, checks,
screens, tile. Contract: `tl_core/readiness/types.py` (`phase2-contracts-draft.md` §1), frozen before the fanout;
WS-A commits `tl_mod_awp.facts.iwp_facts(conn, iwp_id)` (the `IwpFacts` reader) first.
**Builder pieces (WS-A 4, WS-B 2):** WS-A: B1 schema part 2 with the `IWP.Ready` event class (T01) and the
`iwp_facts` reader; B2 IWP commands and guards (T02); B3 constraint commands (T03); B4 sign-off, issue and hold
(`SignOffIwp`, `IssueIwp`, `HoldIwp`, `ReleaseHold`: access per P2-Q2; distinct signers; the record hash in the
signature event) and the references of T04a, T09a and T09b. WS-B: B5 the readiness engine (T05); B6 the
`documents_current` and `rfis_answered` checks (T06a) and the references of T06b, T07a–b and T08. Routes and client
methods are T04c; registrations are glue; the simulator desk is T10a. `STATE-A.md`, `STATE-B.md`.
**Checkpoints:** C1 = B1 merged (WS-B starts), B5 merged; C2 = B2–B4, B6, T04c merged; C3 = all H rows merged;
C4 = T10b demo green, SR2 closed.

| WS | ID | Title | Tier | Depends | Sec |
|---|---|---|---|---|---|
| A | T01 | LinkML `awp` part 2: `IWP`, `Constraint`, `IWPCloseout`, `ScopeItem` (P2-Q7); IWP workflow with side states (Draft → In development → Constraint check → Ready → Issued → In progress → Field complete → Closed; On hold, Split, Cancelled); `tl:expects_link` permit-to-work at Issued; `iwp_facts` reader | B1 | — | schema |
| A | T02 | IWP commands: `CreateIwp`, `AddIwpScope` / `RemoveIwpScope` (`contains`), `PinIwpDocument`, `SplitIwp` (by scope items or hours); guards per state; sizing warning from `awp.iwp.size_hours` | B2 | B1 | guards |
| A | T03 | Constraint commands: `RaiseConstraint` (sources `manual`, `rule`, `feed_hold`, `thread_hold`, `check`; need-by from the setting; owner required), `AssignConstraint`, `ClearConstraint` (resolving record link `resolves`), aging; `blocks` link to the IWP | B3 | B1 | by_module sources |
| A | T04a | `cur_awp_constraint` read views: by owner, by type, by age; `tl awp constraint ls|show` | H lite | B3 | — |
| A | T04b | TUI constraint review screen grouped by owner and type | H full | T04c | — |
| A | T04c | API read routes for IWP, constraints and readiness from the B2–B5 models; `ApiClient` and TUI client methods with the fakes; tests | H full | B2–B5 | routes (read) |
| B | T05 | Readiness engine: `tl_core/readiness/` registry (entry point `throughline.readiness_checks`), job kind `awp.readiness` (one IWP per run, bounded `resolve_via`), event `IWP.ReadinessEvaluated`, projector `cur_awp_readiness`, `IWP.Ready` on the first all-green evaluation, re-evaluation requests from link, pin and constraint events | B5 | contract, B1 | job, event |
| B | T06a | Checks `documents_current` (stale pins via `tl_mod_documents.resolver`) and `rfis_answered` (P1-I6 type) | B6 | B5 | — |
| B | T06b | Checks `permits_planned`, `inspections_planned`, `labour_requested`, `predecessors_handed_over`, `model_slice_available` returning `n_a` with a fixed note, each with its test and name reserved | H lite | B5 | — |
| B | T07a | TUI readiness screen (sketch §10.6 no. 5): checks, counts, `resolve_via` jump | H full | T04c | — |
| B | T07b | TUI IWP record view tabs (scope, documents, constraints, readiness, history) | H full | T04c | — |
| B | T08 | Sizing warning surface and the backlog-weeks-per-foreman dashboard tile (`awp.backlog.target_weeks`) | H full | B5, T04c | — |
| A | T09a | Reports: IWP status, readiness and constraint log, constraints by type, owner and age (`tl awp report`) | H lite | T04a, B5 | — |
| A | T09b | MCP read tools `get_iwp`, `iwp_readiness`, `list_constraints`; proposable `propose_constraint` (`user`) and `propose_iwp_scope` from the B3 models (registration is glue) | H full | T04c | agent |
| A | T10a | Simulator desk and `workface_planner` actor: builds IWPs, raises and clears constraints | H lite | T09a | — |
| A | T10b | `dev/demos/P2-I2.sh` from the clause list (both adapters) | H full | T10a | — |

Merge order: A B1 → B B5 → A B2–B4 ∥ B B6 → A T04c → the H rows in dependency order. A owns conflicts.

---

## Increment 3 — M4 item library, inventory, receipts

**Goal:** the `materials` module: a company item library, project items, locations, receipts with heat numbers and
MTRs, ledgered movements whose projection is stock on hand, reservations against IWPs, and the materials readiness
check.
**Demo** (`just demo P2-I3`): (1) an admin loads `co.acme.materials@1.0.0` (categories, UOMs, location kinds) and
imports an item library of 50 items from a CSV (preview, apply); a user cannot; (2) a location tree company →
warehouse → project → laydown → toolcrib → gang box; (3) a receipt of 2 flanges with heat number `H-7781` and an
MTR in the slot `mtr`; accepting the receipt without the MTR is refused; (4) issue to a crew against a cost code,
transfer to the laydown, return of one, an adjustment with a reason (admin); stock by location is the sum of the
movements and a projection rebuild gives the same figures on both databases; (5) heat traceability: the flange
lot → receipt → MTR; (6) an MTO derived document (P1-I3 pipeline, schema `mto`) is published into `MTOLine`
records linked to a CWP; compensation takes them back; (7) a reservation against an IWP (I2 on the trunk: the
materials readiness check turns `ok`; else the reservation view alone) and a shortage report against IWPs;
(8) the same stock over the API, the TUI (item library, stock by location, receipt entry, movement log) and MCP;
(9) a movement with a non-ASCII digit, a negative receipt or a quantity over the bound is refused with a fixed
message.
**Seams:** module records; movements as events on the lot stream with typed references (P2-Q5); `PublishMapping`
`target_kind: mto`; the envelope for the item-library CSV; file slot `mtr`; the readiness entry point; `cost.CostCode`
by `references`.
**Fanout:** no. Wave 1, alternating with I1; merges after I1 (registry owner). `STATE.md`: `docs/tickets/P2-I3/STATE.md`.
**Builder pieces (4):** B1 schema and fixture patterns (T02, T01's patterns); B2 module spec, projectors including
the inventory projection (T04: stock per lot and location from movement events, heat columns, rebuild equality on
both adapters), allow-lists, and the references of T07, T09a–b and T10a; B3 movement commands (T03) and receiving
acceptance with the MTR slot guard (T06); B4 the item-library and MTO readers in the envelope and `PublishDerivedMto`
(T05). Routes and client methods are T09c; registrations are glue.
**Checkpoints:** C1 = B1, B2 merged; C2 = B3, B4, T09c merged; C3 = all H rows merged; C4 = T11b demo green, SR1 closed.

| ID | Title | Tier | Depends | Sec |
|---|---|---|---|---|
| T01 | Fixtures: `co.acme.materials@1.0.0.yaml` code lists (item categories, location kinds, condition codes, movement reasons), sample item library and location CSVs (patterns `RCPT`, `MTO` are B1) | H lite | B1 | — |
| T02 | LinkML `schema/modules/materials/`: `ItemMaster`, `CatalogItem`, `ProjectItem`, `MTO`, `MTOLine`, `POLineRef`, `Receipt` (slot `mtr`), `StockLot`, `SerializedItem`, `Equipment`, `InventoryLocation`; movement event classes; receipt workflow (Received → Inspected → Accepted / Rejected) | B1 | — | schema |
| T03 | Movement commands `Receive`, `Issue`, `Transfer`, `Return`, `Adjust` (admin), `Scrap` (admin), `Reserve`, `Unreserve` (quantities as deltas, decimal with UOM); `cur_materials_movement`; cost-code posting of consumables; `AcceptReceipt` guarded by the `mtr` slot for permanent materials, inspection hook as an expected link (T06) | B3 | B2 | money, guard, slot |
| T04 | Inventory projection: `cur_materials_stock` (lot × location), serialized items, heat traceability columns; rebuild equality test on both adapters | B2 | B1 | — |
| T05 | MTO publication: `PublishMapping` `target_kind: mto`, `PublishDerivedMto` (`controller`), compensation through the recorded ids; `tl derive publish` picks the command by kind; item-library and MTO readers in the envelope | B4 | B3 | import, parser |
| T06 | (folded into B3) | — | — | — |
| T07 | Readiness check `materials_reserved` (reservation rows against MTO lines of the IWP) against the frozen contract, registered under `throughline.readiness_checks`; provided test from the B2 reference | H full | B2 | — |
| T08a | TUI item library and stock-by-location screens | H full | T09c | — |
| T08b | TUI receipt entry form and movement log | H full | T09c | — |
| T09a | CLI `tl mat item|stock|lot|move` reads | H lite | B2 | — |
| T09b | Company-level aggregation views (equipment by project, surplus by item) and `tl mat report equipment|surplus` | H lite | B2 | — |
| T09c | API read routes from the B3–B4 models; `ApiClient` and TUI client methods with the fakes; tests | H full | B3, B4 | routes (read) |
| T10a | Reports: stock on hand, MTO vs received vs issued, shortages against IWPs, heat traceability | H lite | B2 | — |
| T10b | MCP read tools (`stock_on_hand`, `get_lot`, `heat_trace`, `mto_status`); proposable `propose_reservation` (`user`) from the B3 model (registration is glue) | H full | T09c | agent |
| T11a | Simulator `materials_coordinator` desk and actor (receipts with MTRs, reservations) | H lite | T10a | — |
| T11b | `dev/demos/P2-I3.sh` from the clause list (both adapters) | H full | T11a | — |

---

## Increment 4 — M9 requisitions and work orders, scaffold, toolcrib

**Goal:** the generic request → work order engine in the `requisitions` module with its four specialisations, the
`scaffold` module (asset lifecycle, tag colour, inspection due list, dismantle check), the scaffold and labour
readiness checks, and the toolcrib fast-entry screen over I3 commands.
**Demo** (`just demo P2-I4`): (1) a material requisition `requires` an IWP; its approval (P2-Q3) turns it into a
work order and its fulfilment posts movements through the I3 commands; a thread `/dispatch material-request`
creates it when P1-I7 WS-B is on the trunk (else the clause says `deferred`); (2) a scaffold request for the IWP
becomes a scaffold asset Requested → Designed → Erecting → Inspected and tagged green; the scaffold readiness
check turns `ok`; the tag turns red on a failed inspection and the check turns `blocked`; (3) the inspection due
list from the interval setting; a dismantle request is refused while an open IWP still uses the scaffold;
(4) a labour requisition of 6 pipefitters for two weeks; the forecast by craft and week; the labour check turns
`ok`; (5) a general requisition (crane lift) with a type-specific pset; (6) the toolcrib screen issues a tool to a
person and takes it back in one line each, keyboard only; (7) `requisitions` numbering is gap-free per kind under
two concurrent creators (the writer lock); (8) the same over the API, the TUI (scaffold register, requisition and
work order screens) and MCP.
**Seams:** two new modules; approval as module commands with access words; the readiness entry point; I3 movement
commands called by the material requisition fulfilment (`tl_mod_materials` imported by `tl_mod_requisitions`: the
first module-to-module import, recorded in the contract); `allocate_key`; the job runner for the inspection due
list.
**Fanout (orchestrator), in two waves:** **I4-A** `requisitions` (engine, all four request types, work orders;
owner of the merge) runs in wave 3 beside I5; **I4-B** `scaffold` (asset lifecycle, inspections, register screen,
readiness checks) and the toolcrib screen run in wave 4 beside the I6 prep tickets. Contract:
`phase2-contracts-draft.md` §3 (the `Requisition` and `WorkOrder` LinkML base, the events I4-B consumes, the
`open_requisitions_for(conn, record_id)` view). `STATE-A.md`, `STATE-B.md`.
**Builder pieces (A 3, B 2):** A: B1 schema (T01); B2 engine (T02: numbering per kind, approval chain, scheduling,
assignment, closeout) and the references of T04a and T08a; B3 the labour and material specialisations with the
fulfilment into I3 movements (T04b). B: B4 scaffold schema and lifecycle (T03: tag colour rules, dismantle check)
and the job kind `scaffold.inspections_due`; B5 none planned (the two checks are T05, Haiku against the frozen
contract). Routes and client methods are T09a (A) and T09b (B); registrations are glue.
**Checkpoints:** A: C1 = B1 merged; C2 = B2, B3, T09a merged; C3 = T04a, T07b, T08a–b merged; C4 = T10 demo
clauses 1, 4, 5, 7, 8 green, SR3 closed. B: C1 = B4 merged; C2 = T09b merged; C3 = T05, T06, T07a merged; C4 = T10
clauses 2, 3, 6 green, SR4 closed.

| WS | ID | Title | Tier | Depends | Sec |
|---|---|---|---|---|---|
| A | T01 | LinkML `schema/modules/requisitions/`: `Requisition` (abstract), `WorkOrder`, `LaborRequisition`, `MaterialRequisition`, `GeneralRequisition`, `ScaffoldRequest`; workflows (Requested → Approved → Scheduled → In progress → Done → Closed; Rejected, Cancelled) | B1 | contract | schema |
| A | T02 | Generic engine: `RaiseRequisition`, `ApproveRequisition` (access per P2-Q3), `RejectRequisition`, `ScheduleWorkOrder`, `AssignWorkOrder`, `CompleteWorkOrder`, `CloseWorkOrder`; numbering per kind; guards | B2 | B1 | access |
| B | T03 | LinkML `schema/modules/scaffold/`: `Scaffold` asset, `ScaffoldInspection`; lifecycle (Requested → Designed → Erecting → Inspected/Tagged Green → In Use → Modify → Dismantle → Removed); tag colour; `DismantleScaffold` refuses while an open IWP `requires` it; job `scaffold.inspections_due` | B4 | contract, I4-A on trunk | guard, job |
| A | T04a | Labour requisition forecast by craft and week (view and report) | H lite | B3 | — |
| A | T04b | Material requisition fulfilment: approved lines → `Issue` movements (I3), partial fulfilment, shortage back to the constraint owner; the labour and material specialisations | B3 | B2 | money |
| B | T05 | Readiness checks `scaffold_tagged` (green tag on every scaffold the IWP `requires`) and `labour_requested` (an approved labour requisition covers the window) against the frozen contract, provided tests from the B4 and B3 references | H full | B4 | — |
| B | T06 | Toolcrib issue and return fast-entry screen (§10.5) over the I3 `Issue` and `Return` commands, serial or item, person, qty, keyboard only | H full | I3 T09c | — |
| B | T07a | TUI scaffold register (status, tag colour, inspection due) and scaffold record view | H full | T09b | — |
| A | T07b | TUI requisition and work order screens; dispatch wiring from threads (P1-I7 parser) | H full | T09a | — |
| A | T08a | Reports: open requisitions, quantities on hire, labour forecast, work order backlog (the scaffold register report moves to B T07a) | H lite | T04a | — |
| A | T08b | MCP read tools; proposable `propose_requisition` (`user`) from the B2 model (registration is glue) | H full | T09a | agent |
| A | T09a | API read routes from the B2–B3 models; `ApiClient` and TUI client methods with the fakes; tests | H full | B2, B3 | routes (read) |
| B | T09b | API read routes from the B4 models; client methods with the fakes; tests | H full | B4 | routes (read) |
| B | T10 | Simulator `scaffold_supervisor` actor (desk from the contract §6); `dev/demos/P2-I4.sh` (A's clauses are added by A's T08b report, B's by this ticket; both adapters) | H full | T08b, T07a | — |

Merge order: wave 3: A B1 → B2 → B3 ∥ T09a → T04a, T07b, T08a–b. Wave 4: B B4 → T09b → T05 ∥ T06 ∥ T07a → T10. A owns conflicts in wave 3, B in wave 4.

---

## Increment 5 — Weekly workface planning cycle, rules of credit, progress, IWP pack, closeout

**Goal:** the six-step weekly cycle over the P1-I4 look-ahead and the I2 readiness, earned progress from linked
record states through a company rules-of-credit package, the rollup IWP → CWP → WBS → cost code with a CSV
export, the printable IWP pack, closeout with feedback, and the KPIs.
**Demo** (`just demo P2-I5`): (1) the rules-of-credit package `co.acme.awp-roc@1.0.0` (P2-Q1) loads: scope item
steps 30/60/10; a package whose weights do not sum to 100 is refused; (2) a new XER snapshot (`tl xer`, `p1/i4`)
is published and the look-ahead screen lists the activities of the next four weeks with their IWPs and readiness;
(3) constraint review, then release of the Ready IWPs (sign-off, I2); (4) foreman commitments for the week;
(5) progress: scope items move state, earned % per IWP follows the rules, PPC is computed from commitments; the
rollup job writes earned quantities per CWP and WBS node and `tl awp export progress --period 2026-W43` writes the
CSV by cost code; (6) the IWP pack renders (HTML always; PDF when the dependency of P2-Q11 is allowed) with cover,
scope, drawings with QR deep links, MTO, safety and quality placeholders, permits, scaffold tags and the sign-off
sheet; (7) closeout: actual hours CSV (envelope), redlines slot, remaining punch count, feedback text; the KPIs
(backlog weeks, % constraint-free, constraint aging, schedule compliance, PPC, earned vs burned, stale-pin issues)
agree with the ledger on both databases; (8) a CWP assigned to a subcontractor party records progress through
`RecordSubcontractProgress` (CSV; inbound webhook mapping when P1-I7 WS-A exists).
**Seams:** standards loader pattern for the package; `look_ahead` and `resolve_activity`; `cur_awp_readiness`;
job kind `awp.rollup`; the envelope for the hours CSV; file slots `pack`, `redlines`; `cost.CostCode` figures are
read, never written.
**Fanout:** no. Wave 3, alternating with I4-A; merges after I4-A. `STATE.md`: `docs/tickets/P2-I5/STATE.md`.
**Builder pieces (5):** B1 the package schema and loader (T01, human gate); B2 the rules-of-credit engine (T02);
B3 the progress rollup and export (T03); B4 the `WeeklyPlan` commands (commitments, PPC), the `LookAhead` read
and the `RecordSubcontractProgress` command with party assignment (T05, T04, T10 write sides) and the references
of T04, T05, T09; B5 closeout commands with the actual-hours reader in the envelope (T08 write side) and the
references of T07a. The pack renderer is Haiku (T07a: a renderer over committed read views and repository
templates); routes and client methods are T11; registrations are glue.
**Checkpoints:** C1 = B1, B2 merged; C2 = B3–B5, T11 merged; C3 = all H rows merged; C4 = T12 demo green, SR3 closed.

| ID | Title | Tier | Depends | Sec |
|---|---|---|---|---|
| T01 | `RulesOfCredit` package: LinkML class, `co.acme.awp-roc@1.0.0.yaml` with scope item, weld and bolted joint examples, loader `tl awp roc load`, weights sum to 100 (human gate) | B1 | — | schema |
| T02 | Rules-of-credit engine: `earned_fraction(conn, iwp_id)` from linked record states; manual entry for commodities without records; `IWP.ProgressRecorded` | B2 | B1 | — |
| T03 | Progress rollup IWP → CWP → WBS → cost code (job `awp.rollup` shared with I1 T05) and `tl awp export progress` (CSV, period, reserved source prefix) | B3 | B2 | money, export |
| T04 | `LookAhead` read: `look_ahead` joined with `cur_awp_readiness` and constraints; `tl awp look-ahead`; view (the read is B4's reference) | H lite | B4 | — |
| T05 | `WeeklyPlan` reads and CLI: `tl awp week commit|ppc` over the B4 commands; miss reasons view | H lite | B4 | — |
| T06a | TUI weekly cycle steps 1 to 3 (load snapshot, constraint review, release) | H full | T11 | — |
| T06b | TUI weekly cycle steps 4 to 6 (commitments, progress and PPC, closeout) | H full | T11 | — |
| T07a | IWP pack renderer: data assembly over the committed read views, Jinja2 → HTML, deep links from `api.public_base_url`, PDF behind the P2-Q11 flag; stored in slot `pack`; templates are repository files, never uploaded | H full | T11 | template input |
| T07b | IWP pack template: cover, scope and steps, drawing list with QR, MTO, safety, ITP placeholder, permits, scaffold tags, sign-off sheet; snapshot test | H lite | T07a | — |
| T08 | Closeout reads: `redlines` slot view, remaining punch, feedback, `IWPCloseout` register and `tl awp closeout show` (writes and the hours reader are B5) | H lite | B5 | — |
| T09 | KPIs as reports and dashboard tiles: backlog weeks, % constraint-free, constraint aging, schedule compliance, PPC, earned vs burned, IWPs issued with stale pins | H lite | B3, B4 | — |
| T10 | Subcontracted scope reads: party assignment views, interface constraints report, `tl awp subcontract` reads (the command is B4; inbound mapping when available) | H lite | B4 | — |
| T11 | API read routes from the B2–B5 models; `ApiClient` and TUI client methods with the fakes; MCP read tools; tests | H full | B2–B5 | routes (read), agent |
| T12 | `dev/demos/P2-I5.sh` from the clause list (both adapters) | H full | T06b, T07a, T09 | — |

---

## Increment 6 — Simulation, lake marts, reports, Phase 2 exit

**Goal:** the Phase 2 actors and fault injections in one scenario, the gold marts, the §12 report audit, and the
phase-exit demo on a simulated project.
**Demo** (`just demo P2-I6`, the phase exit): on `refinery-piping-medium` v2 (seeded, deterministic): (1) the
planner builds CWPs and IWPs, the materials coordinator receives and reserves, the scaffold supervisor erects and
tags, an operator signs off; `sim_assert` passes with the Phase 2 operators listed; (2) the `material_late`
injection delays a receipt by 21 days: the materials check goes `blocked`, a constraint appears with the receipt
as `resolve_via`, the IWP goes On hold, and clears when the receipt lands; (3) an IWP is issued with documents,
materials and scaffold `ok` (the §16 exit), on SQLite and Postgres; (4) `tl lake sync` loads the marts and
`lake_query` answers the readiness history of that IWP and the schedule trend against readiness with the ledger
`seq` it covers; (5) every §12 M3, M4 and M9 base report runs from the CLI and the API with a non-empty result.
**Fanout:** no. T02 and T03 run in wave 4 as I6 prep (under `docs/tickets/P2-I6/STATE.md`, beside I4-B); the rest
is wave 5 alone.
**Builder pieces (2):** B1 the injection semantics (`material_late` as a late receipt, `scaffold_failed`,
`design_revision` against pinned IWP drawings) and the scenario references; B2 the marts sync pass (rebuild equals
incremental, property-tested as the lake is) and the SQL model references. The exit demo is Haiku from the clause list.
**Checkpoints:** C1 = B2 merged (wave 4); C2 = B1 merged (wave 5); C3 = T01–T03 merged; C4 = T04 green on both
adapters, SR5 closed, the phase-exit review of open `SEC` lines done.

| ID | Title | Tier | Depends | Sec |
|---|---|---|---|---|
| T01 | Scenario `refinery-piping-medium` v2: `ROLE_NAMES` gains `workface_planner`, `materials_coordinator`, `scaffold_supervisor`, `foreman`; injections `material_late` (real), `scaffold_failed` wired to B1; operators for sign-off and issue | H full | B1 | — |
| T02 | Lake gold marts as SQL models over the B2 sync pass: `mart_iwp_readiness_history` (from `IWP.ReadinessEvaluated`), `mart_materials` (stock and movements by period), `mart_schedule_vs_readiness` (activity dates against readiness per snapshot) | H full | B2 | lake guard |
| T03 | Base reports audit against §12 for M3, M4 and M9: one row per report with its command and route; gaps filed as draft tickets | H lite | I5 on trunk | — |
| T04 | Phase-exit demo `dev/demos/P2-I6.sh` (clauses above, both adapters) | H full | T01, T02 | — |
| T05 | Phase report, risk register, `LEARNINGS.md` curation, ADRs; the full parity suite and the capped-mutation sweep of the phase on dedicated time (orchestrator) | O | T04 | — |

---

## 7. Plan check (skill rule 8)

Pending. Before wave 1 the orchestrator spawns `plan-check` on this file and on `phase2-contracts-draft.md` and
records each finding here as `F<n> <sev> <section>: <answer | waived: reason>`. Nothing is dispatched until this
section is filled. v0.3 points the check should weigh first: the five-wave shape against four (§0.2); T07a of I5
and T05 of I4-B as Haiku rather than builder work; T04c, T09c, T09a–b and T11 (routes plus client methods plus fakes)
against the ≤ 5-file rule; the I2 piece count (6 across two workstreams).
