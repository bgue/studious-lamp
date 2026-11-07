# Runbook — load the WBS, CWAs and path; compensate and reload; run the rollup; read the awp screens

Purpose: bring a project's WBS (with cost-code allocations), its construction work areas (CWA) and its path of construction into the ledger from an export, take a bad load back, and run and read the budget rollup and the five awp screens. Spec: `docs/build-spec/specs/m3-wbs-cwp.md`. Brief: §8 and §9 (`docs/brief-v0.4.md`).

## When to use
- Trigger: a project starts its work breakdown from an export, a CWA list changed, or the budget roll-up on the WBS is stale.
- Trigger: a load was wrong and must be taken back, then loaded again.

## Before you start
- Access needed: the administrator role for every `tl load` command (owner answer 12); the awp word `awp.view` to read and `awp.wbs.configure`, `awp.cwa.edit`, `awp.path.configure` or `awp.cwp.edit` to write through the commands the load and the rollup use.
- The ledger is given by `--db` or `TL_DB` (SQLite path or `postgresql://` URL). Do not paste the URL into a ticket.
- Safe to run during business hours: yes for open, extract, profile, plan and reconcile; load writes in one transaction and compensate retires in one.
- The cost codes of a WBS allocation must already exist in the project (`cost.CostCode`). A row that names one that does not exist is counted invalid.

## Load targets and loaders

| Target | Loader (`--loader`) | Input | Creates |
|---|---|---|---|
| `awp_wbs` | `awp-wbs` | CSV or XLSX with `code`, `title`, `parent`, `cost_codes` (`CODE:PCT;CODE:PCT`) | WBS nodes, parents first |
| `awp_cwa` | `awp-cwa` | CSV or XLSX with `code`, `title`, optional `sequence` | CWAs; with `sequence`, the version-1 path |

Both targets are project scope: give `--project P123`.

1. List the loaders and the targets.
   ```
   uv run tl load loaders
   uv run tl load targets
   ```
   Expected: `awp-wbs` and `awp-cwa` in the loaders; `awp_cwa  awp  project` and `awp_wbs  awp  project` in the targets.

## Steps

### Load the WBS
1. Open, extract, profile and plan the file.
   ```
   uv run tl load open wbs.csv --project P123 --loader awp-wbs
   uv run tl load extract <run> --project P123
   uv run tl load profile <run> --project P123 --show
   uv run tl load plan <run> --project P123
   ```
   Expected: `opened awp/wbs#<n> <run>`; `planned <run> new N existing M invalid K` with the first invalid lines. The reasons are fixed words, for example `allocation sums to 101.00, not 100.00`, `parent is unknown`, `depth is over 8 levels`. Fix the file and open a new run when K is not acceptable.
2. Load with the count you saw in the plan, then reconcile.
   ```
   uv run tl load load <run> --project P123 --expect-new N
   uv run tl load reconcile <run> --project P123
   uv run tl load show <run> --project P123 --report
   ```
   Expected: `loaded <run> created N ...`; `mismatches 0`. `error: the project changed since the plan` means someone changed the WBS in between: plan again.

### Load the CWAs and the path
1. Same four steps with `--loader awp-cwa` and the CWA file. A file with a `sequence` column also plans the version-1 path; a row with a `sequence` that is not a whole number, or a repeated sequence, makes the whole path wait for a fixed file.
   ```
   uv run tl load open cwas.csv --project P123 --loader awp-cwa
   uv run tl load plan <run> --project P123
   uv run tl load load <run> --project P123 --expect-new N
   uv run tl load reconcile <run> --project P123
   ```
   Expected: as above. A retired area cannot join the path (`a retired area cannot join the path`).
2. Check the path.
   ```
   uv run tl awp path show --project P123
   uv run tl awp path versions --project P123
   ```

### Compensate and reload
Compensation takes the load back. It does not delete rows.
1. Compensate the run. It retires the WBS nodes and CWAs the run created.
   ```
   uv run tl load compensate <run> --project P123 --reason "..."
   ```
   Expected: the records the run created are retired. It refuses, changing nothing, when a record is no longer there (`a record the load made is not there`), was changed after the load (`it was changed after the load`), has a package or CWP that is not void (`a package that is not void allocates to the node`, `a package that is not void names the area`), or has a node the load did not make hanging under it (`a node the load did not make hangs under it`). Settle those records by hand, then run it again.
2. The path cannot be taken back. Compensate leaves the path in place (the load reports it as irreversible). Move an area with `tl awp path move` instead.
3. Reload. A retired WBS node of the same parent is brought back by a reinstate (`WBSNode.Reinstated`), not created again. To reinstate one node by hand, use the command `ReinstateWbsNode` on `POST /commands/ReinstateWbsNode` with `node` and a `reason`; there is no `tl awp wbs` verb for it. It refuses a node that is not retired and a node whose parent is still retired: reinstate parents first.

### Read the budget rollup
1. Queue the rollup for the project, then run the queue.
   ```
   uv run tl awp rollup --project P123
   uv run tl awp worker --once
   ```
   Expected: `rollup requested  job rollup:project:P123`, then one line `ran rollup:project:P123 awp.rollup <outcome>` and `worker done: ran=1`.
2. A second request while one is queued adds nothing. A run changes at most 500 nodes; a larger tree is settled by a further run that the same job queues.
3. Read the figures.
   ```
   uv run tl awp report wbs_vs_cost_code --project P123
   uv run tl awp wbs tree --project P123
   ```
   Expected: one row per cost code and the Unallocated row; `wbs tree` lists the nodes with their rollup.

Without `--once` the worker waits for jobs until interrupted (Ctrl-C ends it cleanly).

### Read the five screens
Open the TUI on the ledger (`uv run tl-tui` with `TL_DB` set; see `docs/runbooks/tui-dev.md`), press `Ctrl+P`, type the palette id and press Enter. The palette ids are keyless entries.

| Palette id | Screen | What it shows | Keys |
|---|---|---|---|
| `cwps` | CWP register | number, subject, state, discipline, CWA, planned start, budget hours, allocated | `/` filter, `d` discipline, `s` state, `c` by CWA |
| `wbs` | WBS tree | code, title (indented by depth), budget hours, cost codes | `1`–`8` depth limit, `u` unallocated leaves |
| `cwas` | CWA register | code, title, position on the path, CWP count, budget hours | `r` shows retired areas |
| `path` | Path of construction | the steps of one version and reasons | `[` `]` previous and next version, `v` compare with the previous |
| `packages` | External packages | EWP and PWP: number, status, forecast, actual, constraint source | |

The CWP record's Details tab shows the same fields as the register row.

Reads need `awp.view`. A record you may not read is absent from every screen, not shown as hidden.

## Verify
- `uv run tl load show <run> --project P123` is Reconciled with `mismatches 0`.
- `uv run tl awp wbs tree --project P123` lists the loaded codes; `uv run tl awp cwa ls --project P123` lists the areas, retired ones flagged.
- After a compensate, `uv run tl awp wbs show <code> --project P123` shows the node retired.

## Known limits
- **F6, rename on reload is not handled.** A reload keeps the title a node already has; a change of title in the file is not written. Use `uv run tl awp wbs revise <code> --project P123 --title "..."` (access `awp.wbs.configure`) for a rename.
- **F7, a CWA reload is not handled.** A CWA code the project still holds, retired or not, counts as existing, so a reload does not bring a retired area back. No command reinstates a CWA (`ReviseCwa` does not un-retire it); the area needs a new code or a fix by the office.
- The path is written once. A second load does not re-sequence an existing path (`existing`); re-sequence with `uv run tl awp path move <cwa> --project P123 --to <n> --reason <code>`.

## Roll back
- Before the load: `uv run tl load void <run> --project P123 --reason "..."`.
- After the load: the compensate step above. The path stays.

## Related
- `docs/build-spec/specs/m3-wbs-cwp.md` (§4 rollup, §6 imports, §8 screens), `docs/runbooks/legacy-load.md` (the load steps), `packages/tl-modules/awp/README.md` (interface), `packages/tl-modules/awp/AGENTS.md` (rules), `docs/runbooks/tui-dev.md`.
