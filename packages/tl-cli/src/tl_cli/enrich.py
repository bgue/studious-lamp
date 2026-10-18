"""The `tl enrich` group: the review queue of enriched values, and a run on one record (P1-I7-T05a).

An enricher proposes values for the layer `enrich.<enricher>` of a record. Each value waits here
until a person accepts or rejects it (or the enricher's `auto` policy accepted it already).
Accepting writes only that layer; making a value an authoritative field is the person's own
`tl pset set`. Each subcommand parses options, makes one call into `tl_core.integration.enrichers`,
and prints; the rules live in the services.
"""

from __future__ import annotations

import json
from typing import Annotated

import typer
from tl_core.integration.enrichers.commands import (
    AcceptEnrichment,
    RejectEnrichment,
    RunEnricher,
    handle_accept_enrichment,
    handle_reject_enrichment,
    handle_run_enricher,
)

from tl_cli.integration_support import (
    DEFAULT_ACTOR,
    SOURCE,
    ActorOption,
    CompanyOption,
    ProjectOption,
    factory,
    fail,
    line,
    one,
    record_id_of,
    rows,
    scope_of,
    service_errors,
)

app = typer.Typer(help="Enriched values: list, show, accept, reject, run.", no_args_is_help=True)

_STATES = ("proposed", "shadow", "accepted", "auto_accepted", "rejected")
_LIST_SQL = (
    "SELECT v.value_id, v.acceptance_state, v.property_path, v.value_json, v.confidence, "
    "v.target_id, r.key AS record_key FROM cur_enrichment_value v "
    "LEFT JOIN cur_core_record r ON r.id = v.target_id"
)
_VALUE_SQL = (
    "SELECT v.*, r.key AS record_key FROM cur_enrichment_value v "
    "LEFT JOIN cur_core_record r ON r.id = v.target_id "
    "WHERE v.value_id = :id AND v.scope = :scope"
)


def value_line(row: dict[str, object]) -> str:
    """``<id>  proposed  enrich.doc_classifier.doc_type  ISD-001  "ISO"  0.9``: the id, the state,
    the property path, the record's key (``-`` when it has none), the value as JSON
    (``json.dumps(row["value"], ensure_ascii=False)``) and the confidence."""
    shown = json.dumps(row["value"], ensure_ascii=False)
    return line(
        row["value_id"], row["acceptance_state"], row["property_path"], row["record_key"], shown,
        row["confidence"],
    )  # fmt: skip


@app.command("ls")
def ls(
    ctx: typer.Context,
    project: ProjectOption = None,
    company: CompanyOption = False,
    state: Annotated[
        str,
        typer.Option("--state", help="proposed, shadow, accepted, auto_accepted, rejected or all."),
    ] = "proposed",
    n: Annotated[int, typer.Option("-n", min=1, help="How many (oldest first).")] = 50,
) -> None:
    """List enriched values, oldest first; by default the ones waiting for a person.

    STEPS: ``state`` not ``all`` and not in ``_STATES``: ``fail(f"--state must be one of
    {', '.join(_STATES)} or all")``. ``scope = scope_of(project, company)`` when either option is
    given. Build ``WHERE`` clauses on ``_LIST_SQL``: ``v.scope = :scope`` and ``v.acceptance_state
    = :state`` (not for ``all``); add ``ORDER BY v.seq LIMIT :n``. In a read-only unit of work
    inside ``service_errors()`` read with ``rows(...)`` and print ``value_line(row)`` for each.
    """
    if state != "all" and state not in _STATES:
        fail(f"--state must be one of {', '.join(_STATES)} or all")
    clauses: list[str] = []
    params: dict[str, object] = {"n": n}
    if project is not None or company:
        clauses.append("v.scope = :scope")
        params["scope"] = scope_of(project, company)
    if state != "all":
        clauses.append("v.acceptance_state = :state")
        params["state"] = state
    where = f" WHERE {' AND '.join(clauses)}" if clauses else ""
    with factory(ctx) as opened, opened(readonly=True) as uow, service_errors():
        for row in rows(uow, f"{_LIST_SQL}{where} ORDER BY v.seq LIMIT :n", **params):
            typer.echo(value_line(row))


@app.command("show")
def show(
    ctx: typer.Context,
    value_id: Annotated[str, typer.Argument(help="The value id from `tl enrich ls`.")],
    project: ProjectOption = None,
    company: CompanyOption = False,
) -> None:
    """Print one value with its provenance.

    STEPS: ``scope = scope_of(project, company)``; ``row = one(uow, f"value {value_id}",
    _VALUE_SQL, id=value_id, scope=scope)`` in a read-only unit of work inside
    ``service_errors()``. Print, in this order: ``value <id>``, ``state <acceptance_state>``,
    ``record <record_key>`` (``-`` when none), ``property <property_path>``, ``value
    <json.dumps(row["value"], ensure_ascii=False)>``, ``confidence``, ``enricher
    <enricher>@<enricher_version>``, ``produced <produced_at>``; then, only when set, ``file
    <sha256>`` (the ``file_sha256`` of the first of ``row["inputs"]``, when that is set),
    ``decided <decided_by> <decided_at>`` and ``reason <reason>``.
    """
    scope = scope_of(project, company)
    with factory(ctx) as opened, opened(readonly=True) as uow, service_errors():
        row = one(uow, f"value {value_id}", _VALUE_SQL, id=value_id, scope=scope)
    typer.echo(f"value {row['value_id']}")
    typer.echo(f"state {row['acceptance_state']}")
    typer.echo(f"record {row['record_key'] or '-'}")
    typer.echo(f"property {row['property_path']}")
    typer.echo(f"value {json.dumps(row['value'], ensure_ascii=False)}")
    typer.echo(f"confidence {row['confidence']}")
    typer.echo(f"enricher {row['enricher']}@{row['enricher_version']}")
    typer.echo(f"produced {row['produced_at']}")
    inputs = row["inputs"] or []
    if inputs and inputs[0].get("file_sha256"):
        typer.echo(f"file {inputs[0]['file_sha256']}")
    if row["decided_by"]:
        typer.echo(f"decided {row['decided_by']} {row['decided_at']}")
    if row["reason"]:
        typer.echo(f"reason {row['reason']}")


@app.command("accept")
def accept(
    ctx: typer.Context,
    value_id: Annotated[str, typer.Argument(help="A waiting value.")],
    project: ProjectOption = None,
    company: CompanyOption = False,
    actor: ActorOption = DEFAULT_ACTOR,
) -> None:
    """Accept a waiting value: it is written into the enricher's layer of the record.

    STEPS: ``scope = scope_of(project, company)``. In a write unit of work inside
    ``service_errors()`` call ``handle_accept_enrichment(uow, AcceptEnrichment(actor=actor,
    source=SOURCE, scope=scope, value_id=value_id))``. Print ``accepted <value_id>``.
    """
    scope = scope_of(project, company)
    with factory(ctx) as opened, service_errors(), opened() as uow:
        handle_accept_enrichment(
            uow, AcceptEnrichment(actor=actor, source=SOURCE, scope=scope, value_id=value_id)
        )
    typer.echo(f"accepted {value_id}")


@app.command("reject")
def reject(
    ctx: typer.Context,
    value_id: Annotated[str, typer.Argument(help="A waiting value.")],
    reason: Annotated[str, typer.Option("--reason", help="Why; the ledger keeps it.")],
    project: ProjectOption = None,
    company: CompanyOption = False,
    actor: ActorOption = DEFAULT_ACTOR,
) -> None:
    """Reject a waiting value. The same value is not proposed to a person again.

    STEPS: as ``accept`` with ``handle_reject_enrichment(uow, RejectEnrichment(actor=actor,
    source=SOURCE, scope=scope, value_id=value_id, reason=reason))``. Print ``rejected
    <value_id>``.
    """
    scope = scope_of(project, company)
    with factory(ctx) as opened, service_errors(), opened() as uow:
        handle_reject_enrichment(
            uow,
            RejectEnrichment(
                actor=actor, source=SOURCE, scope=scope, value_id=value_id, reason=reason
            ),
        )
    typer.echo(f"rejected {value_id}")


@app.command("run")
def run(
    ctx: typer.Context,
    enricher: Annotated[str, typer.Argument(help="The enricher's name.")],
    key: Annotated[str, typer.Argument(help="The record's key.")],
    project: ProjectOption = None,
    company: CompanyOption = False,
    actor: ActorOption = DEFAULT_ACTOR,
) -> None:
    """Run one enricher on one record now. Prints how many values it proposed and accepted.

    STEPS: ``scope = scope_of(project, company)``. In a write unit of work inside
    ``service_errors()``: ``record_id = record_id_of(uow, key, scope)`` (it names the record
    in its error); ``made = handle_run_enricher(uow, RunEnricher(actor=actor, source=SOURCE,
    scope=scope, enricher=enricher, record_id=record_id))``. Print ``proposed N`` and
    ``accepted M``, where N and M count the events of ``made.events`` whose ``event_type`` is
    ``Enrichment.Proposed`` and ``Enrichment.Accepted``.
    """
    scope = scope_of(project, company)
    with factory(ctx) as opened, service_errors(), opened() as uow:
        record_id = record_id_of(uow, key, scope)
        made = handle_run_enricher(
            uow,
            RunEnricher(
                actor=actor, source=SOURCE, scope=scope, enricher=enricher, record_id=record_id
            ),
        )
    kinds = [e.event_type for e in made.events]
    typer.echo(f"proposed {kinds.count('Enrichment.Proposed')}")
    typer.echo(f"accepted {kinds.count('Enrichment.Accepted')}")
