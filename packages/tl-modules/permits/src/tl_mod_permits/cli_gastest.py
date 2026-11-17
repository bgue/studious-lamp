"""`tl gastest record|ls`: record a gas test of a permit, list a permit's gas tests (P2-PTW-T06b).

``record`` builds ``RecordGasTest``, gates it and runs the handler ``COMMANDS`` names, on one unit
of work (``cli_permit_write``). The handler decides the result and any suspension; the CLI prints
what the handler's result says and reads the stored result back through ``gas_tests_for``.
``ls`` reads through ``gas_tests_for`` as the session's viewer. Both first check the access word
``permits.view`` (``cli_permit_read.enter``) and resolve the permit key as the viewer reads it,
so a hidden permit answers as one that does not exist. No record id is printed.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from typing import Annotated

import typer
from tl_adapters.db import DbTarget, open_uow
from tl_cli.derive_support import DEV_ACTOR, acting, cell, fail, scope_of, service_errors
from tl_core import confidentiality as cf
from tl_core.services.commands import Command
from tl_core.uow import UnitOfWork

from tl_mod_permits.cli import gastest_app
from tl_mod_permits.cli_permit_read import LIST_LIMIT, Actor, Project, enter
from tl_mod_permits.cli_permit_write import _execute, _model, _permit
from tl_mod_permits.iso_commands import RecordGasTest
from tl_mod_permits.iso_views import gas_tests_for
from tl_mod_permits.names import PERMIT_SUSPENDED

_KEY_HELP = "The permit key a read prints, for example P123-PTW-0001."
_READING = "Decimal text, for example 20.9."


def _taken(value: str | None) -> datetime | None:
    """``--taken-at`` as a time with an offset; a naive or unreadable one is a usage error."""
    if value is None:
        return None
    try:
        when = datetime.fromisoformat(value)
    except ValueError:
        raise typer.BadParameter(
            "must be an ISO date and time with an offset, for example 2026-12-01T07:30:00+00:00",
            param_hint="'--taken-at'",
        ) from None
    if when.tzinfo is None or when.utcoffset() is None:
        raise typer.BadParameter(
            "must carry an offset, for example +00:00", param_hint="'--taken-at'"
        )
    return when


def _when(value: datetime) -> str:
    """A time as `YYYY-MM-DD HH:MM UTC`."""
    return value.astimezone(UTC).strftime("%Y-%m-%d %H:%M UTC")


def _reading(value: Decimal | None) -> str:
    """A stored reading as the table shows it (`-` for a reading not taken)."""
    return cell(value, 12)


@gastest_app.command("record")
def gastest_record(
    ctx: typer.Context,
    key: Annotated[str, typer.Argument(help=_KEY_HELP)],
    project: Project,
    instrument: Annotated[str, typer.Option("--instrument", help="The instrument used.")],
    taken_at: Annotated[
        str | None,
        typer.Option(
            "--taken-at", help="When the test was taken, ISO with an offset (default now)."
        ),
    ] = None,
    o2: Annotated[str | None, typer.Option("--o2", help=f"O2 in percent. {_READING}")] = None,
    lel: Annotated[str | None, typer.Option("--lel", help=f"LEL in percent. {_READING}")] = None,
    h2s: Annotated[str | None, typer.Option("--h2s", help=f"H2S in ppm. {_READING}")] = None,
    co: Annotated[str | None, typer.Option("--co", help=f"CO in ppm. {_READING}")] = None,
    note: Annotated[str | None, typer.Option("--note", help="A note on the test.")] = None,
    actor: Actor = DEV_ACTOR,
) -> None:
    """Record a gas test of a permit; prints `recorded <GAS key>  <pass|fail>`.

    A failing test that suspended the permit also prints `permit <KEY> suspended`.
    """
    db: DbTarget = ctx.obj
    who = acting(db, actor)
    scope = scope_of(project)
    enter(db, scope, actor)  # permits.view first; nothing is read before it
    when = _taken(taken_at)
    permit_id = ""

    def build(uow: UnitOfWork) -> Command:
        nonlocal permit_id
        viewer = cf.viewer_for_actor(uow.conn(), who)
        row = _permit(uow, scope, key, viewer)
        permit_id = str(row["id"])
        return _model(
            RecordGasTest,
            actor=who,
            source="cli",
            scope=scope,
            permit=permit_id,
            instrument_text=instrument,
            taken_at=when,
            o2_pct=o2,
            lel_pct=lel,
            h2s_ppm=h2s,
            co_ppm=co,
            note=note,
        )

    result = _execute(db, who, build)
    with service_errors(), open_uow(db, readonly=True) as uow:
        viewer = cf.viewer_for_actor(uow.conn(), who)
        tests = gas_tests_for(uow.conn(), permit_id, viewer=viewer)
    made = next((t for t in tests if t.key == result.key), None)
    if made is None:
        fail(f"no gas test {result.key}")
    typer.echo(f"recorded {made.key}  {made.result}")
    if any(event.event_type == PERMIT_SUSPENDED for event in result.events):
        typer.echo(f"permit {key} suspended")


@gastest_app.command("ls")
def gastest_ls(
    ctx: typer.Context,
    key: Annotated[str, typer.Argument(help=_KEY_HELP)],
    project: Project,
    actor: Actor = DEV_ACTOR,
    limit: Annotated[
        int, typer.Option("--limit", min=1, help="The most tests to list.")
    ] = LIST_LIMIT,
) -> None:
    """List a permit's gas tests, newest first. An empty list prints `no gas tests`."""
    db: DbTarget = ctx.obj
    scope = scope_of(project)
    viewer = enter(db, scope, actor)
    with service_errors(), open_uow(db, readonly=True) as uow:
        permit = _permit(uow, scope, key, viewer)
        tests = gas_tests_for(uow.conn(), str(permit["id"]), viewer=viewer)[:limit]
    if not tests:
        typer.echo("no gas tests")
        return
    typer.echo("key  taken  instrument  tester  O2  LEL  H2S  CO  result  note")
    for t in tests:
        typer.echo(
            f"{t.key}  {_when(t.taken_at)}  {cell(t.instrument_text)}  {cell(t.tester)}  "
            f"{_reading(t.o2_pct)}  {_reading(t.lel_pct)}  {_reading(t.h2s_ppm)}  "
            f"{_reading(t.co_ppm)}  {t.result}  {cell(t.note)}"
        )
