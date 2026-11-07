# P2-I3-T08a — `tl load` verbs take `--company` (a company run can be advanced past open)

Status: ready
Tier: haiku
Kind: ticket
Review: full
Labels: cli
Depends on: nothing new (p2/i3 head). Unblocks T08 clause 1 (`docs/reports/P2-I3/T08.md`, Blocked).
Branch: `p2/i3-t08a-load-company`   (from p2/i3)

## Goal
`tl load open ... --company` works today, but every later verb takes only `--project ID` and builds
`project:<ID>`, so a company run (the 50-item library, loader `mat-items`) cannot be extracted,
profiled, planned, loaded, reconciled or shown. Give every run verb the same choice `open` has:
`--project ID` or `--company`, exactly one. This is also wave-0 follow-up Q9 ("a company load run
cannot advance past open").

## Interfaces (exist; use, do not change)
- `packages/tl-cli/src/tl_cli/derive_support.py`: `OptProject` (optional `--project`), and
  `scope_of(project, company)` -> `"company"` or `"project:<ID>"`; it fails with
  "give --project ID or --company, and not both" when both or neither are given.
- `packages/tl-cli/src/tl_cli/load.py` `open_run`: the pattern to copy (`project: OptProject = None`,
  `company: Annotated[bool, typer.Option("--company", help=...)] = False`, `scope = scope_of(project, company)`).
- `LoadService` already takes the scope string; no service change.

## Steps
1. In `load.py`, add one module-level `_Company` alias (the `--company` option of `open_run`, help
   "A company run (not a project one).") and use it in `open_run` too.
2. For each verb that now takes `project: Project` (extract, profile, bronze, plan, load, reconcile,
   compensate, void, ls, show): change it to `project: OptProject = None, company: _Company = False`,
   compute `scope = scope_of(project, company)` once at the top (before any service call) and pass
   `scope` where `_scope(project)` was. Delete `_scope` when unused. Keep option order and every
   other option and output line unchanged. Update the app help to "...into a project or the company."
3. Tests in `packages/tl-cli/tests/test_cli_load_targets.py` (same fixtures as the `open` tests there):
   a. a company target run (register one the way `test_targets_lists_a_registered_company_target...`
      does, or use the installed `mat-items` loader with `samples/items.csv` if the materials package
      is on this tree) goes open -> extract -> profile -> plan -> load -> reconcile -> show with
      `--company`, each exit 0; reconcile prints `mismatches 0`.
   b. `tl load extract RUN` with neither option, and with both, exits non-zero with the
      `scope_of` message.
   c. an existing project run still works with `--project` (one verb is enough: `ls --project P123`).

## Allowed paths
- `packages/tl-cli/src/tl_cli/load.py`
- `packages/tl-cli/tests/test_cli_load_targets.py`
- `docs/reports/P2-I3/T08a.md` (create)
- `docs/reference/cli*` only if `just check` reports CLI reference drift (regenerate with the repo's tool, never by hand)

## Acceptance
- `NODE_OPTIONS=--max-old-space-size=6144 just check` exit 0
- `just gate packages/tl-cli/tests/test_cli_load_targets.py packages/tl-cli/tests/test_cli_load.py | tail -45 | tee .gate/summary.txt` ends `gate: PASS`
- Report: the commands above, 5 decisive lines each; the exact reconcile line of 3a.
