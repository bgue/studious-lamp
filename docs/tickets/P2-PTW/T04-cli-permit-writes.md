# P2-PTW-T04 - CLI `tl permit` write verbs

Status: ready (written r4; base `p2/ip-r3`; PTW-S2 and T01 merged)
Tier: haiku
Kind: ticket
Review: full
Labels: cli, permits
Depends on: P2-PTW-S2 (the ten commands, `COMMANDS`, stub `cli_permit_write.py`), P2-PTW-T01 (views, used to resolve keys), merged
Branch: `p2/ptw-t04-cli-permit-writes`
Worktree: `/home/user/wt/ptw/t04` (from `p2/ip-r3`)

## Goal
`tl permit request | approve | reject | issue | revalidate | suspend | resume | handback | close | cancel` exist, each one thin: parse options, build the command model of `tl_mod_permits.commands`, gate it with `require_command`, run the handler the `COMMANDS` table names, print one line. The guards (approver is not the requester, issue blockers, validity, who may resume) are the handlers'; none is repeated here.

## Rules
- Fill `tl_mod_permits/cli_permit_write.py` only; register on `permit_app` from `tl_mod_permits.cli` (`@permit_app.command("request")` ...). `cli.py` already imports this file at its bottom; do not edit it. Pattern: `tl_cli/punch_write.py` (`_handler`, `_execute`, `acting`, `scope_of`, `service_errors`, `_line`), module-package files may import `tl_cli.*`.
- `request --project P --type TYPE --area A --location TEXT --description TEXT --holder H --from DATE --until DATE [--for KEY]`: `--for` resolves with `get_record` under the actor's viewer (`cf.viewer_for_actor`) to `for_record_id` (hidden or unknown: `error: no record <KEY>`, same text). Prints `requested <key>  version <v>`.
- The other nine take `KEY` (the key a read prints), `--project P`, `--actor`, optional `--expected-version N`; the key resolves with `get_record` as the actor reads it and must be of type `permits.Permit` (else `error: no permit <KEY>`, the same text for hidden, missing, other type). `reject`, `suspend`, `cancel` need `--reason`; `handback` needs `--note` (`handback_note`); `issue` takes repeated `--tick ID` (`precautions`). Prints `<verb-past> <key>  version <v>`.
- The handler's refusals print as the CLI prints every service error (`error: <text>`, `service_errors()`); do not catch or reword them.
- No SQL; no import of `tl_api`, `tl_mcp`, `tl_web`.

## Context (read these, nothing else)
- `packages/tl-cli/src/tl_cli/punch_write.py` lines 1-90 and 140-230 (the verb pattern), `packages/tl-cli/src/tl_cli/derive_support.py` (names only)
- `packages/tl-modules/permits/src/tl_mod_permits/commands.py` (fields), `module.py` lines 55-90 (`COMMANDS`), `cli.py`, `cli_permit_write.py`
- `packages/tl-modules/permits/tests/permit_world.py`, `packages/tl-cli/tests/test_cli_punch.py` lines 1-110 (the `Cli` helper pattern)

## Interfaces (verbatim)
```python
COMMANDS: tuple[PermitCommand, ...]   # PermitCommand(model, handler, access, meta); model.__name__ is the command name
permit_app = typer.Typer(no_args_is_help=True, help="Permits to work.")   # tl_mod_permits.cli
```

## Allowed paths
- `packages/tl-modules/permits/src/tl_mod_permits/cli_permit_write.py` (edit)
- `packages/tl-cli/tests/test_cli_permit_write.py` (create)
- `docs/reports/P2-PTW/T04.md` (create)
No pin moves (the groups exist); one that does is updated here and listed (rule 12).

## Tests to add (`test_cli_permit_write.py`; ledger from `permit_world.World`, loaded by path as `test_cli_punch.py` loads its world)
1. Walk one permit through request, approve, issue (`--tick` ids of the type), revalidate, suspend, resume, handback, close by the people who may; each prints the line and the stored state moves (read `cur_workflow_state`).
2. `reject` and `cancel` paths with reasons; a missing `--reason` is a usage error.
3. The requester cannot approve (`error:` from the handler, same text as the handler's); an actor without the word is refused by `require_command`.
4. A hidden `--for` key, an unknown key and a key of another type print the same text; a key of a restricted permit for a reader who cannot see it prints the missing-permit text.
5. Output never prints a record id (`HEX32`/ULID grep as `test_cli_punch.py` does).
6. `tl permit --help` lists the ten verbs (and, once T05 merges, the reads).

## Acceptance
```
uv run ruff format --check packages/tl-modules/permits packages/tl-cli/tests/test_cli_permit_write.py
uv run ruff check packages/tl-modules/permits packages/tl-cli/tests/test_cli_permit_write.py
uv run pyright packages/tl-modules/permits packages/tl-cli/tests/test_cli_permit_write.py
just gate packages/tl-cli/tests/test_cli_permit_write.py packages/tl-modules/permits/tests/test_module_spec.py
```
Expected: clean; `gate: PASS`. No `just check` (the orchestrator runs it at DONE), no whole-repo pyright.

## Escalation triggers
A verb needs a command field the models lack; `get_record` cannot tell a permit from another type; a handler needs a change.

## Report requirements
Standard report (`docs/templates/haiku-report.md`), <= 60 lines, deviations first. Commit subjects `P2-PTW-T04: ...` with the trailers the dispatch message names; no model names.

## Blocked
(implementer writes here)

## Decision
(supervisor or orchestrator writes here)
