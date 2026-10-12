# P1-I0-T35 — `tl types` and `tl types quarantine` on a SQLite path or a Postgres URL

Status: ready
Tier: haiku
Labels: cli
Depends on: P1-I0-S30, S32, S33, S34, T34 (merged on `p1/i0b`)
Branch: `p1/i0b-t35-cli-types`

## Goal
`tl types sync|ls|show|validate|lock|deprecate|watch` and `tl types quarantine` run on whichever database the root `--db` option or `TL_DB` names: a SQLite file or a
`postgresql://` URL. Today they call the SQLite-only `open_uow` and treat the database as a `Path`,
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
DbTarget = str | Path
"""A SQLite ledger file, or a ``postgresql://`` URL (optionally scoped by ``schema_url``)."""

def open_uow(
    target: DbTarget,
    *,
    readonly: bool = False,
    registry: ProjectorRegistry | None = None,
    bus: Bus | None = None,
) -> AbstractContextManager[BaseUnitOfWork]:
    """Open ``target`` and yield an entered unit of work (one transaction)."""
```
The old import, `tl_adapters.sqlite.uow.open_uow(path, *, readonly=False, ...)`, has the same call
shape; only the name of the module and the type of the first argument change.

## Context (read these, nothing else)
- `packages/tl-cli/src/tl_cli/extypes.py`
- `packages/tl-cli/src/tl_cli/extypes_quarantine.py`
- `packages/tl-cli/src/tl_cli/main.py (the root callback; read only)`
- `packages/tl-cli/tests/test_cli_extypes.py`
- `packages/tl-cli/tests/test_cli_extypes_conflict.py`
- `packages/tl-cli/tests/test_cli_extypes_settings.py`
- `packages/tl-cli/tests/test_cli_extypes_quarantine.py`
may explore: (none)

## Allowed paths
- `packages/tl-cli/src/tl_cli/extypes.py`
- `packages/tl-cli/src/tl_cli/extypes_quarantine.py`
- `docs/reports/P1-I0/P1-I0-T35.md (create: your report; commit it)`

## Steps
1. `uv sync --all-packages`, then `pg_isready -h localhost` (see Rules).
2. In each source file under *Allowed paths*, make exactly these edits and nothing else:
   - replace `from tl_adapters.sqlite.uow import open_uow` with
     `from tl_adapters.db import DbTarget, open_uow`;
   - change every `db: Path = ctx.obj` to `db: DbTarget = ctx.obj`;
   - remove `from pathlib import Path` only if `uv run ruff check` then reports it unused.
   Note: `extypes.py` has two helpers whose first parameter is the database: `sync_lines(db: Path, root: Path, actor: str)` and `_factory(db: Path)`; only the `db` parameter changes, to `DbTarget` (keep `root: Path`, so `Path` stays imported there). `extypes_quarantine.py` has `_factory(db: Path)` too.
3. Run the acceptance commands. Paste the decisive lines into the report.

## Acceptance
```
just check
uv run pytest packages/tl-cli/tests/test_cli_extypes.py packages/tl-cli/tests/test_cli_extypes_conflict.py packages/tl-cli/tests/test_cli_extypes_settings.py packages/tl-cli/tests/test_cli_extypes_quarantine.py -q --adapters sqlite,postgres
uv run pytest packages/tl-cli -q
```
Expected: `just check` clean; 66 passed in the second command (each parity test runs once per
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
- Commit as `P1-I0-T35: <summary>` with your report in the same commit.

## Escalation triggers
- Stop and report *Blocked* if a provided test still fails on Postgres after the edits above (it
  would mean a real defect or a test problem, not something to work around), if a source file needs
  a change other than the ones listed, or if you would have to touch a file outside *Allowed
  paths*. Never edit a provided test file, skip a test, or mark one expected to fail.

## Blocked
(implementer writes here)

## Decision
(supervisor or orchestrator writes here)
