# awp (`tl_mod_awp`)

The awp module (M3, part 1) keeps the WBS and its cost-code allocation, the path of construction, the construction work areas (CWA), the construction work packages (CWP) and the owner's EWP and PWP references for a project. It implements the budget rollup from CWP to WBS node to cost code (§1 scope of `docs/build-spec/specs/m3-wbs-cwp.md`; brief §8 and §9 for the packaging context, `docs/brief-v0.4.md`).

From P2-I2 it also keeps the interim work packages (IWP): their scope, pins, sign-off, issue and hold, and their readiness, the last evaluation of the nine readiness checks. Constraints on any record are a core type (`tl_core.constraints`, ADR-0024); this module only reads them and reads their effect on readiness. Runbook: `docs/runbooks/iwp-readiness.md`.

From P2-I5 it also keeps the weekly plan (`awp.WeeklyPlan`: one per ISO week, its commitments and outcomes), the earned progress of each IWP under the rules of credit in force for the project, the KPI tiles and the IWP work pack. Runbooks: `docs/runbooks/weekly-cycle.md`, `docs/runbooks/rules-of-credit.md`, `docs/runbooks/iwp-pack.md`.

## Public interface

Import: `tl_mod_awp` (module name `awp`, spec `tl_mod_awp.module:spec`).

### Record types

| Type | Key | Holds |
|---|---|---|
| `awp.WBSNode` | typed code, unique per project | a WBS node, its parent, depth and retired flag; child table `cur_awp_wbs_allocation` |
| `awp.PathOfConstruction` | one per project | the ordered CWAs, every version kept; child table `cur_awp_path_step` |
| `awp.CWA` | typed code | a construction work area and its location |
| `awp.CWP` | allocator number `P123-CWP-PIP-0001` | a work package with its dates, budget hours and workflow state; child table `cur_awp_cwp_allocation` |
| `awp.EWPRef`, `awp.PWPRef` | typed package number | a mirror of the owner's engineering or procurement package |
| `awp.IWP` | `P123-IWP-PIP-0001` style number | an interim work package: discipline, CWP, crew, foreman, state, pins and sign-offs (`schema/modules/awp/iwp.yaml`) |
| `awp.ScopeItem` | scope key | one scope item (commodity, quantity, unit, hours) that an IWP takes by `AddIwpScope` (`schema/modules/awp/scope_item.yaml`) |
| `awp.WeeklyPlan` | ISO week `YYYY-Www` per scope | the plan of one week: state `Draft`, `Committed` or `Closed`; child table `cur_awp_week_commitment` (one row per committed IWP, its hours and outcome) (`schema/modules/awp/week.yaml`) |

Rollup rows are in `cur_awp_rollup`, written by the server job only. Keys are namespaced per type (`awp.wbs@`, `awp.cwa@`, `awp.ewp@`, `awp.pwp@`; `names.py` `KEY_PREFIX`).

### Events (19)

| Event | Written by |
|---|---|
| `WBSNode.Defined`, `WBSNode.Revised`, `WBSNode.Retired`, `WBSNode.Reinstated` | the WBS commands |
| `WBSNode.CostCodesMapped` | `MapWbsToCostCodes` |
| `WBSNode.BudgetRolledUp` | the rollup job (`feed_policy: none`) |
| `PathOfConstruction.Defined`, `PathOfConstruction.Resequenced` | the path commands |
| `CWA.Defined`, `CWA.Revised`, `CWA.Retired` | the CWA commands |
| `CWP.Defined`, `CWP.Revised`, `CWP.AllocatedToWbs`, `CWP.Released` | the CWP commands |
| `EWPRef.Defined`, `EWPRef.Updated`, `PWPRef.Defined`, `PWPRef.Updated` | the package commands |

The full event schemas are in `schema/modules/awp/events.yaml`.

### IWP events (P2-I2)

Schemas in `schema/modules/awp/iwp_events.yaml`.

| Event | Written by |
|---|---|
| `IWP.Created`, `IWP.Revised` | `CreateIwp`, and the IWP edits |
| `IWP.ScopeAdded`, `IWP.ScopeRemoved`, `IWP.DocumentPinned`, `IWP.Split` | the scope, pin and split commands |
| `IWP.SignedOff`, `IWP.Issued` | `SignOffIwp`, `IssueIwp` |
| `IWP.Held`, `IWP.HoldReleased` | `HoldIwp`, `ReleaseHold` |
| `IWP.ReadinessEvaluated` | the readiness job (one per evaluation) |
| `IWP.Ready` | the readiness job, when an IWP turns Ready; the event the brief's default webhook carries |
| `ScopeItem.Created`, `ScopeItem.Revised` | `CreateScopeItem` |

`IWP.Ready` is an ordinary outbox event: a webhook subscription (`docs/runbooks/webhook-operations.md`) receives it. An evaluation that leaves the IWP not Ready writes `IWP.ReadinessEvaluated` only.

### Weekly plan and progress events (P2-I5)

Schemas in `schema/modules/awp/week_events.yaml` and `progress.yaml`; the IWP events above also carry the P2-I5 fields.

| Event | Written by |
|---|---|
| `WeeklyPlan.Opened` | `OpenWeeklyPlan` (`week open`) |
| `WeeklyPlan.IwpCommitted` | `CommitIwpToWeek` (`week commit`) |
| `WeeklyPlan.OutcomeRecorded` | `RecordWeekOutcome` (`week outcome`) |
| `WeeklyPlan.Closed` | `CloseWeek` (`week close`); writes the PPC |
| `IWP.Started` | `StartIwpWork` (`iwp start-work`) |
| `IWP.FieldCompleted` | `CompleteIwpField` (`iwp complete-field`) |
| `IWP.ProgressRecorded` | `RecordManualProgress` (`iwp step`), when the figure or the manual list changes; `CompleteIwpField` writes one as well |

The rules of credit are a package (`co.acme.awp@1.1.0` shipped; `rules_of_credit` section). The project's edition is the setting `awp.rules_of_credit.set`, written by `tl awp roc set`.

### Constraints (core, read here)

`core.Constraint` is a core record type that can sit on any record (ADR-0024). It is not owned by awp. The commands are `RaiseConstraint`, `AssignConstraint`, `ClearConstraint` and `WithdrawConstraint` in `tl_core.constraints`; they take the core word `core.constraint.edit`, and the reads take `core.constraint.view`. A constraint with a blocking severity on an IWP is what the `constraints_cleared` check counts. Constraint events are `Constraint.Raised`, `Constraint.Assigned`, `Constraint.Cleared` and `Constraint.Withdrawn`. No awp word exists for constraints: `awp.constraint.edit` is dropped (ADR-0024 decision 7).

### Commands and access words

Every command needs its access word (`schema/settings/access-words.yaml`). Agents hold no word; they propose (see `propose_cwp` below). Command names are the API's `POST /commands/<Name>` routes.

| Command | Access word | CLI verb (`tl awp …`) |
|---|---|---|
| `DefineWbsNode`, `ReviseWbsNode`, `RetireWbsNode`, `ReinstateWbsNode`, `MapWbsToCostCodes` | `awp.wbs.configure` | `wbs define`, `wbs revise`, `wbs retire`, `wbs map` (no CLI verb for reinstate) |
| `DefinePathOfConstruction`, `MoveCwaInPath` | `awp.path.configure` | `path define`, `path move` |
| `DefineCwa`, `ReviseCwa` | `awp.cwa.edit` | `cwa define`, `cwa revise` |
| `RetireCwa` | `awp.wbs.configure` | `cwa retire` |
| `CreateCwp`, `ReviseCwp`, `AllocateCwpToWbs` | `awp.cwp.edit` | `cwp create`, `cwp revise`, `cwp allocate` |
| `StartCwpDevelopment`, `StartCwpExecution`, `CompleteCwp` | `awp.cwp.edit` | `cwp move start-development \| start-execution \| complete` |
| `ReleaseCwp`, `ReturnCwp` | `awp.cwp.release` | `cwp move release \| return` |
| `CloseCwp`, `ReopenCwp` | `awp.cwp.close` | `cwp move close \| reopen` |
| `VoidCwp` | `awp.void` | `cwp void` |
| `RecordExternalPackage`, `UpdateExternalPackage` | `awp.package.edit` | `package record`, `package update` |
| `VoidExternalPackage` | `awp.void` | `package void` |
| `RequestRollup` | `awp.cwp.edit` | `rollup` |
| `CreateIwp`, `CreateScopeItem`, `AddIwpScope`, `RemoveIwpScope`, `PinIwpDocument`, `SplitIwp` | `awp.iwp.edit` | `iwp create`, `iwp item-create`, `iwp add-scope`, `iwp remove-scope`, `iwp pin`, `iwp split` |
| `StartIwpDevelopment`, `SendIwpToConstraintCheck`, `ReturnIwpToDevelopment` | `awp.iwp.edit` | `iwp move start-development \| constraint-check \| return-to-development` |
| `CancelIwp` | `awp.void` | `iwp cancel` |
| `SignOffIwp` | `awp.iwp.signoff` | `iwp sign-off --hash <sha256>` |
| `IssueIwp` | `awp.iwp.issue` | `iwp issue --hash <sha256>` |
| `HoldIwp`, `ReleaseHold` | `awp.iwp.hold` | `iwp hold`, `iwp release-hold` |
| constraint writes (core) | `core.constraint.edit` | `constraint raise`, `constraint assign`, `constraint clear`, `constraint withdraw` |
| clear of a check-raised constraint as waived (core) | `core.constraint.waive` (controller) | `constraint clear` |
| `OpenWeeklyPlan` | `awp.week.plan` | `week open` |
| `CommitIwpToWeek`, `RecordWeekOutcome` | `awp.week.commit` | `week commit`, `week outcome` |
| `CloseWeek` | `awp.week.close` (controller) | `week close` |
| `RecordManualProgress`, `InstallScopeItem`, `ReturnScopeItem`, `VerifyScopeItem` | `awp.progress.record` | `iwp step`, `iwp item-move` |
| `StartIwpWork`, `CompleteIwpField` | `awp.iwp.edit` | `iwp start-work`, `iwp complete-field` |
| set the rules-of-credit edition | the project setting `awp.rules_of_credit.set` (no awp word) | `roc set` |
| `tl awp worker` (applies the hold rule) | `awp.worker.run` (controller, company scope) | `worker` |
| weekly and progress reads: `week ls`, `week show`, `week ppc`, `week reasons`, `look-ahead`, `roc ls`, `roc show`, `iwp progress`, `export progress`, `report kpi_ppc`, `report kpi_constraint_free`, `iwp pack` | the viewer's class filter | the reads the view returns |
| IWP reads: `iwp ls`, `iwp show`, `iwp scope`, `iwp hash`, `readiness ls`, `readiness show` | none checked by the CLI; the module's class filter applies | the reads the view returns |
| constraint reads: `constraint ls`, `constraint show`, `constraint groups` | `core.constraint.view` | the reads |
| `report` (CWP, IWP and constraint names) | none checked by the CLI; the class filter applies | `report <name> --project P123` |
| all other reads | `awp.view` | `wbs tree`, `wbs show`, `cwp ls`, `cwp show`, `cwa ls`, `path show`, `path versions`, `package ls` |

### Load targets and loaders

| Target | Loader (`tl load open --loader`) | Scope | Creates |
|---|---|---|---|
| `awp_wbs` | `awp-wbs` (CSV, XLSX) | project | WBS nodes with `cost_codes` as `CODE:PCT;CODE:PCT` |
| `awp_cwa` | `awp-cwa` (CSV, XLSX) | project | CWAs, and the version-1 path when a `sequence` column is present |

Both are create-only and compensable, except the path, which cannot be taken back. Procedure: `docs/runbooks/awp.md`.

### Weekly cycle, rules of credit and progress (P2-I5)

- **Weekly plan.** A week is `Draft` until its first commitment, then `Committed`, then `Closed`. Only an Issued or In progress IWP that is not on hold can be committed; a second commit of the same IWP replaces the first. A commitment has hours above 0 with one decimal place. Outcomes are `done` or `missed` (missed needs a miss-reason key from the adopted edition, `week reasons`) and can be corrected until the week is closed. `CloseWeek` needs at least one commitment, every commitment with an outcome, and writes the PPC: IWPs done over IWPs committed, one decimal place. A closed week is final.
- **Progress.** Steps of scope items are marked by hand (`iwp step`) only where no record proves them; the earned percent of an IWP follows from the stored figure and the rules of credit (`roc show`). Figures keep the edition in force when recorded. `iwp progress` reads them.
- **Export and KPIs.** `export progress --period YYYY-Www` prints earned progress by cost code as CSV, computed on read (nothing stored). `report kpi_ppc` is the PPC tile over the last 4 closed weeks; `report kpi_constraint_free` is the share of live IWPs with no open blocking constraint.
- **Work pack.** `iwp pack NUMBER --project P --out FILE` writes one printable HTML file of an IWP (sections, drawing codes, sign-off); `--attach` stores it in the IWP's `pack` slot. QR codes need the `pack` extra; without it the file is written without them and a note says so.
- **Hold and waive.** A blocking constraint raised on an Issued IWP puts it On hold when `tl awp worker` runs (`readiness/hold_rule.py`, `IWP.Held` with `by` and `reason`). Only Issued IWPs move; a constraint cleared or withdrawn before the worker runs holds nothing; a replay writes nothing. Clearing a check-raised constraint needs `core.constraint.waive`; the clear is then a waive (state Cleared, `waived` derived, no new event field), and `iwp show` lists `waived by <who>: <reason>`.
- **Worker word.** `tl awp worker` needs `awp.worker.run`, a company-scope controller word: a project-only superuser is refused.
- **Foreman landing.** The TUI opens on the IWP log filtered to the foreman's own IWPs when the `tui.landing` setting is `iwp_mine`, or when it is unset and the signed-in person is a foreman of an IWP. A user who sets `default` opens as before.

### Rollup job

`rollup.request(uow, scope)` queues job `rollup:<scope>` (kind `awp.rollup`) once; `tl awp rollup` calls it. `tl awp worker` runs the queue. Figures: budget hours per leaf, summed to parents, split by cost code with largest remainder. Only nodes whose figures changed get an event.

### Screens (TUI)

Palette ids (keyless entries in `tl_tui/commands.py` `APP_COMMANDS`, opened with `Ctrl+P`):

| Palette id | Screen | Shows |
|---|---|---|
| `cwps` | CWP register | number, subject, state, discipline, CWA, start, budget hours, allocated |
| `wbs` | WBS tree | code, title, budget hours, cost codes; keys `1`-`8` depth, `u` unallocated leaves |
| `cwas` | CWA register | code, title, position on the path, CWP count, budget hours |
| `path` | Path of construction | steps of one version; `[` `]` previous and next version, `v` compare |
| `packages` | External packages | EWP and PWP: number, title, status, forecast, actual, constraint source |
| `week` | Weekly cycle | five steps (keys `1` to `5`): look-ahead; constraints (`x` waive); release (`s` sign off, `i` issue); commitments (`c` commit, `d` done, `m` missed, `z` close, `o` open); progress (`w` start work, `f` complete field work). `tl_tui/widgets/weekly_screen.py` |
| `iwps` | IWP log | IWP number, title, state, foreman; `r` filters to the Ready IWPs; `Enter` opens the IWP screen, where `r` opens readiness and `c` the constraints (`tl_tui/widgets/iwp_register.py`) |
| `constraints` | Constraint log | open constraints and their owners (core constraint screen) |
| `backlog` | Backlog | IWPs by view, with the sizing view |

The readiness screen (`tl_tui/widgets/readiness_screen.py`) has no palette id; it opens from the IWP screen with `r`. Full key lists: `docs/reference/awp.md`.

The CWP record's Details tab uses the same renderer as the panels (`tl_tui/details/awp.py`).

### MCP read tools

From `packages/tl-mcp/src/tl_mcp/awp_tools.py`. An agent may call a tool only when its identity lists the tool as `mcp.<tool>` (`tl_mcp/identity.py`); each read tool then passes the same `document.read` check as every other read (`guarded`), answered under the agent's own viewer, and `propose_cwp` only files a proposal a person accepts.

| Tool | Arguments | Returns |
|---|---|---|
| `list_cwps` | `project`, `state?`, `discipline?`, `cwa?` | CWPs by number, void ones left out |
| `get_cwp` | `project`, `number` | one CWP with allocation, packages, activities |
| `wbs_tree` | `project`, `depth?` (1 to 20) | WBS nodes depth-first with rollup |
| `path_of_construction` | `project`, `version?` | the path at one version, or null |
| `propose_cwp` | `project`, `discipline`, `title`, `cwa_code`, `planned_start?`, `planned_finish?`, `budget_hours?`, `summary?` | a pending proposal, **not a write**: a person who may edit CWPs accepts it in the review queue |

Weekly and progress reads (`packages/tl-mcp/src/tl_mcp/awp_week_tools.py`, each needs `mcp.<tool>`): `list_weekly_plans`, `get_weekly_plan` (week `YYYY-Www`), `get_iwp_progress`, `get_progress_rollup`, `list_kpis`. The look-ahead is not on MCP (D29). Clear and close are not offered to agents (`agent_must_propose`).

### MCP IWP tools

From `packages/tl-mcp/src/tl_mcp/iwp_tools.py` (not `awp_tools.py`). Each needs `mcp.<tool>` in the agent's identity (`IWP_MCP_ACTIONS`, `tl_mcp/identity.py`). The reads are the lowest clearance, so a hidden record answers as a missing one. The agent holds no `core.constraint.*` word, so there are no constraint tools (D37).

| Tool | Arguments | Returns |
|---|---|---|
| `list_iwps` | `project`, `state?` | IWPs by number |
| `get_iwp` | `project`, `number` | one IWP with its crew, scope by type, pins, open constraints and sign-offs |
| `list_iwp_scope` | `project`, `number` | the scope items of one IWP |
| `get_iwp_readiness` | `project`, `number` | the last readiness evaluation, check by check |
| `propose_iwp_scope` | `project`, `iwp`, `items` (at most 50) | a pending proposal, **not a write**: a person with the `user` word accepts it (ADR-0014 section 8) |
| `propose_progress` | `project`, `iwp`, `steps` (at least 1, at most 50) | a pending proposal of hand progress, **not a write**: a person with `awp.progress.record` accepts it |
| `propose_week_commitment` | `project`, `week` (`YYYY-Www`), `iwp`, `committed_hours`, `foreman?` | a pending proposal, **not a write**: a person with `awp.week.commit` accepts it |

### Readiness (P2-I2)

`tl_mod_awp/readiness/` (engine, job, projector, view) evaluates one IWP per job (`ready:<iwp>`). It runs the nine checks named in D9 and writes `IWP.ReadinessEvaluated`; when the IWP is Ready after the evaluation it also writes `IWP.Ready`. The checks are registered through the entry-point group `throughline.readiness_checks`.

| Check | Source | Answer in this release |
|---|---|---|
| `documents_current` | engineering documents, pins | a real check |
| `rfis_answered` | RFIs | a real check |
| `materials_reserved` | materials reservations | a real check |
| `constraints_cleared` | open blocking constraints on the IWP (`readiness/checks.py`) | a real check |
| `permits_planned` | `tl_mod_awp/checks_na.py` | `n_a` (the module it waits for does not exist yet) |
| `inspections_planned` | `checks_na.py` | `n_a` |
| `labour_requested` | `checks_na.py` | `n_a` |
| `predecessors_handed_over` | `checks_na.py` | `n_a` |
| `model_slice_available` | `checks_na.py` | `n_a` |

A check answers `ok`, `blocked`, `pending`, `n_a` or `unknown`. `ok` and `n_a` pass (D9); any other state makes the IWP not Ready. `unknown` is released only when `awp.release.allow_unknown_checks` is true (default false).

### Sign-off, issue and hold (P2-I2)

- The life cycle: `Planned` (`iwp move start-development`), `Constraint check` (`iwp move constraint-check`), `Ready` (only by the readiness job), `Issued`, `In progress` (`iwp start-work`), `On hold`, `Cancelled`.
- `SignOffIwp` needs the IWP `Ready` and `SIGNERS_NEEDED` = 2 distinct signers, each holding a role in `awp.release.signoff_roles` in the project. The hash passed (`iwp hash`) must equal the record hash now; a stale hash is refused.
- `IssueIwp` needs `Ready`, the same hash, and two distinct signers among the recorded sign-offs.
- `HoldIwp` acts from `Ready`, `Issued` or `In progress`; `ReleaseHold` from `On hold`.
- A new blocking constraint on an Issued IWP puts it On hold through the worker (P2-I5, see *Weekly cycle, rules of credit and progress*).

### Reports (P2-I2)

`tl awp report <name> --project P123` (`tl_mod_awp/iwp_reports.py`): IWP reports `iwp_status`, `iwp_readiness`; constraint reports `constraint_log`, `constraints_by_category`, `constraints_by_owner`, `constraints_by_age`. P2-I5 adds the KPI tiles `kpi_ppc` and `kpi_constraint_free` (`tl_mod_awp/kpis.py`). The CWP reports `cwp_status`, `wbs_vs_cost_code`, `cwa_sequence` are the P2-I1 set. List-level counts (Ready and Constraints per IWP row) are not shown on the IWP log; they are a follow-up read (D33).

## Depends on / used by
- Depends on: `tl-core`, `tl-schema`, `tl-adapters`, `tl-mod-engineering`, `tl-mod-legacy`, `tl-mod-schedule` (the list in `packages/tl-modules/awp/pyproject.toml`). Cost codes are read, never written (`tl_mod_cost`).
- Used by: `tl-api` (commands and GET routes), `tl-mcp` (`awp_tools.py`), `tl-cli` (`tl awp`, `tl load`), `tl-tui` (five screens and the CWP record).

## Commands

```
just test packages/tl-modules/awp
uv run tl awp --help
uv run tl awp rollup --project P123
uv run tl awp worker --once
uv run tl load targets
uv run tl awp iwp ls --project P123
uv run tl awp readiness ls --project P123
uv run tl constraint ls --project P123
```

`tl load targets` lists `awp_cwa` and `awp_wbs`. Runbook for the IWP steps: `docs/runbooks/iwp-readiness.md`.

## Configuration

| Setting or env var | Default | Notes |
|---|---|---|
| `TL_DB` | the root `--db` | SQLite path or `postgresql://` URL; `tl awp … --db` overrides it |
| access words | `schema/settings/access-words.yaml` | the `awp.*` rows |
| `tl awp worker --once` | off | without it the worker waits until interrupted |

Limits (`limits.py`): WBS depth at most 8 levels, at most 5 000 nodes per project; path at most 500 steps; an allocation list at most 20 lines; CWP quantities at most 50 rows.

## Not built yet
Struck from P2-I5 (roadmap 3c). The list and the reasons are in `docs/build-spec/DEFERRED.md`: the closeout and subcontract screens, the PDF pack, demo clauses 7 and 8, and the web pages of the weekly cycle.

## Rules specific to this package
See `AGENTS.md` in this directory.

## Status
Introduced in P2-I1 (S3 to S7). P2-I5 adds the weekly cycle, the rules of credit and progress, the KPI tiles, the IWP work pack and the hold and waive rules (reports `docs/reports/P2-I5/`). IWP, scope, sign-off, issue, hold, readiness and the IWP and constraint reports added in P2-I2 (decisions D9, D18, D33 and D37 in `docs/tickets/P2-I2/STATE.md`). Last interface change: P2-I2 (see `docs/tickets/P2-I2/STATE.md`). Constraints: ADR-0024.
