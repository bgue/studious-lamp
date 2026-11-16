# P2-PTW-T06a - CLI `tl isolation` (apply, verify, remove, link, unlink, ls, show, export)

Status: staged (written r5; base `p2/ip-r3` after PTW-T02 merges; PTW-S3 merged)
Tier: haiku
Kind: ticket
Review: full
Labels: cli, permits, confidentiality, safety
Depends on: P2-PTW-S3 (the five isolation commands, stub `cli_isolation.py`), P2-PTW-T02 (`iso_views`), P2-PTW-T04 and T05 (the permit CLI pattern; merged)
Branch: `p2/ptw-t06a-cli-isolation`
Worktree: `/home/user/wt/ptw/t06a` (from `p2/ip-r3`)

## Goal
`tl isolation apply | verify | remove | link | unlink | ls | show | export` exist. Writes are thin as `tl permit` writes are (T04): parse, build the model of `tl_mod_permits.iso_commands`, gate with `require_command`, run the handler `COMMANDS` names, print one line. Reads call `iso_views` under the signed-in viewer.

## Rules
- Fill `tl_mod_permits/cli_isolation.py` only, registering on `isolation_app` (`from tl_mod_permits.cli import isolation_app`); `cli.py` already imports it. Patterns in this package: `cli_permit_write.py` (resolve a key with `get_record` under `cf.viewer_for_actor`, `acting`, `service_errors`, `_line`) and `cli_permit_read.py` (`enter`, `require_view`, session viewer, table printing).
- `apply --project P --point TEXT --energy E --method M --lock N --tag N [--point-record KEY]` (`--point-record` resolves as `--for` of `request`: hidden or unknown is `error: no record <KEY>`); prints `applied <ISL key>  version <v>`.
- `verify KEY` and `remove KEY` take `--project P`, optional `--expected-version N`; `link PERMIT_KEY ISO_KEY` and `unlink PERMIT_KEY ISO_KEY` take `--project P` (no `expected_version`). A key resolves to a record of the right type or `error: no isolation <KEY>` / `error: no permit <KEY>` (one text for hidden, missing, other type).
- Handler refusals print as every service error prints (`error: <text>`); do not reword or catch them (the "a permit you cannot see" text is the handler's).
- Reads: `ls --project P [--state S] [--energy E] [--limit N]` (`isolation_list`; columns key, point, energy, state, lock, tag, applied by, depends; last line `n of total`; limit default 200, at most the view's bound), `show KEY --project P` (`isolation_detail`; property:value lines, empty values left out; linked permit keys as a comma list; unknown or hidden: `error: no isolation <KEY>`), `export --project P --format csv|jsonl [--state --energy]` (`isolation_export_rows` of the list, written as is; another format is a usage error). `--state` and `--energy` are checked against the module's constants (usage error, exit 2). Word for reads is `permits.view` on `project:P`, checked before any read.
- Never print a record id. No SQL; no import of `tl_api`, `tl_mcp`, `tl_web`. No clock.

## Context (read these, nothing else)
- `packages/tl-modules/permits/src/tl_mod_permits/cli_permit_write.py`, `cli_permit_read.py` (whole), `iso_commands.py` (fields), `iso_views.py` (signatures), `module.py` (COMMANDS), `cli.py`, `cli_isolation.py`
- `packages/tl-cli/tests/test_cli_permit_write.py`, `test_cli_permit_read.py` (the Cli helper), `packages/tl-modules/permits/tests/permit_world.py`

## Allowed paths
- `packages/tl-modules/permits/src/tl_mod_permits/cli_isolation.py` (edit)
- `packages/tl-cli/tests/test_cli_isolation.py` (create)
- `docs/reports/P2-PTW/T06a.md` (create)
No pin moves (the groups exist); one that does is updated here and listed (rule 12).

## Tests to add (`test_cli_isolation.py`)
1. Apply, verify by another person, link to an Approved permit, ls and show (depends 1, permit key listed), unlink, remove: each prints its line and the stored state moves.
2. The applier verifying is refused with the handler text; removing while a linked permit is Approved or Active is refused with the handler text; removing a hidden dependent prints the fixed "a permit you cannot see" text and no key.
3. Hidden point record: for the reader who cannot see it, `ls` has no row and `n of total` omits it, `show` prints the same missing text as an unknown key; the cleared reader sees it.
4. `export --format csv|jsonl` equals `isolation_export_rows` of the same list; `--format xml`, `--state Nope` exit 2.
5. A person without the write word is refused by `require_command`; without `permits.view` refused before any read; output never contains a record id.

## Acceptance
```
uv run ruff format --check packages/tl-modules/permits packages/tl-cli/tests/test_cli_isolation.py
uv run ruff check packages/tl-modules/permits packages/tl-cli/tests/test_cli_isolation.py
uv run pyright packages/tl-modules/permits/src/tl_mod_permits/cli_isolation.py packages/tl-cli/tests/test_cli_isolation.py
just gate packages/tl-cli/tests/test_cli_isolation.py packages/tl-modules/permits/tests/test_module_spec.py
```
Expected: clean; `gate: PASS`. No `just check`, no whole-repo pyright.

## Escalation triggers
A verb needs a command field the models lack; `get_record` cannot tell the record type from another; a handler needs a change.

## Report requirements
Standard report (`docs/templates/haiku-report.md`), <= 60 lines, deviations first. Commit subjects `P2-PTW-TNN: ...` (the ticket id) with the trailers the dispatch message names; no model names.

## Blocked
(implementer writes here)

## Decision
(supervisor or orchestrator writes here)
