# P2-I5-T04b — CLI for the progress writes: `tl awp iwp start-work|complete-field|item-move|step|progress`

Status: ready (S2 merged; dispatch after T01 merges: both add one line to `awp.py`)
Tier: haiku
Kind: ticket
Review: full
Labels: cli
Depends on: S2
Branch: `p2/i5-t04b-progress-cli`
Worktree: harness-created under `/home/user/wt/i5/t04b` (from `p2/i5` head)

## Goal
A planner or foreman records field progress from the terminal: starts and completes an IWP's field work, moves scope items, marks hand-credited steps, and reads the earned figure. Every verb builds one S2 command and runs its handler; the CLI parses and prints, the handlers decide.

## Brief references (pasted)
- Commands (S2, `tl_mod_awp.commands`; all `extra="forbid"`): `StartIwpWork(iwp_id, expected_version, at: date|None)` and `CompleteIwpField` (same fields); `InstallScopeItem`, `ReturnScopeItem`, `VerifyScopeItem(record_id, expected_version)`; `RecordManualProgress(iwp_id, steps: list[ManualStep], expected_version)` with `ManualStep(scope_item_id, step, done)`. The handlers check state, word (`awp.iwp.edit`, `awp.progress.record`) and the stale version; the CLI never repeats a check.
- Verbs, all in the `iwp` group (`register(iwp_app)`), `--project`, `--actor` (default `DEV_ACTOR`) as in `awp_iwp_write.py`:
  - `start-work NUMBER [--date YYYY-MM-DD] [--expected-version N]` prints `start-work <number>  version <v>`; `complete-field` likewise `complete-field <number>  version <v>`.
  - `item-move ITEM_KEY ACTION [--expected-version N]`, ACTION one of `install`, `verify`, `return` (a `typer.BadParameter`-style usage error, exit 2, for any other word); prints `<action> <item key>  version <v>`.
  - `step NUMBER ITEM_KEY STEP [--undo] [--expected-version N]` builds one `ManualStep` (`done` false with `--undo`); prints `step <number>  version <v>`.
  - `progress NUMBER` (a read) prints `iwp <number>`, `earned <pct>  edition <package@version>`, `items: <n>`, then per item `<key>  <pct>  <steps earned joined ", " or ->` and one `note: <text>` per note. It uses `engine.earned_fraction(conn, iwp_id, viewer=session_viewer(db))`; a missing or hidden IWP is `error: no IWP <number>` (exit 1), one text for both.
- `--expected-version` default: the current version of the IWP (`StartIwpWork`, `CompleteIwpField`, `RecordManualProgress`) or of the scope item (moves), read with `get_record(uow, scope_of(project), key)["version"]` inside the same unit of work (the CLI runs the person's act on what the terminal shows; a given value that is stale is refused by the handler).
- An IWP is named by its number (`iwp_views.iwp_detail`, as `awp_iwp_write._iwp_id`), a scope item by its record key (`_record_id`).

## Interfaces (verbatim from repo)
```python
# tl_cli/awp_write.py
def _execute(db: DbTarget, build: Callable[[UnitOfWork], Command]) -> CommandResult   # gates with require_command, runs the handler
def _line(verb: str, number: str, result: CommandResult) -> None                    # "<verb> <number>  version <v>"
# tl_cli/awp_iwp_write.py
def _iwp_id(uow, project, number) -> str ; def _record_id(uow, project, key, what) -> str
# tl_mod_awp/progress/engine.py
def earned_fraction(conn, iwp_id, *, viewer=None) -> Earned    # Earned.pct, .edition, .items (key, pct, steps), .notes
```

## Context (read these, nothing else)
- `packages/tl-cli/src/tl_cli/awp_iwp_write.py` (lines 1-80, `iwp_hold`, `register`), `packages/tl-cli/src/tl_cli/awp_write.py` (lines 100-132), `packages/tl-cli/src/tl_cli/awp_iwp_read.py` (a read verb), `packages/tl-cli/src/tl_cli/awp.py`
- `packages/tl-modules/awp/src/tl_mod_awp/commands.py` (lines 730-790), `packages/tl-modules/awp/src/tl_mod_awp/progress/engine.py` (lines 95-122, 388-400)
- the provided test `docs/tickets/P2-I5/provided/T04b_test_awp_progress.py`
may explore: (none)

## Allowed paths
- `packages/tl-cli/src/tl_cli/awp_progress.py` (create): `register(iwp_app: typer.Typer) -> None`
- `packages/tl-cli/src/tl_cli/awp.py`: one import and one `awp_progress.register(iwp_app)` line after `awp_iwp_write.register(iwp_app)`
- `packages/tl-cli/tests/test_awp_progress.py` (create: byte-identical copy of the provided test)
- `docs/reports/P2-I5/T04b.md` (create)
- consequential pins: none expected; list any

## Acceptance
```
just check
just gate packages/tl-cli/tests/test_awp_progress.py packages/tl-cli/tests/test_cli_awp.py
```
Expected: 7 passed in the first file; `just check` clean; `cmp` of the test and the provided copy identical.

## Tests to add
The provided test (copied). Add nothing else.

## Report requirements
Standard report (`docs/templates/haiku-report.md`), <= 60 lines, deviations first. Commit subjects `P2-I5-T04b: ...`; trailer is the attribution lines your harness requires then `Claude-Session: https://claude.ai/code/session_01MSkuXpRjf5XzVwbAVQNqK4`. No model names in committed files.

## Escalation triggers
- A handler needs a field or word the command lacks.
- The viewer user `vera` is not refused (word table differs): write the answer under Blocked, do not edit the test.
- The provided test fails on a line the ticket does not explain.

## Blocked
(implementer writes here)

## Decision
(supervisor or orchestrator writes here)
