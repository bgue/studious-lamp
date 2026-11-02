# P2-I1-T04d — `tl awp` write verbs for the WBS, the CWAs and the path of construction

Status: ready (T04a, T04b, T04c, S3, S4 merged; r8 moved `rollup` and `worker` to T04e)
Tier: haiku
Review: full
Labels: cli
Depends on: T04c (merged)
Branch: `p2/i1-t04d-wbs-cwa-path`
Worktree: `/home/user/wt/i1/t04d` (from `p2/i1` head)

## Goal
The WBS, the work areas and the path of construction are maintained from `tl awp ...`, each verb one command model of `AWP_COMMANDS` and its handler, gated by `require_command`. The CLI parses and prints; the handlers decide. Mounting `awp_write2.register(app)` in `tl_cli/awp.py` is supervisor glue.
Build on `tl_cli/awp_write.py` (T04c, merged, read it whole; do not edit it): import its `_execute`, `_line`, `_parts`, `_group` instead of copying them.

## Verbs (fixed; every one takes `--project` and `--actor`; an unknown code is `error: no WBS node 'x' in project P` / `no CWA 'x' ...` / `no path ...`, exit 1)
```
wbs define CODE --title T [--parent CODE] [--position N]                          -> DefineWbsNode; prints `defined WBS CODE`
wbs revise CODE [--title T] [--parent CODE | --root] [--position N]               -> ReviseWbsNode (node = views.wbs_detail(conn, scope, CODE).id; send only the options given: model_fields_set; --root sends parent_code null)
wbs retire CODE --reason T                                                         -> RetireWbsNode
wbs map CODE (--cost-code CODE:PERCENT ... | --clear)                              -> MapWbsToCostCodes (CostCodeLine(cost_code, percent); --clear sends allocations []; neither -> `error: give --cost-code or --clear`)
cwa define CODE --title T [--location T]                                           -> DefineCwa; prints `defined CWA CODE`
cwa revise CODE [--title T] [--location T | --clear-location]                      -> ReviseCwa (cwa = id from views.cwa_list by code)
cwa retire CODE --reason T                                                         -> RetireCwa
path define --step CWA[:REASON] ...  (repeatable, at least one, in order)          -> DefinePathOfConstruction (PathStepIn(cwa_code, reason_code)); prints `defined path  version 1`
path move CWA --to N --reason R [--note T]                                         -> MoveCwaInPath (expected_version = views.path(conn, scope).current_version; no path -> `error: no path ...`)
```
Every write but `define` prints `<verb> <CODE>  version <result.version>` (`_line`; `path move` prints `move <CWA>  version <n>`). A malformed `--cost-code` or `--step` is `error: ...`, exit 1, before any ledger is opened (`_parts`). Handler refusals and model errors go through `service_errors()`.

## Interfaces (verbatim)
```python
# tl_mod_awp.commands: DefineWbsNode(code, title, parent_code, position) ReviseWbsNode(node, title, parent_code, position) RetireWbsNode(node, reason)
#  MapWbsToCostCodes(node, allocations: list[CostCodeLine]) CostCodeLine(cost_code, percent: str) DefineCwa(code, title, location_text) ReviseCwa(cwa, title, location_text)
#  RetireCwa(cwa, reason) DefinePathOfConstruction(steps: list[PathStepIn]) PathStepIn(cwa_code, reason_code|None) MoveCwaInPath(cwa_code, to_position, reason_code, note, expected_version)
#  every command: actor, source, scope; AWP_COMMANDS; access words awp.wbs.configure (wbs, RetireCwa), awp.cwa.edit (cwa define/revise), awp.path.configure (path)
# tl_mod_awp.views: wbs_detail(conn, scope, code) -> WbsRow|None (.id) ; cwa_list(conn, scope) -> list[CwaRow] (.id .code) ; path(conn, scope, version=None) -> PathView|None (.current_version)
# tl_cli.awp_write: _execute(db, build) -> CommandResult ; _line(verb, number, result) ; _parts(value, count, option, shape) ; _group(app, name, help) ; register pattern at the end of the file
# tl_cli.derive_support: Project Actor DEV_ACTOR SOURCE acting fail scope_of service_errors
```
`register(app)`: join the `wbs`, `cwa` and `path` groups that `awp_read.register` made (`_group`), then add the verbs; call order is glue's.

## Context (read these, nothing else)
- `packages/tl-cli/src/tl_cli/awp_write.py` (all), `dev/accept/P2-I1/T04c.py` (the script pattern)
- `packages/tl-modules/awp/src/tl_mod_awp/commands.py` lines 92-230 (class bodies)
- `dev/accept/P2-I1/S4.py` lines 155-200 (people: `user:sue` superuser, `user:uma` plain user) and the cost code names it loads
may explore: `.accept/p2-i1.db`

## Allowed paths
- `packages/tl-cli/src/tl_cli/awp_write2.py` (create; not `awp_write.py`, `awp.py`, `main.py`, any pyproject)
- `dev/accept/P2-I1/T04d.py` (create), `docs/reports/P2-I1/T04d.md` (create)

## Acceptance
```
uv sync --all-packages
NODE_OPTIONS=--max-old-space-size=6144 just check            # background, > 120 s
uv run python dev/accept/P2-I1/S4.py --keep .accept/p2-i1.db   # if the file is missing
uv run python dev/accept/P2-I1/T04d.py --db .accept/p2-i1.db
```
`T04d.py`: copy the seed to a temp file; `CliRunner` on a local `typer.Typer()` with `awp_read.register(app)` then `awp_write2.register(app)`, root `--db` as `tl_cli.main` passes it, `TL_ENV=dev` and a temp `TL_SESSION_FILE` (as `T04c.py`). As `user:sue`, reading back with `tl_mod_awp.views`:
`wbs define 9 --title Spare` and `wbs define 9.1 --parent 9 --title Spare leaf` (`PASS wbs define`); `wbs map 9.1 --cost-code <a seed cost code>:100` (`PASS wbs map`) and `--clear` (`PASS wbs clear`); `wbs revise 9.1 --title ...` (`PASS wbs revise`); `wbs retire 9.1 --reason ...` (`PASS wbs retire`);
`cwa define SP --title Spare area`, `cwa revise SP --location ...`, `cwa retire SP --reason ...` (`PASS cwa`); `path move <a seed CWA> --to 1 --reason <a PathReason code of the seed>` makes version 2 (`PASS path move`); `path define --step A --step B:Access` on the seed is refused, exit 1 `error:` (`PASS path redefine`).
Refusals, each exit 1 with `error:`: `user:uma` runs `wbs define` (`PASS forbidden`), unknown WBS code (`PASS unknown`), `--cost-code 100` malformed (`PASS parse`), `wbs map 9.1` with neither option (`PASS map args`). Ends `T04d ok`. No pytest, no `just gate`.

## Tests to add
none (T11: `packages/tl-cli/tests/test_awp_write2.py`).

## Report requirements
`docs/reports/P2-I1/T04d.md` <= 60 lines; deviations first; one line per verb with a sample output line (9 lines). Subject `P2-I1-T04d: ...`; no model names; commit trailer = the harness attribution line, then `Claude-Session: https://claude.ai/code/session_01MSkuXpRjf5XzVwbAVQNqK4`.

## Escalation triggers
- Stop if a verb needs a handler or field `commands.py` does not have; never add a command, an access word or a view field.
- If the handler accepts a second `path define` on the seed, report what it did; do not change the expectation to match.
- Stop if the CLI's `--actor` hook refuses `user:sue`/`user:uma`: write what it says.

## Blocked
(implementer writes here)

## Decision
(supervisor writes here)
