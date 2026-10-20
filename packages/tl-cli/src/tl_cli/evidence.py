"""`tl evidence`: the chain of records around an item as it stood at the end of a day.

Brief 9, M10: "for any Commercial or Legal item, one view assembles the full linked chain ... as of
the relevant dates (time-travel reads)". The command replays the ledger to the end of `--as-of`
(`tl_mod_correspondence.evidence`): what existed, the state it had, and the links that were there.
It reads as the signed-in person, so a record or link the person cannot read today is not shown,
whatever its class was on the day, and nothing says how many were left out (ADR-0016).
"""

from __future__ import annotations

import json
from datetime import date
from typing import Annotated

import typer
from tl_adapters.db import DbTarget, open_uow
from tl_mod_correspondence import evidence

from tl_cli.doc import _Project, _service_errors

_Number = Annotated[str, typer.Argument(help="The item number, for example P123-EW-0001.")]


def line(node: evidence.EvidenceNode) -> str:
    """One node of the trail as a line: indented by depth, with how it was reached."""
    via = ""
    if node.via is not None:
        pin = f" pinned {node.via.pin}" if node.via.pin else ""
        via = f" <- {node.via.label} ({node.via.status}{pin}, since {node.via.since})"
    voided = " VOID" if node.voided else ""
    facts = " ".join(f"{k}={v}" for k, v in node.facts.items() if k not in ("question", "answer"))
    return (
        f"{'  ' * node.depth}{node.key or node.record_id} [{node.type}] {node.state or '-'}"
        f"{voided} {node.title}{via}" + (f" | {facts}" if facts else "")
    )


def evidence_cmd(
    ctx: typer.Context,
    number: _Number,
    project: _Project,
    as_of: Annotated[
        str | None,
        typer.Option("--as-of", help="YYYY-MM-DD, never later than today. Default today."),
    ] = None,
    depth: Annotated[int, typer.Option("--depth", min=0, max=3, help="Links to follow.")] = 2,
    as_json: Annotated[bool, typer.Option("--json", help="Print JSON.")] = False,
) -> None:
    """The evidence trail of an item as of a day: the records linked to it and their state then."""
    db: DbTarget = ctx.obj
    with _service_errors(), open_uow(db, readonly=True) as uow:
        found = evidence.evidence_trail(
            uow.conn(), f"project:{project}", number, as_of, depth=depth
        )
    if as_json:
        typer.echo(json.dumps(found.model_dump(), indent=2))
        return
    typer.echo(f"evidence for {number} as of {found.as_of} ({date.fromisoformat(found.as_of):%A})")
    for node in found.nodes:
        typer.echo(line(node))
    if found.truncated:
        typer.echo("the walk was cut short by a bound; ask for less depth")
