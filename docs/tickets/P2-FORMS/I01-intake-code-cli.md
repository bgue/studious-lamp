# P2-FORMS-I01 — `tl intake code issue|revoke`: the documented way to issue an intake code

Status: ready
Tier: haiku
Kind: ticket
Review: full  (a security path: it makes the secret; S7c security review rule)
Labels: cli, tests
Depends on: S7c merged (`IssueIntakeCode`, `RevokeIntakeCode`, `tl_core/qr/codes.py`); nothing else. The poster label that this item first named moves to I08 (it needs the QR renderer).
Branch: `p2/forms-i01-code-cli`
Worktree: harness-created under `/home/user/wt/forms/i01` (from `p2/ip` head)

## Goal
`tl intake code issue` makes a fresh code with `new_code()`, sends only `code_hash(code)` to `IssueIntakeCode`, and prints the grouped code once. This is the only supported way to issue a code
(S7c review: the server never sees the code, a caller could choose a weak one; the CLI never lets the person choose). `tl intake code revoke` revokes by id. The group `tl intake` is created here
with these two verbs; I04 adds `ls`, `show`, `accept`, `reject`, `purge` to the same group.

## Brief references (pasted)
`IssueIntakeCode(actor, source, scope, code_hash, template_id, context_id?, heading, controller_role, expires_on)`; word `forms.intake.issue`; refusals are fixed texts (`MSG_UNKNOWN`, `MSG_NOT_PUBLISHED`,
`MSG_NOT_INTAKE`, `MSG_EXPIRY`, `MSG_CODE_TAKEN`, `MSG_PROJECT`). `RevokeIntakeCode(record_id, reason 1..300, expected_version?)`; same word. Result carries `stream_id`. Code: 16 symbols, `grouped(code)` is `7KQ2-M9XA-4TTC-P0HV`.
The code is never logged, stored, put in an event, an error text or argv.

## Interfaces
```python
# packages/tl-cli/src/tl_cli/intake.py (create): `app = typer.Typer(help=...)`, a `code` sub-group; `register()` pattern of tl_cli/punch.py
# packages/tl-cli/src/tl_cli/intake_code.py (create): the two verbs
#   tl intake code issue --template ID --heading TEXT --controller-role ROLE --expires-on YYYY-MM-DD [--context KEY] --project P [--actor A]
#   tl intake code revoke ID --reason TEXT --project P [--actor A]
```
Output: issue prints exactly two lines to stdout, `issued <record id>  expires <date>` then `code <grouped code>`; and one line to stderr `this code is shown once and cannot be recovered`. Revoke prints `revoked <id>`.
There is **no** `--code` option and no way to read the code later (a test proves `--code` is a usage error, exit 2). `--context KEY` is resolved to a record id as the actor's viewer reads it (copy `_source_id` of `punch_write.py`: a hidden or absent key is `no record <key>`).
Execution follows `punch_write.py` exactly (`_execute`, `_model`, `require_command`, `service_errors`, `acting`, `scope_of`, `fail`), with `FORMS_COMMANDS` from `tl_mod_forms.module`. A refusal is `error: <the fixed text>` and exit 1 (as the punch verbs); nothing prints a code or hash on failure.

## Context (read these, nothing else)
- `packages/tl-cli/src/tl_cli/punch_write.py` (whole; the pattern), `packages/tl-cli/src/tl_cli/punch.py` (group), `packages/tl-cli/src/tl_cli/derive_support.py` (helpers signatures)
- `packages/tl-modules/forms/src/tl_mod_forms/commands.py` (lines of `IssueIntakeCode`, `RevokeIntakeCode`), `packages/tl-core/src/tl_core/qr/codes.py`
- `packages/tl-cli/tests/test_cli_punch.py` (test style; the world is loaded by path from `packages/tl-modules/forms/tests/forms_world.py`)
may explore: `packages/tl-cli/src/tl_cli/main.py` (one `add_typer` line near `punch`)

## Allowed paths
- `packages/tl-cli/src/tl_cli/intake.py`, `.../intake_code.py` (create); `packages/tl-cli/src/tl_cli/main.py` (one import name and one `app.add_typer(intake.app, name="intake")  # P2-FORMS`, nothing else)
- `packages/tl-cli/tests/test_cli_intake_code.py` (create)
- Pinned CLI lists (command group lists, help snapshots) only where they fail because the group exists; name each with old and new count in the report
- `docs/reports/P2-FORMS/I01.md` (create)
Not allowed: `tl_mod_forms/**`, `tl_core/**`, `schema/**`, `AGENTS.md` (the supervisor lists the group), any dependency.

## Tests to add (lint-clean under `ruff format`, `ruff check`, strict `pyright`; no sleeps)
- issue as a controller: exit 0; stdout has exactly the two lines; `normalise_code` of the printed code is a code and `code_hash` of it equals `cur_forms_intake_code.code_hash` of the new row; the printed code appears **nowhere else**: not in any `event` payload, not in any `cur_*` row, not in stderr, not in `caplog` text
  (scan with the plain and the grouped form). Two issues print different codes.
- `--code ABCD...` is a usage error (exit 2) and writes nothing; missing `--heading` is exit 2.
- refusals exit 1 with the fixed text and print no code or hash: a person without `forms.intake.issue`; an unpublished and a non-public template; expiry in the past; a context key that is hidden to the actor answers exactly as an absent key.
- revoke: Active code revoked (exit 0, `revoked <id>`); a second revoke exit 1; an unknown id and an id of another project answer the same text.
- `tl intake --help` lists `code`; `tl intake code --help` lists `issue` and `revoke`.

## Acceptance
```
NODE_OPTIONS=--max-old-space-size=6144 just check
just gate packages/tl-cli/tests/test_cli_intake_code.py packages/tl-cli/tests/test_cli_punch.py
```
Expected: all pass, `gate: PASS`.

## Report requirements
Standard report; first line deviations or none. Paste the issue output once with the code replaced by `<code>`; list every pinned file touched with old and new count.

## Escalation triggers
- The command needs a field or word S7c does not define (report; do not edit `tl_mod_forms`).
- A pinned list outside `tl-cli` fails (stop; name it).
- Another branch also adds an `intake` group to `main.py` (the hooks branch p2/ip-r3 may: report the conflict, do not resolve it by deleting a line).

## Blocked
(implementer writes here)

## Decision
(supervisor or orchestrator writes here)
