# P0-I8-T07 — `tl lake sync --watch` waits `lake.sync.interval`

Status: merged
Tier: haiku
Labels: cli
Depends on: — (the setting and the lake sync are on the base)
Branch: `p0/i8a-t07-lake-watch`

## Goal
`tl lake sync --watch` keeps the lake current: it syncs, waits the `lake.sync.interval` in force (read again before every wait, so a change applies to a running watcher), and syncs again until interrupted. The option declarations and the command are wired; `watch_loop` and `_interval_seconds` in `tl_cli/lake.py` raise `NotImplementedError`. A provided test file (9 tests) must pass and the existing lake tests must stay green.

## Brief references (pasted)
> **30.5 Representative keys.** `lake.sync.interval` = 5m (how often `tl lake sync --watch` copies new ledger events into the lake). **30.3** Changes apply live: no restart.
> **28** The lake is a copy of the ledger made by `tl lake sync`: one snapshot per sync.

### Specification
`watch_loop(run_once, interval, sleep, max_runs)` is plain Python with the three actions passed in, so the tests drive it with fakes; its docstring is the whole behaviour:
- Run `run_once()`. Count the run. If `max_runs` is reached, stop (no wait after the last run).
- Otherwise read `interval()` and `sleep()` that many seconds. If reading the interval raises `ServiceError`, `SQLAlchemyError`, `ValueError` or `OSError`, keep the last good interval (`DEFAULT_INTERVAL_S` before the first one).
- A run that raises `GuardError` or `LakeError` prints `error: <message>` to standard error (`typer.echo(..., err=True)`) and the loop goes on.
- Return the number of runs.

`_interval_seconds(ctx)` opens a fresh read snapshot of the ledger with the existing `_ledger_snapshot(ctx)` and returns `duration_seconds(str(value_of(conn, INTERVAL_KEY)))`: the company value, else the default. The command already passes `lambda s: _sleep(s)` (the tests replace `lake._sleep`) and handles Ctrl+C. Do not change the command or the option declarations.

Learnings that apply:
- pyright is `standard` for `packages/tl-cli`, `tl-api`, `tl-mcp` and `tl-tui`; ruff limits lines to 100 columns (docstrings and comments too). Run `uv run ruff format` before committing. `uv` prints "UV_NATIVE_TLS is deprecated"; ignore it. Do not pipe `just check` into `tail`.
- Provided tests live under `docs/tickets/P0-I8/provided/*.py.txt`; copy them into the test tree byte for byte. Do not edit the copy.
- Commit your report at `docs/reports/P0-I8/<ticket-id>.md` (it is inside your Allowed paths).
- A fresh worktree needs `uv sync --all-packages` once before `uv run` can import the workspace packages.
- No new dependencies. Remove the `STUB` paragraph from the module docstring and from every docstring or comment you fill in.
- Never run `python` with the working directory set to a package directory that holds a file named `types.py` (it shadows the standard library); run everything from the repository root.
- A failing test that is not in your Allowed paths is not yours to fix: report it under *Blocked*. The base is green: if a test outside your Allowed paths fails, report it under *Blocked* with the output.

## Interfaces (verbatim from the repo at the branch point)
```python
# packages/tl-cli/src/tl_cli/lake.py (the two stubs you complete)
def watch_loop(
    run_once: Callable[[], None],
    interval: Callable[[], float],
    sleep: Callable[[float], None],
    max_runs: int | None = None,
) -> int:
    """STUB (P0-I8-T07): remove this paragraph when you implement the body.

    Call ``run_once``, then wait ``interval()`` seconds, again and again; return the run count.

    The interval is read again before every wait, so a changed setting applies to the next wait.
    If it cannot be read (the ledger is busy, the value is bad) the last one read is used, or
    ``DEFAULT_INTERVAL_S`` before the first. A run that raises ``GuardError`` or ``LakeError``
    prints ``error: <message>`` to standard error and the loop goes on. With ``max_runs`` the
    loop stops after that many runs, without a wait after the last one.
    """
    raise NotImplementedError("STUB: P0-I8-T07")

def _interval_seconds(ctx: typer.Context) -> float:
    """STUB (P0-I8-T07): remove this paragraph when you implement the body.

    ``lake.sync.interval`` in force now, in seconds, read in a fresh read snapshot of the ledger
    with ``value_of(conn, INTERVAL_KEY)`` (the company value, else the default) and converted with
    ``duration_seconds``.
    """
    raise NotImplementedError("STUB: P0-I8-T07")
```
```python
# imports to add to lake.py (the stub's autofix removed them):
from sqlalchemy.exc import SQLAlchemyError
from tl_core.services.errors import ServiceError
from tl_core.settings.resolver import value_of
from tl_core.settings.values import duration_seconds
# GuardError, LakeError, _ledger_snapshot, INTERVAL_KEY and DEFAULT_INTERVAL_S are already in the module.
```
```python
# already implemented (read only)
# tl_core.settings.resolver.value_of(conn, key, *, project=None, user=None, at=None) -> Any
# tl_core.settings.values.duration_seconds("10m") -> 600.0            # InvalidSettingValueError (a ServiceError) for bad text
```

## Context (read these, nothing else)
- `AGENTS.md`
- `packages/tl-cli/src/tl_cli/lake.py`
- `docs/tickets/P0-I8/provided/t07-test_cli_lake_watch.py.txt`
may explore: (none)

## Allowed paths
- `packages/tl-cli/src/tl_cli/lake.py` (edit: the two bodies and their imports)
- `packages/tl-cli/tests/test_cli_lake_watch.py` (create: byte-for-byte copy of the provided file)
- `docs/reports/P0-I8/P0-I8-T07.md` (create: your report; commit it)

## Steps
1. `cp docs/tickets/P0-I8/provided/t07-test_cli_lake_watch.py.txt packages/tl-cli/tests/test_cli_lake_watch.py`
2. Implement `watch_loop` and `_interval_seconds`; delete the STUB paragraphs; add the imports.
3. Run the acceptance commands, write the report, commit both.

## Acceptance
```
uv run pytest packages/tl-cli/tests/test_cli_lake_watch.py packages/tl-cli/tests/test_cli_lake.py -q
just check
```
Expected: 9 new tests pass, the existing lake CLI tests stay green, `just check` clean.

## Tests to add
None beyond the provided file.

## Report requirements
Standard report.

## Escalation triggers
- Stop and report *Blocked* if a pasted signature disagrees with the repo.

## Blocked
(implementer writes here)

## Decision
Reviewed in a fresh context: pass. Merged into p0/i8a as fb25d32.
