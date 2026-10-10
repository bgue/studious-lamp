"""The `tl sim` group: the five simulation operations, plus `run` and `seed` (brief 29.5).

Each subcommand parses options, makes one call into ``tl_sim.api`` and prints. Rules live in the
orchestrator. The group's options say where the run files are (``--sim-dir``), which server to
talk to (``--api-url``) and which token file that server reads (``--tokens``); each has an
environment variable (``TL_SIM_DIR``, ``TL_API_URL``, ``TL_TOKENS``). A failure prints
``error: <message>`` on stderr and exits 1.

Output (the demo and the tests depend on these lines):

* ``create``: ``run <id>``, ``scope <scope>``, ``seeded <n> records`` (ground-truth lines of the
  seed step).
* ``advance``: one ``played <date>`` per day, then ``ground truth +<n> (<total> lines)``.
* ``inject``: ``queued <event> for the next day played``.
* ``status``: ``key: value`` lines for run, scope, scenario, seed, day, next_date, digest, then
  ``  <intent>: <n>`` per intent, then ``pending: <n>``.
* ``assert``: ``ok: <checked> checks`` and exit 0, or ``FAILED: <n> of <checked> checks``
  followed by one ``  <check> <ref> <field>: expected X, found Y`` line per failure and exit 1.
* ``run``: create, advance the scenario's ``duration_days``, assert; prints their output in turn.
* ``seed``: ``run`` for the bundled scenario ``seed-<scale>`` (``xs``, ``s`` or ``m``).
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Annotated, Any, NoReturn

import typer
from pydantic import ValidationError
from tl_api.errors import ApiError
from tl_core.services.errors import ServiceError

from tl_sim import api
from tl_sim.scenario_loader import ScenarioError, load_scenario
from tl_sim.state import RunError

app = typer.Typer(help="Run a simulated project team against the API.", no_args_is_help=True)

SCALES = ("xs", "s", "m")


def _fail(message: str) -> NoReturn:
    typer.echo(f"error: {message}", err=True)
    raise typer.Exit(code=1)


@contextmanager
def _errors() -> Iterator[None]:
    try:
        yield
    except ValidationError as exc:  # before ValueError, which it subclasses
        _fail("; ".join(f"{'.'.join(str(p) for p in e['loc'])}: {e['msg']}" for e in exc.errors()))
    except (RunError, ScenarioError, ApiError, ServiceError, ValueError) as exc:
        _fail(str(exc))


@app.callback()
def root(
    ctx: typer.Context,
    sim_dir: Annotated[
        Path, typer.Option("--sim-dir", envvar="TL_SIM_DIR", help="Where the runs are kept.")
    ] = Path(api.DEFAULT_SIM_DIR),
    api_url: Annotated[
        str, typer.Option("--api-url", envvar="TL_API_URL", help="The running API.")
    ] = api.DEFAULT_API_URL,
    tokens: Annotated[
        Path, typer.Option("--tokens", envvar="TL_TOKENS", help="The token file the API reads.")
    ] = Path(api.DEFAULT_TOKENS),
) -> None:
    """Simulation options shared by every subcommand.

    Under ``tl`` the ledger file is the root ``--db`` (the MCP server for the agent opens it).
    """
    ledger = ctx.obj if isinstance(ctx.obj, Path) else Path(api.DEFAULT_DB)
    ctx.obj = api.SimEnv(sim_dir=sim_dir, api_url=api_url, tokens_path=tokens, db_path=ledger)


_Run = Annotated[str | None, typer.Option("--run", help="Run id; optional when one run exists.")]


def _create(env: api.SimEnv, scenario: str, run_id: str | None) -> dict[str, Any]:
    made = api.sim_create(env, scenario, run_id=run_id)
    typer.echo(f"run {made['run_id']}")
    typer.echo(f"scope {made['scope']}")
    typer.echo(f"seeded {made['ground_truth'].get('record.created', 0)} records")
    return made


def _advance(env: api.SimEnv, run_id: str | None, days: int) -> dict[str, Any]:
    done = api.sim_advance(env, run_id, days=days)
    for played in done["dates"]:
        typer.echo(f"played {played}")
    total = sum(done["ground_truth"].values())
    typer.echo(f"ground truth +{done['ground_truth_written']} ({total} lines)")
    return done


def _assert(env: api.SimEnv, run_id: str | None) -> None:
    report = api.sim_assert(env, run_id)
    if report["ok"]:
        typer.echo(f"ok: {report['checked']} checks")
        return
    failures = report["failures"]
    typer.echo(f"FAILED: {len(failures)} of {report['checked']} checks")
    for f in failures:
        typer.echo(
            f"  {f['check']} {f['ref']} {f['field']}: expected {f['expected']!r}, "
            f"found {f['actual']!r}"
        )
    raise typer.Exit(code=1)


@app.command("create")
def create(
    ctx: typer.Context,
    scenario: Annotated[str, typer.Argument(help="A bundled scenario name or a YAML path.")],
    run_id: Annotated[str | None, typer.Option("--run-id", help="Default: from the seed.")] = None,
) -> None:
    """Create a run and write the template's areas and lines."""
    with _errors():
        _create(ctx.obj, scenario, run_id)


@app.command("advance")
def advance(
    ctx: typer.Context,
    run: _Run = None,
    days: Annotated[int, typer.Option("--days", min=1, help="Working days to play.")] = 1,
) -> None:
    """Play working days."""
    with _errors():
        _advance(ctx.obj, run, days)


@app.command("inject")
def inject(
    ctx: typer.Context,
    event: Annotated[str, typer.Argument(help="material_late, design_revision or post.")],
    arg: Annotated[
        list[str] | None, typer.Option("--arg", help="key=value; repeatable. Numbers stay numbers.")
    ] = None,
    run: _Run = None,
) -> None:
    """Queue an event for the next day played."""
    with _errors():
        args: dict[str, Any] = {}
        for item in arg or []:
            key, sep, value = item.partition("=")
            if not sep or not key:
                _fail(f"--arg must look like key=value, not {item!r}")
            args[key] = int(value) if value.lstrip("-").isdigit() else value
        queued = api.sim_inject(ctx.obj, run, event, args)
        typer.echo(f"queued {queued['queued']['event']} for the next day played")


@app.command("status")
def status(ctx: typer.Context, run: _Run = None) -> None:
    """Show the run: day, next date, ground-truth counts and digest."""
    with _errors():
        info = api.sim_status(ctx.obj, run)
        typer.echo(f"run: {info['run_id']}")
        for key in ("scope", "scenario", "seed", "day", "next_date", "digest"):
            typer.echo(f"{key}: {info[key]}")
        for intent, count in sorted(info["ground_truth"].items()):
            typer.echo(f"  {intent}: {count}")
        typer.echo(f"pending: {len(info['pending'])}")


@app.command("assert")
def assert_(ctx: typer.Context, run: _Run = None) -> None:
    """Compare the ground truth with the suite; exit 1 when they differ."""
    with _errors():
        _assert(ctx.obj, run)


@app.command("run")
def run_(
    ctx: typer.Context,
    scenario: Annotated[str, typer.Argument(help="A bundled scenario name or a YAML path.")],
    run_id: Annotated[str | None, typer.Option("--run-id")] = None,
) -> None:
    """Create a run, play the scenario's duration and assert."""
    with _errors():
        days = load_scenario(scenario).duration_days
        made = _create(ctx.obj, scenario, run_id)
        _advance(ctx.obj, made["run_id"], days)
        _assert(ctx.obj, made["run_id"])


@app.command("seed")
def seed(
    ctx: typer.Context,
    scale: Annotated[str, typer.Option("--scale", help="xs, s or m.")] = "xs",
    run_id: Annotated[str | None, typer.Option("--run-id")] = None,
) -> None:
    """A synthetic project in the ledger: `run` on the bundled `seed-<scale>` scenario."""
    if scale not in SCALES:
        _fail(f"--scale must be one of {', '.join(SCALES)}, not {scale!r}")
    run_(ctx, f"seed-{scale}", run_id)
