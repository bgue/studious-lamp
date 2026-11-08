# P2-I2-T04e1 — CLI writes: IWP, scope item, pins, split, moves, sign-off, issue, hold

Status: ready
Tier: haiku
Kind: ticket
Review: full
Labels: cli, write, access
Depends on: S2, S3 (merged)
Branch: `p2/i2-t04e1-iwp-writes-cli`
Worktree: harness-created under `/home/user/wt/i2/t04e1` (from `p2/i2` head)

## Goal
One module `awp_iwp_write.py` with `register(iwp_app: typer.Typer) -> None` (the glue ticket T04g makes the `iwp` group and adds the call; this ticket edits neither `awp.py` nor `main.py`). Each verb builds one command model of
`tl_mod_awp.commands`, gates it with `require_command`, and runs the handler `AWP_COMMANDS` names, exactly as `awp_write.py` does (import `_execute`, `_line`, `_parts`, `_handler` from there; do not copy them).
An IWP is named by its number (the key `iwp ls` prints, L-P2-I3-3) and resolved to its id with `tl_mod_awp.iwp_views.iwp_detail`; unknown or hidden is `error: no IWP <number>` (one text).

## Brief references (pasted)
> Verbs (option names are the contract; `--project`, `--actor` as in `awp_write.cwp_create`; each prints one line):
> - `create --discipline D --title T [--cwp CWPNUMBER] [--planned-start D] [--planned-finish D] [--foreman user:X] [--hours H] [--crew TEXT]` -> `CreateIwp`; prints `created IWP <number>`. `--cwp` resolves a CWP number to its id with `views.cwp_detail`.
> - `item-create --commodity C --description T --qty Q --uom U --hours H [--cwp CWPNUMBER]` -> `CreateScopeItem`; prints `created scope item <key>` (result key).
> - `add-scope NUMBER ITEM...` / `remove-scope NUMBER ITEM...` -> `AddIwpScope` / `RemoveIwpScope`; items are record KEYS the reads print, resolved to ids with the key lookup `tl_cli/link.py` uses; at most 200; prints `<verb> <number>  <n> items  version <v>` via `_line`.
> - `pin NUMBER DOCUMENT [--pin REVCODE]` -> `PinIwpDocument` (no `--pin` pins the current revision, floating); DOCUMENT is the document key.
> - `split NUMBER --by-hours --reason R` or `split NUMBER --group KEY,KEY ... --reason R` (repeatable `--group` is `by_scope`; the two forms are exclusive, else usage error exit 2) -> `SplitIwp`; prints the new numbers if the result carries them, else `split <number>`.
> - `move NUMBER ACTION [--reason R]` with ACTION in `start-development`, `constraint-check`, `return-to-development` -> `StartIwpDevelopment`, `SendIwpToConstraintCheck`, `ReturnIwpToDevelopment` (a table like `MOVES` in `awp_write.py`); `cancel NUMBER --reason R` -> `CancelIwp`.
> - `hash NUMBER` -> prints `record hash <sha256>` from `tl_mod_awp.handlers.signoff.iwp_record_hash(conn, id)` (a read; read-only uow; the hash only, no other field).
> - `sign-off NUMBER --hash H` -> `SignOffIwp`; `issue NUMBER --hash H [--foreman user:X]` -> `IssueIwp`; `hold NUMBER --reason R` -> `HoldIwp`; `release-hold NUMBER [--reason R]` -> `ReleaseHold`.
>   The signer-role, distinct-signer and record-hash rules are the handlers'; the CLI only passes `--hash`. A `ForbiddenError` or a handler refusal prints through `service_errors()` (`error: ...`, exit 1) and nothing else.
> - Commands are gated by `require_command` (module word per command); never a role check of the CLI's own; never `require_controller`.

## Context (read these, nothing else)
- `packages/tl-cli/src/tl_cli/awp_write.py` (lines 1-130 and `cwp_create`, `cwp_move`, `register`), `packages/tl-cli/src/tl_cli/derive_support.py`
- `packages/tl-modules/awp/src/tl_mod_awp/commands.py` (lines 516-700, the IWP command models; `ReleaseHold`, `SignOffIwp`, `IssueIwp`, `HoldIwp` further down), `packages/tl-modules/awp/src/tl_mod_awp/handlers/signoff.py` (lines 60-110)
- `docs/reports/P2-I2/S2.md`, `docs/reports/P2-I2/S3.md`, `dev/accept/P2-I2/S3.py` (seed and signer setup)

## Allowed paths
- `packages/tl-cli/src/tl_cli/awp_iwp_write.py` (create)
- `dev/accept/P2-I2/T04e1.py` (create; helper `t04e1_checks.py` if over 70 lines), `docs/reports/P2-I2/T04e1.md` (create)
Not here: `awp.py`, `main.py`, constraint verbs (T04e2), reads (T04d), any change to handlers or commands, new pytest (S5).

## Acceptance
```
NODE_OPTIONS=--max-old-space-size=6144 just check
uv run python dev/accept/P2-I2/T04e1.py
just gate packages/tl-cli/tests/test_awp_write.py
```
`T04e1.py` (SQLite ledger, throwaway Typer with `register`, `CliRunner`; one `PASS <check>` per line; final `T04e1 ok`): create an IWP and three scope items, add and remove scope, pin a document, hash, move through to Ready is NOT needed
(drive the ledger to Ready with the S3 helpers), sign-off by two distinct accounts with the signoff role, a plain user refused (`error: forbidden`), the same signer twice refused, a wrong `--hash` refused, issue, hold and release-hold,
split by hours on an oversize IWP; unknown number prints one error text; every refusal is exit 1 with no `Traceback`.

## Tests to add
None (S5).

## Report requirements
Standard report (`docs/templates/haiku-report.md`), <= 60 lines, deviations first. Commit subjects `P2-I2-T04e1: ...`; trailer is the attribution lines your harness requires then `Claude-Session: https://claude.ai/code/session_01MSkuXpRjf5XzVwbAVQNqK4`. No model names in committed files.

## Escalation triggers
- Stop and report *Blocked* if a verb needs a command model that is not in `AWP_COMMANDS`, a key lookup for scope items does not exist, or more than the Allowed paths must change.

## Blocked
(implementer writes here)

## Decision
(supervisor or orchestrator writes here)
