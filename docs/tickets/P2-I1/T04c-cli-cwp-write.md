# P2-I1-T04c — `tl awp` write verbs for CWPs and packages

Status: ready (T04a, T04b, S4, S5 merged)
Tier: haiku
Review: full
Labels: cli
Depends on: T04a (merged)
Branch: `p2/i1-t04c-cwp-write`
Worktree: `/home/user/wt/i1/t04c` (from `p2/i1` head)

## Goal
The CWP life cycle and the EWP/PWP packages run from `tl awp ...`, each verb one command model of `AWP_COMMANDS` and its handler, gated by `require_command`. WBS, CWA, path verbs, `rollup` and `worker` are T04d (diff size).
The CLI parses and prints; the handlers decide. Mounting `awp_write.register(app)` in `tl_cli/awp.py` is supervisor glue.

## Verbs (fixed; every one takes `--project` and `--actor`; `CWP` is the CWP number, resolved with `views.cwp_detail(conn, scope, number).id`, none -> `error: no CWP 'x' in project P`, exit 1)
```
cwp create --discipline D --title T --cwa CODE [--planned-start D --planned-finish D --budget-hours H --contractor T --qty COMMODITY:QTY:UOM ...]   -> CreateCwp; prints `created CWP <result.key>`
cwp revise CWP [--title --cwa --planned-start --planned-finish --budget-hours --contractor --qty ...]                                              -> ReviseCwp
cwp allocate CWP --wbs CODE:PERCENT ...  (repeatable, at least one; replaces the allocation)                                                       -> AllocateCwpToWbs (WbsLine)
cwp move CWP ACTION [--reason T]  ACTION in start-development start-execution complete release return close reopen                                  -> StartCwpDevelopment StartCwpExecution CompleteCwp ReleaseCwp ReturnCwp CloseCwp ReopenCwp
   (return and reopen need --reason, else `error: ACTION needs --reason`; release sets expected_version from get_record_by_id(uow, id)["version"])
cwp void CWP --reason T                                                                                                                              -> VoidCwp (field `id`)
package record --type ewp|pwp --number N --title T --constraint-source/--no-constraint-source [--status T --forecast D --actual D --source-system S] -> RecordExternalPackage (package_type, package_no)
package update NUMBER [--status --forecast --actual --constraint-source/--no-constraint-source]                                                      -> UpdateExternalPackage (id from views.package_list by package_no)
package void NUMBER --reason T                                                                                                                       -> VoidExternalPackage
```
Every write prints `<verb> <CWP or NUMBER>  version <result.version>` (create excepted). A malformed `--wbs` or `--qty` (not `A:B[:C]`) is `error: ...`, exit 1, before any ledger is opened. Model validation errors and handler refusals go through `service_errors()`; `require_command(uow, command)` sits between building the command and the handler, as `tl_cli/cost.py` lines 96-115 do.

## Interfaces (verbatim)
```python
# tl_mod_awp.commands: CreateCwp ReviseCwp AllocateCwpToWbs StartCwpDevelopment StartCwpExecution CompleteCwp ReleaseCwp ReturnCwp CloseCwp ReopenCwp VoidCwp RecordExternalPackage UpdateExternalPackage VoidExternalPackage 
#  QuantityRow(commodity, qty, uom) WbsLine(wbs_code, percent) ; AWP_COMMANDS: tuple[AwpCommand(model, handler, access)]  -> handler = next(c.handler for c in AWP_COMMANDS if c.model is cls)
#  every command: actor, source, scope (+ the fields above); CommandResult(stream_id, key, version, events)
# tl_cli.derive_support: Project, Actor, DEV_ACTOR, SOURCE, acting(db, actor), fail, service_errors, scope_of ; tl_cli.session.require_command(uow, command)
# tl_core.services.queries.get_record_by_id(uow, id) -> dict|None (has "version"); tl_adapters.db.open_uow(db) ; tl_mod_awp.views.cwp_detail / package_list
# register(app): sub-Typers `cwp` and `package` on the awp app (pattern tl_cli/awp_read.py `register`)
```

## Context (read these, nothing else)
- `packages/tl-cli/src/tl_cli/cost.py` lines 1-60 and 96-120, `packages/tl-cli/src/tl_cli/awp_read.py` lines 1-60 and the `register` function
- `packages/tl-modules/awp/src/tl_mod_awp/commands.py` lines 230-470 (class bodies) and 466-500 (`AWP_COMMANDS`)
- `dev/accept/P2-I1/S4.py` lines 155-200 (`people`: sue superuser, uma user) and 300-340
may explore: `.accept/p2-i1.db`

## Allowed paths
- `packages/tl-cli/src/tl_cli/awp_write.py` (create; not `awp.py`, `main.py`, any pyproject)
- `dev/accept/P2-I1/T04c.py` (create), `docs/reports/P2-I1/T04c.md` (create)

## Acceptance
```
uv sync --all-packages
NODE_OPTIONS=--max-old-space-size=6144 just check            # background, > 120 s
uv run python dev/accept/P2-I1/S4.py --keep .accept/p2-i1.db   # if the file is missing
uv run python dev/accept/P2-I1/T04c.py --db .accept/p2-i1.db
```
`T04c.py`: copy the seed to a temp file; `CliRunner` on a local `typer.Typer()` with `awp_write.register(app)` and the root `--db` as `tl_cli.main` passes it (read `T04b.py`). As the superuser of the seed: `cwp create` prints `created CWP ...` and `awp_read` shows it (`PASS create`);
`cwp revise` changes the title (`PASS revise`); `cwp allocate --wbs 1.1:60 --wbs 1.2:40` and a read shows two allocations (`PASS allocate`); `cwp move ... start-development` exits 0 and the state reads In development (`PASS move`);
`package record` then `package update` then `package void` (`PASS package`); `cwp void` (`PASS void`). Refusals, each exit 1 with `error:`:
the plain `user` of the seed runs `cwp move ... release` (`PASS forbidden`), unknown CWP (`PASS unknown`), `--wbs 1.1` malformed (`PASS parse`), `return` without `--reason` (`PASS reason`). Ends `T04c ok`. No pytest, no `just gate`.

## Tests to add
none (T11: `packages/tl-cli/tests/test_awp_write.py`).

## Report requirements
`docs/reports/P2-I1/T04c.md` <= 60 lines; deviations first; one line per verb with a sample output line (12 lines). Subject `P2-I1-T04c: ...`; no model names; commit trailer = the harness attribution line, then `Claude-Session: https://claude.ai/code/session_01MSkuXpRjf5XzVwbAVQNqK4`.

## Escalation triggers
- Stop if a verb needs a handler or field `commands.py` does not have; never add a command, an access word or a view field.
- Stop if the CLI's `--actor` hook refuses the seed's `user:sue`/`user:uma`: write what it says.

## Blocked
(implementer writes here)

## Decision
(supervisor writes here)
