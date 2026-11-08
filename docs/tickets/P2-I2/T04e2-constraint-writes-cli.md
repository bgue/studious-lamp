# P2-I2-T04e2 — CLI writes: `tl constraint raise|assign|clear|withdraw`

Status: ready
Tier: haiku
Kind: ticket
Review: full
Labels: cli, write, access, core
Depends on: C2 (merged)
Branch: `p2/i2-t04e2-constraint-writes-cli`
Worktree: harness-created under `/home/user/wt/i2/t04e2` (from `p2/i2` head)

## Goal
One module `constraint_write.py` with `register(app: typer.Typer) -> None` (the glue ticket T04g makes the `constraint` group and adds the call; this ticket edits neither `awp.py` nor `main.py`). Each verb builds one core command model of
`tl_core.constraints.commands` and runs the handler `command_table()` names for it, on one unit of work (`open_uow(db)`; model the `_execute` shape of `awp_write.py`, but the lookup is `command_table()`, a core table, so write
a three-line local `_handler`). The edit word `core.constraint.edit` is checked by the handler (`handlers.require_edit`); the CLI adds no role check of its own and no `require_command` (core commands are not module commands; read
`docs/reports/P2-I2/C2.md` "Deviations" first).

## Brief references (pasted)
> Verbs (`--project`, `--actor` as in `awp_write.cwp_create`; a constraint is named by its KEY as `tl constraint ls` prints it, L-P2-I3-3, resolved to its id; unknown or hidden is `error: no constraint <key>`, one text):
> - `raise --subject KEY --phase P --severity blocking|advisory --category C [--owner user:X] [--description T] [--due D] [--target KEY | --target-ref TYPE:TEXT]` -> `RaiseConstraint` with `source_kind` left at its default `manual` (a person raises manual only;
>   the other sources are the modules'); `--subject` and `--target` are record keys resolved to ids with the lookup `tl_cli/link.py` uses; an unknown or hidden subject is `error: no record <key>`. `--due` is `YYYY-MM-DD`. `--target-ref` is `TYPE:TEXT` with TYPE one of the model's
>   `target_ref_type` literals, split with `_parts` from `awp_write` (2 parts). `--target` and `--target-ref` are exclusive (usage error exit 2). Prints `raised <key>  version <v>`.
> - `assign KEY --owner user:X` -> `AssignConstraint`; prints `assign <key>  version <v>`.
> - `clear KEY --reason R [--cleared-at WORLD_TIME] [--resolved-by RECORDKEY]` -> `ClearConstraint`; prints `clear <key>  version <v>`.
> - `withdraw KEY --reason R` -> `WithdrawConstraint`; prints `withdraw <key>  version <v>`.
> - Pydantic validation errors (bad pattern, blank text, phase not gated) print through `service_errors()` as `error: ...`, exit 1; usage errors exit 2. The CLI never prints description text of a refused call back.
> Resolving a constraint key to its id: one `SELECT id FROM cur_core_record WHERE key=:k AND type='core.Constraint' AND scope=:scope` on the write uow, then `tl_core.constraints.queries.get_constraint(conn, id, viewer=session_viewer(db))` to confirm
> the subject is visible; `None` is the same `no constraint` text (hidden looks like missing; the handler repeats the check, this one only keeps the message identical).

## Context (read these, nothing else)
- `packages/tl-cli/src/tl_cli/awp_write.py` (lines 1-130, `cwp_create`, `register`), `packages/tl-cli/src/tl_cli/derive_support.py`, `packages/tl-cli/src/tl_cli/link.py` (key lookup only)
- `packages/tl-core/src/tl_core/constraints/commands.py` (lines 82-180), `packages/tl-core/src/tl_core/constraints/handlers.py` (lines 175-200)
- `docs/reports/P2-I2/C2.md`, `dev/accept/P2-I2/C2.py`, `dev/accept/P2-I2/c2_checks.py` (build, seed)

## Allowed paths
- `packages/tl-cli/src/tl_cli/constraint_write.py` (create)
- `dev/accept/P2-I2/T04e2.py` (create; helper `t04e2_checks.py` if over 70 lines), `docs/reports/P2-I2/T04e2.md` (create)
Not here: `awp.py`, `main.py`, the reads (T04d), any `tl_core` change, new pytest (S5).

## Acceptance
```
NODE_OPTIONS=--max-old-space-size=6144 just check
uv run python dev/accept/P2-I2/T04e2.py
uv run python dev/accept/P2-I2/C2.py
```
`T04e2.py` (SQLite ledger from the C2 helpers, throwaway Typer with `register`, `CliRunner`; one `PASS <check>` per line; final `T04e2 ok`): raise a manual constraint on an IWP, assign, clear with reason, withdraw another; a plain `default`-role
actor refused (`error: forbidden`, exit 1, no row written); raising on a hidden subject prints exactly the text of an unknown key; `--target` with `--target-ref` exits 2; a phase that is not gated is refused with the keys-only message;
no `Traceback`; `C2.py` still `C2 ok`.

## Tests to add
None (S5).

## Report requirements
Standard report (`docs/templates/haiku-report.md`), <= 60 lines, deviations first. Commit subjects `P2-I2-T04e2: ...`; trailer is the attribution lines your harness requires then `Claude-Session: https://claude.ai/code/session_01MSkuXpRjf5XzVwbAVQNqK4`. No model names in committed files.

## Escalation triggers
- Stop and report *Blocked* if the handler needs a registry the CLI cannot reach, or the edit word cannot be satisfied on a dev ledger actor.

## Blocked
(implementer writes here)

## Decision
(supervisor or orchestrator writes here)
