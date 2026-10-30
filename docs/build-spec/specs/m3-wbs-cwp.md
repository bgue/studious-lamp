# Spec — M3 part 1: GC WBS, cost-code allocation, path of construction, CWA, CWP (P2-I1)

Status: v0.1, 2026-10-30, spec for builders and implementers. Design: `module-designs/field-work-packaging.md`.
Plan: `08-phase2-plan.md` I1 (wave 1, alternating with P2-I3). Owner decisions: `module-designs/OWNER-DECISIONS-2026-10-30.md`.
Depends on: Phase 2 wave 0 (W0-B1: frozen contracts, reserved prefixes `rollup:` and `job:`, R-P2-3 fix); the core
specs written beside this one: **roles** (access words → per-module `viewer`/`user`/`superuser`, per project),
**offline** (where the class is declared and checked), **web** (how the web client renders logs and record screens).
Phase 2 contracts used: `phase2-contracts-draft.md` §5 (rollup events, `cur_awp_rollup`), §6 (`AwpDesk`), §7.

## 1. Objective and user stories

The `awp` module exists on the ADR-0010 seam with six record types, the CWP workflow, imports through the legacy
loader framework, and the budget rollup CWP → WBS node → cost code. Out of scope (P2-I2 and later): IWP, scope items,
constraints, readiness, rules of credit, progress, weekly cycle.
- **Cost controller (awp superuser):** I load the GC's WBS from a spreadsheet, allocate each leaf node to cost codes
  in percent, and see budget hours per cost code beside the cost system's figures.
- **Area manager (awp superuser):** I set the path of construction as an ordered list of CWAs, re-sequence it with
  a reason, and read any two versions side by side.
- **Workface planner (awp user):** I create CWPs numbered from the pattern, set CWA, dates, budget hours and
  quantities, allocate them to WBS nodes, link the engineering and procurement packages and the schedule
  activities, and move the CWP through development; a superuser releases it for IWP development.
- **Anyone with awp viewer:** the CWP register, the WBS tree and the path read the same over TUI, web, API and MCP.

## 2. Record types

All project scope (`project:<P>`), confidentiality `internal`, no `ConfidentialSource` (every read still goes through
the viewer filter of `cur_core_record` and of links: a linked restricted document stays hidden). Schema in
`schema/modules/awp/{module,wbs,path,cwa,cwp,external_package,rollup,events}.yaml`; every record class carries
`tl:current_state` and `tl:record_types`; child tables are non-record classes (as `cost.CostSnapshotValue`).
Envelope `title` = name or subject; `key` as below. Decimals are text in events (`"1250.0"`), `Decimal` in Python,
ASCII digits only (`tl_core/text.py` checks); dates `YYYY-MM-DD`.

| Type | Key | Typed fields (table) | States | Offline (reason) |
|---|---|---|---|---|
| `awp.WBSNode` | typed `code` (`^[A-Z0-9][A-Z0-9.\-]{0,31}$`, unique per project) | `cur_awp_wbs_node`: `code`, `parent_id` (WBSNode, null at root), `depth` (0..7), `position` (int), `retired` (bool) | none (Active, Retired flag) | `none`: cost-control data whose percentages must sum across nodes; edited centrally |
| child | — | `cur_awp_wbs_allocation`: `node_id`, `cost_code_id` (`cost.CostCode`), `percent` (`"40.00"`) | — | — |
| `awp.PathOfConstruction` | module-built `P123-POC` (`composed_key=True`), one per project | `cur_awp_path`: `current_version`; child `cur_awp_path_step`: `path_id`, `version`, `position`, `cwa_id`, `reason_code`, `actor`, `recorded_at` (every version kept) | none | `none`: one sequence per project; concurrent offline edits cannot merge meaningfully |
| `awp.CWA` | typed `code` (same rule as WBS) | `cur_awp_cwa`: `code`, `location_text` (≤ 200), `retired` | none | `none`: area list is set up once by the office |
| `awp.CWP` | allocator `P123-CWP-PIP-0001`: `{project}-{type}-{discipline}-{seq:4}`, `type_code: CWP`, gap-free, counts per discipline | `cur_awp_cwp`: `discipline` (code list `Discipline`), `cwa_id`, `planned_start`, `planned_finish`, `budget_hours` (1 dp, 0..10 000 000), `quantities_json` (≤ 50 rows `{commodity, qty, uom}`; `Commodity`, `UnitOfMeasure` lists), `contractor_text` (≤ 120); child `cur_awp_cwp_allocation`: `cwp_id`, `wbs_node_id`, `percent` | workflow `awp-cwp.yaml` (below) | `draft_only`: a planner may draft in a site office; number, release and close are central |
| `awp.EWPRef`, `awp.PWPRef` | typed owner package number (unique per type and project) | `cur_awp_ewp_ref` / `cur_awp_pwp_ref`: `package_no`, `status_text` (≤ 40), `forecast_date`, `actual_date`, `constraint_source` (bool; read by P2-I2), `source_system` (≤ 40) | none (mirror) | `none`: mirror of the owner's system |
| rollup table | — | `cur_awp_rollup`: `scope`, `subject_kind` (`wbs_node`), `subject_id`, `line` (`total`, `cost_code`, `unallocated`), `cost_code_id` (set only on `cost_code` lines), `measure` (`budget_hours`; P2-I5 adds `earned_hours`), `value`, `as_of_seq`, `run_id` | — | — (server job only) |

Offline: each class carries `tl:offline` and `tl:offline_reason` as the offline core spec defines; if that spec
chooses a `ModuleSpec` field instead, the same table moves there. Nothing in P2-I1 runs offline (Phase 3 I5).

**CWP workflow** (`schema/fixtures/workflows/awp-cwp.yaml`, no `roles` guard, every move by a module command with
`handle_transition_workflow(..., by_module=True)`): Planned → In development → Released for IWP development →
Executing → Complete → Closed; Released → In development (return); Complete → Executing (reopen); any state but
Closed → Void (a module void, `Record.Voided`). `expected_links` at Released: `awp.EWPRef` by `requires` (reported
missing, never blocking).

**Rules the handlers enforce** (fixed messages, no cell text): WBS depth ≤ 8, ≤ 5 000 nodes per project; allocation
only to leaf nodes (a node with children has none; giving a leaf a child is refused while it has allocations or CWP
allocations); allocation lists ≤ 20 rows, each `0.01..100.00`, no repeated target, sum exactly `100.00`; a cost
code must exist in the project; a retired node or CWA takes no new allocation or CWP; path ≤ 500 steps, every
non-retired CWA at most once; `planned_finish ≥ planned_start`; CWP fields frozen from Released (only `ReturnCwp`
reopens them); release needs a CWA, budget hours > 0, both dates, and CWP allocations summing to 100.

**Links** (no new relation): CWP `belongs_to` its CWA and each allocated WBS node, WBSNode `references` each
allocated cost code. These are written by the module (`by_module=True`, source `rule`) and kept in step with the
typed rows on every change (old link retracted by the module, new one added); a person cannot retract them. By
people: CWP `requires` EWPRef/PWPRef, CWP `references` documents and tags, CWP → activity with the schedule
module's `LinkActivity`.

## 3. Commands, access words, events

Access words are `awp.<area>.<verb>`; the **default role** column is what the roles spec seeds as data. Until that
spec is on the trunk, `viewer` and `user` words map to today's `user` level and `superuser` words to `admin`
(the plan's P2-Q3 A / P2-Q12 A). Agents hold no word; they propose.

| Command | Access word | Default role | Events (stream) |
|---|---|---|---|
| `DefineWbsNode` {code, title, parent_code?, position?} | `awp.wbs.configure` | superuser | `Record.Created`, `WBSNode.Defined` |
| `ReviseWbsNode` {node, title?, parent_code?, position?} | `awp.wbs.configure` | superuser | `Record.Updated` (title only), `WBSNode.Revised` |
| `RetireWbsNode` {node, reason} (refused while a non-void CWP allocates to it) | `awp.wbs.configure` | superuser | `WBSNode.Retired` |
| `MapWbsToCostCodes` {node, allocations[{cost_code, percent}]} (replaces the list) | `awp.wbs.configure` | superuser | `WBSNode.CostCodesMapped`, `Link.*` |
| `DefinePathOfConstruction` {steps[{cwa_code, reason_code?}]} (version 1) | `awp.path.configure` | superuser | `Record.Created`, `PathOfConstruction.Defined` |
| `MoveCwaInPath` {cwa_code, to_position, reason_code, note?, expected_version} | `awp.path.configure` | superuser | `PathOfConstruction.Resequenced` (full new list, version + 1) |
| `ResequencePath` {steps[...], reason_code, expected_version} (CLI and loader) | `awp.path.configure` | superuser | `PathOfConstruction.Resequenced` |
| `DefineCwa` {code, title, location_text?}; `ReviseCwa` | `awp.cwa.edit` | user | `Record.Created`, `CWA.Defined`; `CWA.Revised` |
| `RetireCwa` {cwa, reason} (refused while a non-void CWP names it) | `awp.wbs.configure` | superuser | `CWA.Retired` |
| `CreateCwp` {discipline, title, cwa_code, planned_start?, planned_finish?, budget_hours?, quantities?, contractor_text?} | `awp.cwp.edit` | user | `Numbering.Allocated`, `Record.Created`, `CWP.Defined`, `Link.Added` |
| `ReviseCwp`, `AllocateCwpToWbs` {cwp, allocations[{wbs_code, percent}]} | `awp.cwp.edit` | user | `CWP.Revised`; `CWP.AllocatedToWbs`, `Link.*` |
| `StartCwpDevelopment`, `StartCwpExecution`, `CompleteCwp` | `awp.cwp.edit` | user | `Workflow.Transitioned` |
| `ReleaseCwp` {cwp, expected_version} | `awp.cwp.release` | superuser | `CWP.Released` {by, record_hash}, `Workflow.Transitioned` |
| `ReturnCwp` {cwp, reason} | `awp.cwp.release` | superuser | `Workflow.Transitioned` (reason in note) |
| `CloseCwp`; `ReopenCwp` {reason} | `awp.cwp.close` | superuser | `Workflow.Transitioned` |
| `VoidCwp`, `VoidExternalPackage` {id, reason} | `awp.void` | superuser | `Record.Voided` |
| `RecordExternalPackage` {package_type: ewp\|pwp, package_no, title, status_text?, forecast_date?, actual_date?, constraint_source, source_system?} | `awp.package.edit` | user | `Record.Created`, `EWPRef.Defined` / `PWPRef.Defined` |
| `UpdateExternalPackage` {id, status_text?, forecast_date?, actual_date?, constraint_source?} | `awp.package.edit` | user | `EWPRef.Updated` / `PWPRef.Updated` |
| `RequestRollup` {} (queues `awp.rollup`; idempotent) | `awp.cwp.edit` | user | none (a job row) |
| all reads (routes, CLI, MCP, TUI, reports) | `awp.view` | viewer | — |

Every handler: `require_project`, `require_visible` on every id it is given (ADR-0016 §5), `correlated(cmd)`, keys
without `@` unless module-built; a title or description change in any `Revise*` appends `Record.Updated` from the
module command (never the generic `UpdateRecord`). Proposable (ADR-0014 §8): `propose_cwp` → `CreateCwp`, accepting person needs
`awp.cwp.edit`. Generic allow-list: CWP `{SetPsetValues, AddLink, SuggestLink, AttachFile} ∪ LINK_LIFE` with guard
`not_closed` (Closed or Void refuses); CWA, EWPRef, PWPRef `{AddLink, SuggestLink} ∪ LINK_LIFE`; CWA also
`AttachFile` (plot plan); WBSNode and PathOfConstruction none. `TransitionWorkflow`, `UpdateRecord`, `VoidRecord`
on nothing. Builder verifies `LinkActivity` from a CWP passes the source-end check with this list (L-P1-I1-8).

Webhook catalog gains every `tl:event_type` above; `CWP.Released` is the one the design names. Feed: `WBSNode.*`,
`PathOfConstruction.*`, `CWP.AllocatedToWbs` and `WBSNode.BudgetRolledUp` carry `feed_policy: none` (R-P2-16);
`CWP.Defined`, `CWP.Released` make ordinary cards.

## 4. Rollup job `awp.rollup` (contracts §5, §7)

`tl_mod_awp.rollup.request(uow, scope)` queues job id `rollup:<scope>` unless one is queued; called by every handler
that changes a CWP budget, a CWP or WBS allocation, a retirement or a void, and by `RequestRollup`. The run (one
scope, `JobRunner` kind, lease 300 s): read `as_of_seq`; for each leaf node n, `budget(n) = Σ budget_hours(c) ×
pct(c,n) / 100` over non-void CWPs (all states count: it is budget); parents sum children; per leaf the cost-code
split is `budget(n) × pct(n,k) / 100`, a leaf with no cost codes puts its hours on an `unallocated` line.
Exact `Decimal`, then quantize to 0.1 h `ROUND_HALF_EVEN`; a node's split uses largest remainder so parts sum to its
rounded total. Compare with `cur_awp_rollup`; append `WBSNode.BudgetRolledUp` {run_id, as_of_seq, total,
by_cost_code[...]} only for nodes whose figures differ, at most 500 nodes per run; settle re-queues when more
remain. Correlation `rollup:<run id>`, source `job:awp.rollup`. Same seq → same figures; a rebuild never calls
the job. `tl awp worker` runs the awp kinds (one kind in P2-I1).

## 5. Views, routes, reports

Read functions in `tl_mod_awp/views.py` (all through the viewer): `cwp_list(conn, scope, *, state=, discipline=,
cwa=)`, `cwp_detail(conn, scope, number)` (fields, allocations, packages, activities via
`tl_mod_schedule.resolver.links_to_activities`, link and file counts, timeline), `cwa_list`, `wbs_tree(conn, scope,
*, depth=None)` (depth-first, with rollup totals), `wbs_detail`, `path(conn, scope, version=None)`,
`path_versions`, `package_list(conn, scope, kind=)`. API (GET, `awp.view`): `/projects/{p}/awp/cwps`,
`/awp/cwps/{number}`, `/awp/cwas`, `/awp/wbs`, `/awp/wbs/{code:path}`, `/awp/path?version=`, `/awp/path/versions`,
`/awp/packages`, `/awp/reports/{name}`; writes are `POST /commands/<Name>` from `AWP_COMMANDS`. Every new GET route
joins the confidentiality walking test (`test_confidentiality_walk.py`, five readers).
Reports (`tl awp report <name>`, API, CSV): `cwp_status` (by state and discipline: count, budget h);
`wbs_vs_cost_code` (cost code, name, awp budget h, cost-system budget h from the latest `cost.CostSnapshot` when it
carries an hours measure else `—`, difference; plus the Unallocated row); `cwa_sequence` (current path with CWP counts
and budget h per CWA). Marts are P2-I6: the silver list gains `cur_awp_cwp`, `cur_awp_rollup` then (not here).

## 6. Imports (legacy loader framework)

No new parser: P2-I1 adds **load targets** to the loader framework (piece S1) and two loaders. A target is found by
the entry-point group `throughline.load_targets`; `awp.wbs` creates nodes (`code`, `title`, `parent`, optional
`cost_codes` as `CODE:PCT;CODE:PCT`) parents first, and plans a row invalid with a fixed reason when its parent is
unknown, its depth > 8 or its percentages do not sum to 100 (`allocation sums to 101.00, not 100.00`); `awp.cwa`
creates CWAs and, with a `sequence` column, the version-1 path. Loaders `awp-wbs` and `awp-cwa` (CSV and XLSX,
sample mapping files) are entry points of the awp package. The load stays create-only and compensable (ADR-0014
rule); `tl load` stays an admin act (platform power) until the roles spec says otherwise. This replaces the plan's
"WBS CSV reader in the envelope with preview and apply" (divergence 1).

## 7. Allowed actions per state and role (`tl_mod_awp/actions.py`, ADR-0010 addendum 2026-10-21)

One `RULES` table drives the offer, the handlers' `require_state` (`states_for`) and a test that each row's word
equals the command's access word. "Su" = superuser default; every row is also refused to agents.

| Type | States | Label | Command | Word (default) |
|---|---|---|---|---|
| CWP | Planned, In development | Edit; Allocate to WBS | `ReviseCwp`; `AllocateCwpToWbs` | `awp.cwp.edit` (user) |
| CWP | Planned | Start development | `StartCwpDevelopment` | `awp.cwp.edit` (user) |
| CWP | In development | Release for IWP development | `ReleaseCwp` | `awp.cwp.release` (Su) |
| CWP | Released for IWP development | Return to development; Start execution | `ReturnCwp`; `StartCwpExecution` | `awp.cwp.release` (Su); `awp.cwp.edit` (user) |
| CWP | Executing | Complete | `CompleteCwp` | `awp.cwp.edit` (user) |
| CWP | Complete | Close; Reopen | `CloseCwp`; `ReopenCwp` | `awp.cwp.close` (Su) |
| CWP | all but Closed | Void | `VoidCwp` | `awp.void` (Su) |
| WBSNode | Active | Edit; Retire | `ReviseWbsNode`; `RetireWbsNode` | `awp.wbs.configure` (Su) |
| WBSNode | Active, leaf | Map cost codes | `MapWbsToCostCodes` | `awp.wbs.configure` (Su) |
| PathOfConstruction | — | Move CWA | `MoveCwaInPath` | `awp.path.configure` (Su) |
| CWA | Active | Edit; Retire | `ReviseCwa`; `RetireCwa` | `awp.cwa.edit` (user); `awp.wbs.configure` (Su) |
| EWPRef, PWPRef | not void | Update; Void | `UpdateExternalPackage`; `VoidExternalPackage` | `awp.package.edit` (user); `awp.void` (Su) |

Forms (`ActionFormScreen`): Allocate to WBS and Map cost codes take up to 20 `code  percent` lines; Release asks
no words; Return, Reopen, Void, Retire ask a reason (≤ 500); Move CWA asks CWA, position, reason code. Create
commands are not offers: "New CWP", "New CWA" and "New package" are palette commands opening a form.

## 8. Logs and record screens (log standard, `tui-layout` skill)

All are `LogScreen` subclasses opened from the navigation panel ("Work packaging") and the palette, no F-key. The
column, panel and section definitions below are the contract for both clients: the web client renders the same
columns, summary line, sections and server-offered actions from the same routes (web core spec decides the shared
form; if the web renderer is on the trunk at C2 each screen ticket gets a web twin, else twins are filed for the
first web increment). Panels and the record screen's Details tab share one renderer per type (`details/awp.py`).

**CWP register** (home). Columns: Number, Subject, State, Discipline, CWA, Planned start, Budget h (right),
Allocated (`✓`/`—`). Keys: `/` filter, `d` discipline, `s` state, `c` by CWA. Panel: `P123-CWP-PIP-0001 · Rack 12
piping`; `In development · since 2026-10-28`; summary `Piping · CWA 12 · 2026-11-03 to 2027-01-29 · 4 200 h`.
Sections: Scope (Budget hours, Contractor, then table Commodity, Qty, UOM); Allocation (table WBS node, Title, %,
Hours); References (table Package, Type, Status, Forecast, Constraint source; `No packages linked`); Schedule
(table Activity, Name, Start, Finish; stale or orphaned marked `!`); Timeline (Date, Who, Event, Note); Files (n),
Links (n). P2-I2 adds IWPs `3 ready / 8`, P2-I5 Earned %.
**CWA register.** Number (code), Subject (name), Position (in the current path, `—` if absent), CWPs, Budget h.
No State column (no workflow; `Retired` rows hidden unless `r`). Panel summary `Position 3 of 12 · 4 CWPs ·
11 300 h`; sections Location, CWPs (table Number, Subject, State, Budget h), Files, Links.
**WBS tree.** Number (code), Subject (title indented two spaces per depth), Budget h, Cost codes (`3 · 100%`, or
`—` on a parent). Keys `1`–`8` depth limit, `u` unallocated leaves only. Panel `1.2.3 · Rack 12 piping`; second
line `Leaf · active` or `Parent of 4 · active`; summary `Parent 1.2 · 4 CWPs · 4 200 h`; sections Cost codes (table
Code, Name, %, Hours), CWPs (table Number, Subject, %, Hours), Timeline.
**Path of construction.** Number (position), Subject (CWA code · name), Reason, CWPs, Budget h. Keys `[` `]`
previous/next version, `v` compare with the previous version (two columns Before / After, moved rows marked `↑n`
`↓n`). Panel: version heading `Path of construction · version 4`; `Re-sequenced 2026-10-29 by A. Ruiz · reason
Access`; sections Steps changed, Versions (table Version, Date, Who, Reason).
**External packages.** Number (package no), Subject, Type (`EWP`/`PWP`, shown only when both present), Status
(owner's), Forecast, Actual, Constraint source (`Yes`/`—`), CWPs. Panel summary `EWP · forecast 2026-11-20 ·
required by 3 CWPs`.

## 9. Integration points

Cost: `cost.CostCode` by `references`, allocations typed; cost figures are read, never written (ADR-0015 §1).
Schedule: `LinkActivity` from CWPs; `links_to_activities` for the Schedule section; `unscheduled_records(record_type=
"awp.CWP")` report works unchanged. Documents and tags: generic `references` from a CWP; stale pins matter from
P2-I2 (IWP). Correspondence: none in I1 (the RFI `ConstraintSink`, ADR-0019 §9, is P2-I2). Threads:
`threads.enabled_types` gains `awp.CWP` (no dispatch targets yet). MCP read tools `list_cwps`, `get_cwp`,
`wbs_tree`, `path_of_construction`; proposable tool `propose_cwp`.

## 10. Pieces and tickets

Paths are repository-relative; every ticket's Allowed paths include its report `docs/reports/P2-I1/<id>.md`. B = builder
piece (`review: full`, sentinel + ≤ 5 targeted mutants on the named guards); H = Haiku ticket.

| ID | Kind | Rev | Depends | Title, Allowed paths | Tests it adds |
|---|---|---|---|---|---|
| S1 | B | full | W0-B1 | Load targets by entry point: `TargetKind` becomes a registered name; `throughline.load_targets`; built-ins `tags`, `documents`; generic column-mapping form for module targets; a target declares `scope: project | company` (`tl load open --company` for company targets, needed by P2-I3); duplicate name is a `ModuleLoadError`. `packages/tl-modules/legacy/**`, `packages/tl-cli/src/tl_cli/load.py`, `docs/runbooks/legacy-load.md`. Mutants: duplicate name, unknown target at plan, create-only skip | `packages/tl-modules/legacy/tests/test_load_targets.py` |
| S2 | B | full (schema, human gate) | W0-B1 | LinkML `schema/modules/awp/**`, `schema/fixtures/workflows/awp-cwp.yaml`, CWP line in `schema/fixtures/numbering/patterns.yaml`, `schema/fixtures/standards/co.acme.awp@1.0.0.yaml` (lists `Commodity`, `PathReason`, `ConstraintType`), offline annotations, `just gen` output | `packages/tl-schema/tests/test_awp_schema.py`; pinned lists regenerated |
| S3 | B | full | S1, S2 | `packages/tl-modules/awp/**` (new package: `module.py`, `names.py`, `limits.py`, `projectors/`, `handlers/wbs.py`, `path.py`, `cwa.py`, `targets.py`), root `pyproject.toml` entry points; WBS, allocation, path, CWA commands; load targets `awp.wbs`, `awp.cwa`; `views.py` WBS/path/CWA reads. Mutants: sum = 100, leaf-only, depth bound, expected_version | `packages/tl-modules/awp/tests/test_wbs.py`, `test_path.py`, `test_cwa.py`, `test_targets.py`, `test_projection_rebuild.py` (both adapters) |
| S4 | B | full | S3 | CWP and external package commands, workflow moves, `actions.py` `RULES`, `commands.py` `AWP_COMMANDS`, proposable `propose_cwp`, `views.py` CWP/package reads, provided tests for T03a–T07. Mutants: release preconditions, frozen fields after Release, access word per row, `not_closed` guard | `packages/tl-modules/awp/tests/test_cwp.py`, `test_actions.py`, `test_packages.py` |
| S5 | B | full | S4 | Rollup job `awp.rollup` (`tl_mod_awp/rollup.py`, projector rows, `tl awp worker` entry), §4. Mutants: largest remainder, unallocated bucket, batch bound, re-queue | `packages/tl-modules/awp/tests/test_rollup.py` (incl. rebuild = incremental, property test, both adapters) |
| T01 | H | lite | S2 | Samples (not gated fixtures): `packages/tl-modules/awp/src/tl_mod_awp/samples/wbs-sample.csv` (12 nodes, one row summing to 101), `cwa-sample.csv` (4 CWAs), loader mapping files under `tl_mod_awp/loaders/mappings/` | `packages/tl-modules/awp/tests/test_fixtures.py` (provided) |
| T02 | H | lite | S3, T01 | Loaders `awp-wbs`, `awp-cwa` (`tl_mod_awp/loaders/*.py`, package `pyproject.toml` entry points) | `packages/tl-modules/awp/tests/test_loaders.py` (provided) |
| T03a | H | full | S4 | API read routes `packages/tl-api/src/tl_api/routes/awp.py`, router line; walking test entries | `packages/tl-api/tests/test_api_awp.py`; walk lists in `test_confidentiality_walk.py` |
| T03b | H | full | T03a | `ApiClient` and TUI client methods (`tl_tui/client.py`, `embedded.py`, `remote.py`, fake) | `packages/tl-tui/tests/test_client_awp.py` |
| T04 | H | lite | S5 | CLI `tl awp wbs\|cwa\|cwp\|path\|package\|report\|rollup` (`packages/tl-cli/src/tl_cli/awp.py`) and reports `tl_mod_awp/reports.py` | `packages/tl-cli/tests/test_cli_awp.py`, `packages/tl-modules/awp/tests/test_reports.py` |
| T05a | H | full | T03b | CWP register + `details/awp.py` + `tl_tui/awp_text.py` (`widgets/cwp_register.py`) | `packages/tl-tui/tests/test_cwp_register.py` (80 and 170 cols, plain walk entry) |
| T05b | H | full | T03b | WBS tree and CWA register (`widgets/wbs_screen.py`, `widgets/cwa_register.py`) | `packages/tl-tui/tests/test_wbs_screen.py` |
| T05c | H | full | T03b | Path of construction and external packages logs (`widgets/path_screen.py`, `widgets/package_log.py`) | `packages/tl-tui/tests/test_path_screen.py` |
| T06 | H | full | T03a | MCP read tools and `propose_cwp` (`packages/tl-mcp/src/tl_mcp/awp_tools.py`; registration is glue) | `packages/tl-mcp/tests/test_awp_tools.py`, MCP walk entries |
| T07 | H | lite | T04 | Simulator `AwpDesk` (in `packages/tl-sim/src/tl_sim/client.py`) and `actors/workface_planner.py` (CWPs from a template) | `packages/tl-sim/tests/test_workface_planner.py` |
| T08 | H | full | T05a–c, T06, T07 | `dev/demos/P2-I1.sh`, `dev/demos/p2_i1_demo.py` (§11) | the demo itself |
| T09 | H | lite | T08 | Docs: `packages/tl-modules/awp/README.md`, `AGENTS.md`, `docs/runbooks/awp-setup.md`, `docs/modules/awp/` | — |

Totals: **5 pieces, 12 tickets**; more than 10 tickets, so the plan check of skill rule 8 runs on this spec before
dispatch. Checkpoints: C1 = S1–S3; C2 = S4, S5, T03a–b; C3 = all tickets; C4 = T08 green on both adapters, SR1.
Registry lines (`AWP_COMMANDS` splat, `add_typer`, `MCP_ACTIONS`, nav entry) are supervisor glue; I3 merges last.

## 11. Demo clauses (`just demo P2-I1`, SQLite then Postgres, one PASS each)

1. An admin loads `co.acme.awp@1.0.0`; loading twice changes nothing. 2. `tl load` of `wbs-sample.csv` plans 12 new
and 1 invalid (`allocation sums to 101.00, not 100.00`), loads 12; each leaf `references` its cost codes; compensate
then reload gives the same tree. 3. The CWA loader makes 4 CWAs and path v1; `MoveCwaInPath` makes v2; both versions
read back; a stale `expected_version` is refused. 4. A user creates 6 CWPs (`P123-CWP-PIP-0001`…), allocates them,
links two EWPRefs (one `constraint_source`) and activities of the P1-I4 demo schedule; release is refused without an
allocation, accepted for a superuser, refused for a user. 5. The rollup runs; `wbs_vs_cost_code` shows budget hours
per cost code and the Unallocated row; a revised budget moves the figures and both runs are in the ledger; rebuild
gives the same rows. 6. A user cannot map cost codes or move the path; an agent's `propose_cwp` waits until a person
accepts. 7. API, TUI (CWP register, WBS tree, path screen at 170 columns) and MCP show the same CWP.

## 12. Divergences, risks, owner questions

Divergences: (1) WBS and CWA import through loader targets, not a module CSV reader (one import path, envelope and
compensation for free). (2) Roles: access words with default roles replace the plan's `admin`/`user` (owner decision
1); WBS, allocation and path are awp **superuser**, not admin (P2-Q12 superseded). (3) CWP pattern in
`numbering/patterns.yaml` (allocator file, as correspondence), not in the standards edition, which holds only code
lists. (4) Rollup table is contracts §5 `cur_awp_rollup` with a `measure` column, not the plan's
`cur_awp_wbs_rollup`; event `WBSNode.BudgetRolledUp` (per node) instead of `CWP.BudgetRolledUp`. (5) Releasing a
CWP is a superuser act and CWP→WBS allocation is frozen from Release (new; the design listed no CWP approvals).
Risks: R-P2-2 (rollup at scale: bench 5 000 nodes × 2 000 CWPs before C4, one bound JSON per chunk on Postgres);
R-P2-4 pinned lists (S2 regenerates); the load-target change touches a P1 package (S1 runs the legacy suite and the
P1-I8 demo); the roles spec landing after C2 forces a word-to-level shim (interim map above, one test).
Owner questions: Q-M3-1 is CWP release a superuser act (proposed) or a planner (`user`) act? Q-M3-2 cost-code
allocation on leaf nodes only (proposed)? Q-M3-3 may an awp superuser run `tl load` for awp targets, or does it stay
admin? Q-M3-4 the GC's commodity list for CWP quantities (sample list until given).
