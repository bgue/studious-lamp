"""The `tl webhook` group, part 1: add, ls, test, replay (brief 18.4).

Each subcommand parses options, makes one call into `tl_core.webhooks`, and prints. Validation,
secrets and delivery rules live in the services; the secret is printed once by `add` and can
never be shown again. Part 2 (dlq, disable, enable, rotate-secret) is `webhook_ops.py`,
registered at the bottom.
"""

from __future__ import annotations

import time
from datetime import UTC, datetime
from typing import Annotated, Any

import typer
from tl_core.webhooks import queries
from tl_core.webhooks.subscriptions import CreateWebhookSubscription, create_subscription
from tl_core.webhooks.wiring import make_dispatcher, make_engine
from tl_core.webhooks.worker import WebhookWorker

from tl_cli import webhook_ops
from tl_cli.webhook_common import ACTOR, SOURCE, factory, fail, scope_of, service_errors

app = typer.Typer(help="Outbound webhooks: subscriptions, tests, replay.", no_args_is_help=True)

PROJECT = Annotated[str | None, typer.Option("--project", help="Project ID; scope project:<ID>.")]
COMPANY = Annotated[bool, typer.Option("--company", help="Company scope instead of a project.")]


def _moment(text: str) -> datetime:
    """An ISO-8601 time as an aware datetime; without an offset it is UTC (bad text: ValueError)."""
    moment = datetime.fromisoformat(text)
    return moment if moment.tzinfo is not None else moment.replace(tzinfo=UTC)


@app.command("add")
def add(
    ctx: typer.Context,
    name: Annotated[str, typer.Option("--name", help="Short label.")],
    url: Annotated[str, typer.Option("--url", help="Receiver URL (https).")],
    project: PROJECT = None,
    company: COMPANY = False,
    mode: Annotated[str, typer.Option("--mode", help="thin, delta or full.")] = "thin",
    event_type: Annotated[
        list[str] | None, typer.Option("--event-type", help="Event type or glob; repeatable.")
    ] = None,
    selector: Annotated[
        str | None, typer.Option("--selector", help="Query-language expression for the record.")
    ] = None,
    record_id: Annotated[
        list[str] | None, typer.Option("--record-id", help="Subject record id; repeatable.")
    ] = None,
    changed_field: Annotated[
        list[str] | None, typer.Option("--changed-field", help="Changed field path; repeatable.")
    ] = None,
    transition: Annotated[
        list[str] | None, typer.Option("--transition", help="'From -> To'; repeatable.")
    ] = None,
    link_relation: Annotated[
        list[str] | None, typer.Option("--link-relation", help="Link relation; repeatable.")
    ] = None,
    file_slot: Annotated[
        list[str] | None, typer.Option("--file-slot", help="File slot; repeatable.")
    ] = None,
    hashtag: Annotated[
        list[str] | None, typer.Option("--hashtag", help="Hashtag; repeatable.")
    ] = None,
    scope_selector: Annotated[
        str | None, typer.Option("--scope-selector", help="Scope id or glob.")
    ] = None,
    expires: Annotated[
        str | None, typer.Option("--expires", help="ISO-8601 time the subscription ends.")
    ] = None,
) -> None:
    """Create a subscription. Prints its id and its signing secret, once."""
    scope = scope_of(project, company)
    given: dict[str, Any] = {
        "event_types": event_type,
        "record_selector": selector,
        "record_ids": record_id,
        "changed_fields": changed_field,
        "transitions": transition,
        "link_relations": link_relation,
        "file_slots": file_slot,
        "hashtags": hashtag,
        "scope_selector": scope_selector,
    }
    flt = {key: value for key, value in given.items() if value is not None and value != []}
    with factory(ctx) as opened:
        with service_errors():
            expires_at = None if expires is None else _moment(expires)
            with opened() as uow:
                issued = create_subscription(
                    uow,
                    CreateWebhookSubscription(
                        actor=ACTOR,
                        source=SOURCE,
                        scope=scope,
                        name=name,
                        target_url=url,
                        filter=flt,
                        payload_mode=mode,
                        expires_at=expires_at,
                    ),
                )
            typer.echo(f"subscription {issued.subscription_id}")
            typer.echo(f"secret_id {issued.secret_id}")
            typer.echo(f"secret {issued.secret}")
            typer.echo("keep the secret: it is not shown again", err=True)


@app.command("ls")
def ls(ctx: typer.Context, project: PROJECT = None, company: COMPANY = False) -> None:
    """List subscriptions (every scope without --project / --company), one line each."""
    scope = scope_of(project, company) if project is not None or company else None
    columns = (
        "subscription_id",
        "status_label",
        "payload_mode",
        "name",
        "target_url",
        "delivered_total",
        "pending",
        "dead",
    )
    with factory(ctx) as opened:
        with service_errors():
            with opened(readonly=True) as uow:
                rows = queries.list_subscriptions(uow, scope)
            for row in rows:
                typer.echo("\t".join(str(row[column]) for column in columns))


@app.command("test")
def test(
    ctx: typer.Context,
    subscription_id: Annotated[str, typer.Argument(help="Subscription id.")],
    event_type: Annotated[
        str, typer.Option("--event-type", help="Catalog event type to send.")
    ] = "Record.Created",
    allow_host: Annotated[
        list[str] | None,
        typer.Option("--allow-host", help="Egress allow-list entry (host, host:port, IP, CIDR)."),
    ] = None,
) -> None:
    """Send a signed catalog sample to the subscription's URL and report the answer."""
    with factory(ctx) as opened:
        with service_errors():
            result = make_engine(opened, allow_hosts=allow_host or ()).send_test(
                subscription_id, event_type
            )
            typer.echo(f"event_id {result.event_id}")
            typer.echo(f"status {'-' if result.status is None else result.status}")
            typer.echo(f"latency_ms {result.latency_ms}")
            if result.blocked:
                fail(
                    "the target is blocked by the egress policy; "
                    "allow-list it with --allow-host or TL_WEBHOOK_ALLOWLIST"
                )
            if not result.ok:
                fail(result.error or f"the receiver answered HTTP {result.status}")


@app.command("replay")
def replay(
    ctx: typer.Context,
    subscription_id: Annotated[str, typer.Argument(help="Subscription id.")],
    from_seq: Annotated[int | None, typer.Option("--from-seq", help="First seq.")] = None,
    to_seq: Annotated[int | None, typer.Option("--to-seq", help="Last seq.")] = None,
    since: Annotated[str | None, typer.Option("--since", help="ISO-8601 start time.")] = None,
    until: Annotated[str | None, typer.Option("--until", help="ISO-8601 end time.")] = None,
) -> None:
    """Re-send a seq range or a time range to one subscription."""
    if from_seq is not None and to_seq is not None and since is None and until is None:
        with factory(ctx) as opened:
            with service_errors():
                count = make_dispatcher(opened).replay(subscription_id, from_seq, to_seq)
                typer.echo(f"replayed {count}")
    elif since is not None and until is not None and from_seq is None and to_seq is None:
        with factory(ctx) as opened:
            with service_errors():
                count = make_dispatcher(opened).replay_between(
                    subscription_id, _moment(since), _moment(until)
                )
                typer.echo(f"replayed {count}")
    else:
        fail("give --from-seq and --to-seq, or --since and --until")


@app.command("run")
def run(
    ctx: typer.Context,
    once: Annotated[
        bool, typer.Option("--once", help="Deliver what is due now, print a summary and exit.")
    ] = False,
    allow_host: Annotated[
        list[str] | None,
        typer.Option("--allow-host", help="Egress allow-list entry (host, host:port, IP, CIDR)."),
    ] = None,
    threads: Annotated[int, typer.Option("--threads", min=1, help="Parallel sends.")] = 4,
    interval: Annotated[
        float, typer.Option("--interval", min=0.05, help="Seconds between idle cycles.")
    ] = 0.5,
) -> None:
    """Run the webhook worker: dispatch new events and deliver them, until interrupted."""
    with service_errors(), factory(ctx) as opened:
        worker = WebhookWorker(
            make_dispatcher(opened),
            make_engine(opened, allow_hosts=allow_host or ()),
            threads=threads,
            interval_s=interval,
        )
        if once:
            total = worker.drain()
            for name in ("dispatched", "claimed", "delivered", "retried", "dead", "disabled"):
                typer.echo(f"{name} {getattr(total, name)}")
            return
        typer.echo("webhook worker running; press Ctrl-C to stop", err=True)
        with worker:
            try:
                while worker.running:
                    time.sleep(0.2)
            except KeyboardInterrupt:
                typer.echo("stopping", err=True)


webhook_ops.register(app)
