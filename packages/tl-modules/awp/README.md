# awp (`tl_mod_awp`)

The awp module (M3, part 1) keeps the WBS and its cost-code allocation, the path of construction, the construction work areas (CWA), the construction work packages (CWP) and the owner's EWP and PWP references for a project. It implements the budget rollup from CWP to WBS node to cost code (§1 scope of `docs/build-spec/specs/m3-wbs-cwp.md`; brief §8 and §9 for the packaging context, `docs/brief-v0.4.md`).

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
| all reads | `awp.view` | `wbs tree`, `wbs show`, `cwp ls`, `cwp show`, `cwa ls`, `path show`, `path versions`, `package ls`, `report` |

### Load targets and loaders

| Target | Loader (`tl load open --loader`) | Scope | Creates |
|---|---|---|---|
| `awp_wbs` | `awp-wbs` (CSV, XLSX) | project | WBS nodes with `cost_codes` as `CODE:PCT;CODE:PCT` |
| `awp_cwa` | `awp-cwa` (CSV, XLSX) | project | CWAs, and the version-1 path when a `sequence` column is present |

Both are create-only and compensable, except the path, which cannot be taken back. Procedure: `docs/runbooks/awp.md`.

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

The CWP record's Details tab uses the same renderer as the panels (`tl_tui/details/awp.py`).

### MCP read tools

From `packages/tl-mcp/src/tl_mcp/awp_tools.py`. Each is authorised as `mcp.<tool>` (`tl_mcp/identity.py`).

| Tool | Arguments | Returns |
|---|---|---|
| `list_cwps` | `project`, `state?`, `discipline?`, `cwa?` | CWPs by number, void ones left out |
| `get_cwp` | `project`, `number` | one CWP with allocation, packages, activities |
| `wbs_tree` | `project`, `depth?` (1 to 20) | WBS nodes depth-first with rollup |
| `path_of_construction` | `project`, `version?` | the path at one version, or null |
| `propose_cwp` | `project`, `discipline`, `title`, `cwa_code`, `planned_start?`, `planned_finish?`, `budget_hours?`, `summary?` | a pending proposal, **not a write**: a person who may edit CWPs accepts it in the review queue |

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
```

`tl load targets` lists `awp_cwa` and `awp_wbs`.

## Configuration

| Setting or env var | Default | Notes |
|---|---|---|
| `TL_DB` | the root `--db` | SQLite path or `postgresql://` URL; `tl awp … --db` overrides it |
| access words | `schema/settings/access-words.yaml` | the `awp.*` rows |
| `tl awp worker --once` | off | without it the worker waits until interrupted |

Limits (`limits.py`): WBS depth at most 8 levels, at most 5 000 nodes per project; path at most 500 steps; an allocation list at most 20 lines; CWP quantities at most 50 rows.

## Rules specific to this package
See `AGENTS.md` in this directory.

## Status
Introduced in P2-I1 (S3 to S7). Last interface change: P2-I1 S7 (`ReinstateWbsNode`, `WBSNode.Reinstated`; D58 in `docs/tickets/P2-I1/STATE.md`).
