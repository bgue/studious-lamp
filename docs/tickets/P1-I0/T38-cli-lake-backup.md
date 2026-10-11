# P1-I0-T38 — `tl lake` on a SQLite path or a Postgres URL; `tl backup sqlite` refuses Postgres

Status: ready
Tier: haiku
Labels: cli
Depends on: P1-I0-S30, S32, S33, S34 (merged on `p1/i0b`)
Branch: `p1/i0b-t38-cli-lake-backup`

## Goal
`tl lake sync|rebuild|status|tables|query` and `tl backup sqlite` run on whichever database the root `--db` option or `TL_DB` names: a SQLite file or a
`postgresql://` URL. Today they open the database with SQLite-only code and treat it as a `Path`,
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
def is_postgres(target: DbTarget) -> bool: ...
def display_target(target: DbTarget) -> str:
    """``target`` as text that is safe to print: a Postgres URL without its password."""
def make_engine(target: DbTarget) -> Engine:
    """A SQLAlchemy engine for ``target``. The caller disposes it."""
```
`lake.py` and `backup.py` use `tl_adapters.sqlite.engine.make_engine(path)` and
`tl_adapters.sqlite.backup.backup_database(path, dest)` today.

## Context (read these, nothing else)
- `packages/tl-cli/src/tl_cli/lake.py`
- `packages/tl-cli/src/tl_cli/backup.py`
- `packages/tl-cli/src/tl_cli/main.py (the root callback; read only)`
- `packages/tl-cli/tests/test_cli_lake.py`
- `packages/tl-cli/tests/test_cli_lake_watch.py`
- `packages/tl-cli/tests/test_cli_backup.py`
may explore: (none)

## Allowed paths
- `packages/tl-cli/src/tl_cli/lake.py`
- `packages/tl-cli/src/tl_cli/backup.py`
- `packages/tl-cli/tests/test_cli_backup.py (append one test; see below)`
- `docs/reports/P1-I0/P1-I0-T38.md (create: your report; commit it)`

## Steps
1. `uv sync --all-packages`, then `pg_isready -h localhost` (see Rules).
2. Make exactly these edits and nothing else:
   - `lake.py`: replace `from tl_adapters.sqlite.engine import make_engine` with
     `from tl_adapters.db import DbTarget, display_target, is_postgres, make_engine` and change
     `_ledger_snapshot` to this (the existence check applies to a SQLite file only, and the error
     text never shows a password):
     ```python
     db: DbTarget = ctx.obj
     if not is_postgres(db) and not Path(db).exists():
         _fail(f"no ledger at {display_target(db)}: run `tl init`")
     engine = make_engine(db)
     ```
   - `backup.py`: see "The backup guard" below.
3. Run the acceptance commands. Paste the decisive lines into the report.

## The backup guard (`backup.py`)
`tl backup sqlite` takes an online snapshot with SQLite's backup API, so it cannot work on Postgres.
Today a URL would be handed to it as a file name. Make it refuse, at the top of `sqlite_backup`:
```python
target: DbTarget = ctx.obj
if is_postgres(target):
    _fail(
        "tl backup sqlite takes a SQLite ledger; for Postgres use pgBackRest "
        "(docs/runbooks/pgbackrest-restore.md) or `tl archive seal`"
    )
source = Path(target)
```
(imports: `from tl_adapters.db import DbTarget, is_postgres`; the rest of the function is unchanged.)
Then append this test to `packages/tl-cli/tests/test_cli_backup.py` (the only provided test file
you may edit, and only by appending):
```python
def test_a_postgres_target_is_refused_and_points_to_the_postgres_tools() -> None:
    url = "postgresql://u:hunter2@127.0.0.1:1/tl?sslmode=disable"
    result = runner.invoke(app, ["backup", "sqlite", "--to", "snap.db"], env={"TL_DB": url})
    assert result.exit_code == 1
    assert isinstance(result.exception, SystemExit)  # a clean exit, not a crash
    assert "error: tl backup sqlite takes a SQLite ledger" in result.stderr
    assert "pgbackrest" in result.stderr
    assert "hunter2" not in result.output
```

## Acceptance
```
just check
uv run pytest packages/tl-cli/tests/test_cli_lake.py packages/tl-cli/tests/test_cli_lake_watch.py packages/tl-cli/tests/test_cli_backup.py -q --adapters sqlite,postgres
uv run pytest packages/tl-cli -q
```
Expected: `just check` clean; 48 passed in the second command (each parity test runs once per
adapter); the third command passes (SQLite only; it ran 397 passed before this ticket, plus
whatever this ticket adds).

## Tests to add
- `packages/tl-cli/tests/test_cli_backup.py::test_a_postgres_target_is_refused_and_points_to_the_postgres_tools` (the text is under "The backup guard").

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
- Commit as `P1-I0-T38: <summary>` with your report in the same commit.

## Escalation triggers
- Stop and report *Blocked* if a provided test still fails on Postgres after the edits above (it
  would mean a real defect or a test problem, not something to work around), if a source file needs
  a change other than the ones listed, or if you would have to touch a file outside *Allowed
  paths*. Never edit a provided test file, skip a test, or mark one expected to fail.

## Blocked
(implementer writes here)

## Decision
(supervisor or orchestrator writes here)
