# P2-I1-S3 — The awp package: WBS, cost-code mapping, path of construction and CWA commands

Status: ready
Tier: builder
Kind: piece
Review: full
Labels: core, schema
Depends on: S2 (merged; generated models and `cur_awp_*` DDL are on the branch)
Branch: `p2/i1-s3-awp-package`
Worktree: `/home/user/wt/i1-s3` (from `p2/i1` head)
Approver (schema edit in step 1): owner, or the orchestrator under P2-Q10 (line in `docs/reports/APPROVALS.md` at merge)

## Goal
After this piece `packages/tl-modules/awp/` (import name `tl_mod_awp`) is a registered module that creates and changes
the WBS, its cost-code allocations, the path of construction and CWAs by command, projects them into the `cur_awp_*`
tables, keeps the links in step, and exposes `rollup.request()`. Core feed code stops making cards for the eight awp
no-card events. S4 (CWP, packages), S5 (rollup run) and T02 (load targets) build on it; they do not exist yet.

## Brief references (pasted; spec `docs/build-spec/specs/m3-wbs-cwp.md` §2, §3, §4 first paragraph, §7 is authoritative)
Commands (all project scope; `require_project`, `require_visible` on every id given, `correlated(cmd)`, keys without `@`):

| Command | Access word | Events |
|---|---|---|
| `DefineWbsNode` {code, title, parent_code?, position?} | `awp.wbs.configure` | `Record.Created`, `WBSNode.Defined` |
| `ReviseWbsNode` {node, title?, parent_code?, position?} | `awp.wbs.configure` | `Record.Updated` (title only), `WBSNode.Revised` |
| `RetireWbsNode` {node, reason} (refused while a non-void CWP allocates to it) | `awp.wbs.configure` | `WBSNode.Retired` |
| `MapWbsToCostCodes` {node, allocations[{cost_code, percent}]} (replaces the list) | `awp.wbs.configure` | `WBSNode.CostCodesMapped`, `Link.*` |
| `DefinePathOfConstruction` {steps[{cwa_code, reason_code?}]} (version 1) | `awp.path.configure` | `Record.Created`, `PathOfConstruction.Defined` |
| `MoveCwaInPath` {cwa_code, to_position, reason_code, note?, expected_version} | `awp.path.configure` | `PathOfConstruction.Resequenced` (full new list, version + 1) |
| `DefineCwa` {code, title, location_text?}; `ReviseCwa` | `awp.cwa.edit` | `Record.Created`, `CWA.Defined`; `CWA.Revised` |
| `RetireCwa` {cwa, reason} (refused while a non-void CWP names it) | `awp.wbs.configure` | `CWA.Retired` |

Rules (fixed messages, never cell text): WBS depth <= 8 (`depth` column 0..7), <= 5 000 nodes per project; allocation
only to leaf nodes (a node with children has none; giving a leaf a child is refused while it has allocations or CWP
allocations); allocation lists <= 20 rows, each `0.01..100.00`, no repeated cost code, sum exactly `100.00`, every cost
code exists in the project; a retired node or CWA takes no new allocation; path <= 500 steps, every non-retired CWA at
most once; a `Revise*` that changes the title appends `Record.Updated` from the module command (never `UpdateRecord`).
Links: WBSNode `references` each allocated `cost.CostCode`, written by the module (`by_module=True`, source `rule`) and
kept in step on every change (old link retracted by the module, new one added); a person cannot retract them.
Generic allow-list (`RULES`/`actions.py` shape of the cost module): CWA `{AddLink, SuggestLink, AttachFile} ∪ LINK_LIFE`;
WBSNode and PathOfConstruction none; `TransitionWorkflow`, `UpdateRecord`, `VoidRecord` on nothing.
`tl_mod_awp.rollup.request(uow, scope)` queues job id `rollup:<scope>` unless one is queued (idempotent); every handler
that changes an allocation or retires a node/CWA calls it. S3 ships `request()` only; the run is S5.
Decimals are text in events, `Decimal` in Python, ASCII digits only (`tl_core/text.py`).

Decision Q1 (feed): the eight awp events with `feed_policy: none` (`WBSNode.Defined|Revised|Retired|CostCodesMapped|
BudgetRolledUp`, `PathOfConstruction.Defined|Resequenced`, `CWP.AllocatedToWbs`) must make no feed card. Smallest safe
change: add those eight names to `POLICY_EVENT_TYPES` in `packages/tl-core/src/tl_core/feed/cards.py`. If you find a
smaller change that is as safe, take it and say so; do not widen the set beyond the eight.

## Interfaces (open these; copy their shape)
- Package layout, `module.py` spec, `registry.py`, `names.py`, `limits.py`, `projectors/`, `handlers/`, `pyproject.toml`
  entry point: `packages/tl-modules/cost/` (`tl_mod_cost`). Handler and command shape with `CommandSpec.access`:
  `tl_mod_cost/handlers/snapshots.py`, `tl_mod_cost/commands.py`.
- Link by module and retract: grep `by_module=True` in `packages/tl-modules/correspondence`.
- Job queue request: `docs/build-spec/specs/m3-wbs-cwp.md` §4 and an existing `JobRunner` kind in `tl_core` (grep `queue`).
- Generated models: `tl_schema/generated/` (never edit by hand).

## Context (<= 10 files; read these, nothing else unless a step says so)
- `docs/build-spec/specs/m3-wbs-cwp.md` §2, §3, §4, §7
- `packages/tl-modules/cost/pyproject.toml`, `src/tl_mod_cost/{module,commands,names,limits}.py`, `handlers/snapshots.py`
- `schema/modules/awp/{wbs,path,cwa,events}.yaml`
- `docs/reports/P2-I1/S2.md`
may explore: `packages/tl-modules/correspondence/` (links by module), `schema/settings/access-words.yaml` lines 10-19.

## Allowed paths
- `packages/tl-modules/awp/**` (create: `pyproject.toml`, `AGENTS.md` stub of 5 lines, `src/tl_mod_awp/{__init__,module,names,limits,errors,common,commands,actions,rollup,targets,views}.py`, `handlers/{wbs,path,cwa}.py`, `projectors/`)
  - `commands.py` holds the models and an `AWP_COMMANDS` tuple of the commands above (S4 extends it); `actions.py` holds `RULES` for the types above (S4 extends it).
  - `targets.py` and `views.py` are stubs with a module docstring and the signatures of spec §5 / §6, bodies `raise NotImplementedError` (T02 and T10 fill them).
- Root `pyproject.toml` and `uv.lock` (workspace member and source line only, as the cost package); then `uv sync`.
- `packages/tl-core/src/tl_core/feed/cards.py` (the eight names only) and, as consequential pins (rule 12), any test under `packages/tl-core/tests/` that fails only because those eight now have a policy; list each.
- Schema edit (human gate): in `schema/modules/awp/wbs.yaml`, `cwa.yaml`, `external_package.yaml` delete the `tl:ix_scope_code` and both `tl:ix_scope_package` lines (redundant with the `scope, code` / `scope, package_no` unique keys, review finding F2); `just gen`; update the pinned DDL lists in `packages/tl-schema/tests/test_generate.py` and `test_ddl.py` for the removed names (names removed only).
- `packages/tl-schema/src/tl_schema/generated/**` (`just gen` output only).
- `dev/accept/P2-I1/S3.py` (create), `docs/reports/P2-I1/S3.md` (create).
Not allowed: any other `schema/**`, other packages' source, `tl_core` outside `feed/cards.py`, the CWP, EWP/PWP and rollup-run code, tests beyond the pins above (owner policy: tests at T11).

## Steps
1. Schema index edit and `just gen` first; commit schema, generated and pinned lists together.
2. Package skeleton, `module.py` registration, root `pyproject.toml`, `uv sync`; `ModuleSpec` registers handlers, projectors, record types and `RULES` as the cost module does.
3. Projectors for `WBSNode`, `WBSAllocation`, `PathOfConstruction`, `PathStep` (every version kept), `CWA`; rebuild from events must equal the incremental result.
4. Handlers per the table, links in step, `rollup.request()` calls, the `cards.py` change.
5. Acceptance script.

## Acceptance (run these once; no new pytest)
```
just check
uv run python dev/accept/P2-I1/S3.py
just gate tests/services packages/tl-schema packages/tl-core/tests/feed
```
`S3.py` (SQLite, tmp db, acting accounts at `viewer`, `user`, `controller` as an existing acceptance script does; one
`PASS <check>` line each; final `S3 ok`; <= 40 output lines): build a 3-level WBS, map a leaf to two cost codes 60/40;
refuse sum 99.99, a parent allocation, depth 9, a repeated cost code, an unknown cost code (fixed message, no cell
text); give an allocated leaf a child (refused); define 4 CWAs and path v1, move one CWA with the right
`expected_version`, then with a stale one (refused); `user` refused `DefineWbsNode`, `controller` allowed (word per
row); a hidden id answers as missing; links exist and a person cannot retract them; `rollup:<scope>` queued once after
two changes; rebuild projections equals the incremental tables; `WBSNode.Defined` makes no feed card and
`CWP.Defined`-style ordinary events still do (use `Record.Created` as the control).

## Guards T11 will mutate (name file:line in the report)
Sum = 100.00 check; leaf-only allocation; depth bound; `expected_version` compare; the access word on each command;
`require_visible` on ids; the module-only link retract. Run no mutants here.

## Report requirements
Standard piece report (`docs/templates/haiku-report.md` shape, <= 60 lines): deviations first; files created; pins
updated (each, with why); acceptance output (<= 5 lines per command); guards with file:line; the feed-policy choice;
`APPROVALS` schema paths for the orchestrator; candidate learnings. Builder return to the caller <= 15 lines.

## Commit
Subject `P2-I1-S3: <imperative summary>`; body says what and why; end with the harness attribution line, then the
line `Claude-Session: https://claude.ai/code/session_01MSkuXpRjf5XzVwbAVQNqK4`. Do not discuss the trailer in the report.
No model names anywhere in committed files. Do not merge; do not push.

## Escalation triggers
- *Blocked* if: a command needs a CWP or rollup-table interface that S2 did not generate; the generic allow-list cannot express the CWA rule; the feed fix needs more than the eight names; the index removal changes any non-awp generated file; `LinkActivity` source-end check (L-P1-I1-8) needs a CWP rule (S4 owns it; note it only).

## Blocked
(builder writes here)

## Decision
(supervisor or orchestrator writes here)
