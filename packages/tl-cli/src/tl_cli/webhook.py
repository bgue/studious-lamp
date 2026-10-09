"""The `tl webhook` group, part 1: add, ls, test, replay (brief 18.4).

Each subcommand parses options, makes one call into `tl_core.webhooks`, and prints. Validation,
secrets and delivery rules live in the services; the secret is printed once by `add` and can
never be shown again. Part 2 (dlq, disable, enable, rotate-secret) is `webhook_ops.py`,
registered at the bottom.

STUB (P0-I5-T25): the four command bodies marked `raise NotImplementedError` are the ticket. Remove
this paragraph when done.
"""

from __future__ import annotations

from typing import Annotated

import typer

from tl_cli import webhook_ops

app = typer.Typer(help="Outbound webhooks: subscriptions, tests, replay.", no_args_is_help=True)

PROJECT = Annotated[str | None, typer.Option("--project", help="Project ID; scope project:<ID>.")]
COMPANY = Annotated[bool, typer.Option("--company", help="Company scope instead of a project.")]


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
    raise NotImplementedError


@app.command("ls")
def ls(ctx: typer.Context, project: PROJECT = None, company: COMPANY = False) -> None:
    """List subscriptions (every scope without --project / --company), one line each."""
    raise NotImplementedError


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
    raise NotImplementedError


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
    raise NotImplementedError


webhook_ops.register(app)
