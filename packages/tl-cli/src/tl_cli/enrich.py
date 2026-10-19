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
    """List enriched values, oldest first; by default the ones waiting for a person."""
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
    sql = f"{_LIST_SQL}{where} ORDER BY v.seq LIMIT :n"
    with factory(ctx) as opened, service_errors(), opened(readonly=True) as uow:
        for row in rows(uow, sql, **params):
            typer.echo(value_line(row))


@app.command("show")
def show(
    ctx: typer.Context,
    value_id: Annotated[str, typer.Argument(help="The value id from `tl enrich ls`.")],
    project: ProjectOption = None,
    company: CompanyOption = False,
) -> None:
    """Print one value with its provenance."""
    scope = scope_of(project, company)
    with factory(ctx) as opened, service_errors(), opened(readonly=True) as uow:
        row = one(uow, f"value {value_id}", _VALUE_SQL, id=value_id, scope=scope)
        key = row["record_key"] if row["record_key"] is not None else "-"
        shown = [
            f"value {value_id}",
            f"state {row['acceptance_state']}",
            f"record {key}",
            f"property {row['property_path']}",
            f"value {json.dumps(row['value'], ensure_ascii=False)}",
            f"confidence {row['confidence']}",
            f"enricher {row['enricher']}@{row['enricher_version']}",
            f"produced {row['produced_at']}",
        ]
        first_input = (row["inputs"] or [{}])[0]
        if first_input.get("file_sha256") is not None:
            shown.append(f"file {first_input['file_sha256']}")
        if row["decided_by"] is not None:
            shown.append(f"decided {row['decided_by']} {row['decided_at']}")
        if row["reason"] is not None:
            shown.append(f"reason {row['reason']}")
        for text_line in shown:
            typer.echo(text_line)


@app.command("accept")
def accept(
    ctx: typer.Context,
    value_id: Annotated[str, typer.Argument(help="A waiting value.")],
    project: ProjectOption = None,
    company: CompanyOption = False,
    actor: ActorOption = DEFAULT_ACTOR,
) -> None:
    """Accept a waiting value: it is written into the enricher's layer of the record."""
    scope = scope_of(project, company)
    with factory(ctx) as opened, service_errors(), opened() as uow:
        handle_accept_enrichment(
            uow,
            AcceptEnrichment(actor=actor, source=SOURCE, scope=scope, value_id=value_id),
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
    """Reject a waiting value. The same value is not proposed to a person again."""
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
    """Run one enricher on one record now. Prints how many values it proposed and accepted."""
    scope = scope_of(project, company)
    with factory(ctx) as opened, service_errors(), opened() as uow:
        record_id = record_id_of(uow, key, scope)
        made = handle_run_enricher(
            uow,
            RunEnricher(
                actor=actor, source=SOURCE, scope=scope, enricher=enricher, record_id=record_id
            ),
        )
    proposed = sum(1 for e in made.events if e.event_type == "Enrichment.Proposed")
    accepted = sum(1 for e in made.events if e.event_type == "Enrichment.Accepted")
    typer.echo(f"proposed {proposed}")
    typer.echo(f"accepted {accepted}")
