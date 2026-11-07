# P2-I1-T04a — `tl awp` read commands

Status: ready
Tier: haiku
Review: full
Labels: cli
Depends on: T10 (merged)
Branch: `p2/i1-t04a-cli-reads`
Worktree: `/home/user/wt/i1-t04a` (from `p2/i1` head)

## Goal
`tl awp cwp ls|show`, `tl awp cwa ls`, `tl awp wbs tree|show`, `tl awp path show|versions` and `tl awp package ls` print the
awp read views, one fact per line, two spaces between fields. The group `tl awp` exists and is registered. Reports (T04b),
write verbs, `rollup` and `worker` (T04c) join later through `register(app)` functions; none of them is here.

## Brief references (pasted)
Output rules of `tl cost` (`cost_read.py`): `Project` option, `service_errors()`, `cell(value, width)` prints `-` for none,
`open_uow(db, readonly=True)`, an empty list prints one line `no <things> in project <P>`. Formats (exact):
- `cwp ls [--state S] [--discipline D] [--cwa C]`: `cwps: <n>` then `<number>  <state>  <discipline or ->  <cwa or ->  <budget h or ->  <title ≤ 60>`.
- `cwp show NUMBER`: `cwp <number>`, `title`, `state`, `discipline`, `cwa`, `planned <start or -> to <finish or ->`, `budget <h or ->`,
  `contractor <text or ->`, `allocations <n>` and `  <wbs code>  <percent>` each, `packages <n>` and `  <package no>  <kind>  <status or ->`
  each, `activities <n>` and `  <ref_key>  <status>` each. Unknown, hidden or void: `error: no CWP <number>` exit 1 (`fail(...)` from derive_support).
- `cwa ls`: `cwas: <n>` then `<code>  <title ≤ 60>  <location or ->  <retired or active>`.
- `wbs tree [--depth N]`: `wbs nodes: <n>` then `<code>  <indent two spaces per depth><title ≤ 50>  <total h or ->  <cost codes: 'code=hours' joined by ' ' or ->`.
- `wbs show CODE`: `wbs <code>`, `title`, `parent <code or ->`, `depth`, `retired yes|no`, `total <h or ->`, then `  <cost code>  <hours>` per line.
- `path show [--version N]`: `path version <v> of <current>` then `<position>  <cwa or ->  <reason or ->  <actor>  <recorded_at>`; none: `no path of construction in project <P>`.
- `path versions`: `<version>  <recorded_at>  <actor>  steps <n>  <current or ->`.
- `package ls [--kind EWP|PWP]`: `packages: <n>` then `<package no>  <kind>  <status or ->  forecast <date or ->  actual <date or ->  <constraint yes|no>`.
Quantities print with one decimal (`4,200.0`). The CLI reads as the default (lowest) viewer; do not widen it.

## Interfaces (verbatim)
```python
# tl_mod_awp.views: cwp_list(conn, scope, *, state=None, discipline=None, cwa=None); cwp_detail(conn, scope, number) -> CwpDetail|None;
#  cwa_list; wbs_tree(conn, scope, *, depth=None); wbs_detail(conn, scope, code) -> WbsRow|None; path(conn, scope, version=None) -> PathView|None;
#  path_versions; package_list(conn, scope, *, kind=None)   # models: see the class bodies in views.py
# tl_cli.cost_read.register(app: typer.Typer) -> None   # pattern: app.command(name)(function)
# tl_cli.main: `app.add_typer(cost.app, name="cost")` (line 150) and `cost,` in the import list (line 52)
```
Sub-groups: `cwp_app = typer.Typer(no_args_is_help=True)` etc. in `awp_read.py`; `register(app)` does `app.add_typer(cwp_app, name="cwp")`.

## Context (read these, nothing else)
- `packages/tl-cli/src/tl_cli/cost_read.py`, `packages/tl-cli/src/tl_cli/cost.py` lines 1-45 (group wiring)
- `packages/tl-cli/src/tl_cli/main.py` lines 40-60 and 140-160
- `packages/tl-modules/awp/src/tl_mod_awp/views.py` (class bodies only)
may explore: `.accept/p2-i1.db`; `tl_cli/derive_support.py` (`Project`, `cell`, `fail`, `service_errors`)

## Allowed paths
- `packages/tl-cli/src/tl_cli/awp_read.py` (create), `packages/tl-cli/src/tl_cli/awp.py` (create: `app = typer.Typer(help="Work packaging: ...",
  no_args_is_help=True)` then `awp_read.register(app)`), `packages/tl-cli/src/tl_cli/main.py` (import + `app.add_typer(awp.app, name="awp")`)
- `docs/reference/` only if `just check` reports CLI-reference drift (regenerate, list it)
- `dev/accept/P2-I1/T04a.py` (create), `docs/reports/P2-I1/T04a.md` (create)

## Acceptance
```
uv sync --all-packages
NODE_OPTIONS=--max-old-space-size=6144 just check
uv run python dev/accept/P2-I1/S4.py --keep .accept/p2-i1.db     # if the file is missing
uv run tl awp cwp ls --db .accept/p2-i1.db --project P123
uv run python dev/accept/P2-I1/T04a.py --db .accept/p2-i1.db
just gate packages/tl-cli/tests/test_help.py     # or the CLI help/registry test `grep -l "add_typer" packages/tl-cli/tests` finds; at most 2 files
```
`T04a.py` runs each verb through `typer.testing.CliRunner` (`tl_cli.main.app`, `--db`) and prints `PASS <verb> <first line>`; checks `cwps: 6`,
`cwas: 4`, `wbs nodes: 9`, `path version 1 of 1`, `packages: 0`, a bad CWP number exits 1, `--state Planned` gives 2 rows. Ends `T04a ok`.
Expected: `just check` clean; every PASS; gate PASS.

## Tests to add
none (T11 writes `packages/tl-cli/tests/test_cli_awp.py`).

## Report requirements
`docs/reports/P2-I1/T04a.md` <= 60 lines, <= 5 decisive output lines per command; deviations first; pins updated listed (rule 12).
Subject `P2-I1-T04a: ...`; no model names; commit trailer = the harness attribution line, then
`Claude-Session: https://claude.ai/code/session_01MSkuXpRjf5XzVwbAVQNqK4`.

## Escalation triggers
- Stop and write *Blocked* if a view lacks a field a format needs, if a pinned CLI test breaks for a reason other than the new group, or if the
  group needs a `tl_cli` file outside Allowed paths.

## Blocked
(implementer writes here)

## Decision
(supervisor writes here)
