# P1-I0-T37 — `tl webhook` on a SQLite path or a Postgres URL

Status: ready
Tier: haiku
Labels: cli
Depends on: P1-I0-S30, S32, S33, S34 (merged on `p1/i0b`)
Branch: `p1/i0b-t37-cli-webhook`

## Goal
`tl webhook add|ls|test|replay|run|dlq|disable|enable|rotate-secret` run on whichever database the root `--db` option or `TL_DB` names: a SQLite file or a
`postgresql://` URL. Today they build a SQLite-only unit-of-work factory from a `Path`,
so a URL would be turned into a file name. The tests for this group are already on the branch (S33)
and run each test on SQLite and, with `--adapters sqlite,postgres`, on Postgres; you make the
source side match.

## Brief references (pasted)
> Fanout P1-I0 exit criterion, Postgres: "`tl serve`, `tl tui`, `tl webhook`, `tl lake`, `tl file` and
> the embedded feed accept a `postgresql://` URL wherever they accept a SQLite path, through one
> backend factory. Parity tests cover the new paths."
>
> AGENTS.md rule 5: "Dialect-neutral core. Runtime SQLite- or Postgres-specific SQL lives only under
> `packages/tl-adapters/`." So the CLI must not import `tl_adapters.sqlite` or `tl_adapters.postgres`
> for this; it calls `tl_adapters.db`, which picks the adapter from the target.
>
> The root callback of `tl` (`tl_cli/main.py`, done in S32) puts the database in `ctx.obj` as a
> `DbTarget`: a `Path` for SQLite, the URL text for Postgres.

## Interfaces (verbatim from the repo at the branch point)
```python
# tl_adapters/db.py
def make_uow_factory(
    target: DbTarget,
    *,
    registry: ProjectorRegistry | None = None,
    bus: Bus | None = None,
) -> sqlite.factory.SqliteUowFactory | postgres.factory.PostgresUowFactory:
    """A long-lived unit-of-work factory for ``target`` (one engine, many short transactions).

    ``factory()`` opens a write unit of work and ``factory(readonly=True)`` a read snapshot on
    either adapter; ``dispose()`` ends it.
    """

# tl_core/webhooks/base.py (what make_dispatcher and make_engine take)
class UowFactory(Protocol):
    def __call__(self, *, readonly: bool = False) -> AbstractContextManager[UnitOfWork]: ...
```
`webhook_common.factory(ctx)` today builds `SqliteUowFactory(db)` with `db: Path`. The webhook
commands do not call `open_uow`.

## Context (read these, nothing else)
- `packages/tl-cli/src/tl_cli/webhook_common.py`
- `packages/tl-cli/src/tl_cli/main.py (the root callback; read only)`
- `packages/tl-cli/tests/test_cli_webhook.py`
- `packages/tl-cli/tests/test_cli_webhook_ops.py`
- `packages/tl-cli/tests/test_cli_webhook_run.py`
may explore: (none)

## Allowed paths
- `packages/tl-cli/src/tl_cli/webhook_common.py`
- `docs/reports/P1-I0/P1-I0-T37.md (create: your report; commit it)`

## Steps
1. `uv sync --all-packages`, then `pg_isready -h localhost` (see Rules).
2. In `webhook_common.py` only, change `factory` to build the factory for either database. Replace
   `from tl_adapters.sqlite.factory import SqliteUowFactory` with
   `from tl_adapters.db import DbTarget, make_uow_factory`, add
   `from tl_core.webhooks.base import UowFactory`, and make the function:
   ```python
   @contextmanager
   def factory(ctx: typer.Context) -> Generator[UowFactory]:
       """A unit-of-work factory on the ledger from ``--db`` / ``TL_DB``, disposed afterwards."""
       db: DbTarget = ctx.obj
       opened = make_uow_factory(db)
       try:
           yield opened
       finally:
           opened.dispose()
   ```
   Remove `from pathlib import Path` if ruff then reports it unused. `webhook.py` and
   `webhook_ops.py` call `factory(ctx)` and need no edit.
3. Run the acceptance commands. Paste the decisive lines into the report.

## Acceptance
```
just check
uv run pytest packages/tl-cli/tests/test_cli_webhook.py packages/tl-cli/tests/test_cli_webhook_ops.py packages/tl-cli/tests/test_cli_webhook_run.py -q --adapters sqlite,postgres
uv run pytest packages/tl-cli -q
```
Expected: `just check` clean; 36 passed in the second command (each parity test runs once per
adapter); the third command passes (SQLite only; it ran 397 passed before this ticket, plus
whatever this ticket adds).

## Tests to add
- none: the tests are provided (S33) and must not be edited.

## Report requirements
Standard report (`docs/templates/haiku-report.md`). Paste the output of the three acceptance
commands. State in *Deviations* any edit you made beyond the ones listed under Steps.

## Rules to remember (from the project's learnings)
- Run every command from the repository root of your worktree. `uv sync --all-packages` first: a
  new worktree has an empty `.venv` (L-P0-I6A-1).
- Ruff's line limit is 100 columns, comments and docstrings included (L-P0-I1-6).
- Write and edit files with the Edit or Write tool, not shell heredocs, which can hang the shell.
  Never use `pkill -f`; it can kill your own shell (L-P0-I6C-8). Kill only a process you started,
  by PID.
- The container is shared. Run only the commands listed under Acceptance. Do not run `just test`
  or `just test-parity` (they take 15 minutes and hold the CPUs).
- Postgres must answer: `pg_isready -h localhost` prints `accepting connections`. If it does not,
  run `sudo pg_ctlcluster 16 main start`. The tests create and drop their own schemas inside a
  scratch database; never connect to or drop any other database.
- Commit as `P1-I0-T37: <summary>` with your report in the same commit.

## Escalation triggers
- Stop and report *Blocked* if a provided test still fails on Postgres after the edits above (it
  would mean a real defect or a test problem, not something to work around), if a source file needs
  a change other than the ones listed, or if you would have to touch a file outside *Allowed
  paths*. Never edit a provided test file, skip a test, or mark one expected to fail.

## Blocked
(implementer writes here)

## Decision
(supervisor or orchestrator writes here)
