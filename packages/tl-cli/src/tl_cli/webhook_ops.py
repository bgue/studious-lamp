"""The `tl webhook` group, part 2: dlq ls / redrive, disable, enable, rotate-secret (brief 18.4).

`register(app)` adds these commands to the `webhook` group; `webhook.py` calls it. Each subcommand
parses options, makes one call into `tl_core.webhooks`, and prints.
"""

from __future__ import annotations

from typing import Annotated

import typer
from tl_core.webhooks import queries
from tl_core.webhooks.dispatch import Dispatcher
from tl_core.webhooks.subscriptions import (
    DisableWebhookSubscription,
    EnableWebhookSubscription,
    RotateWebhookSecret,
    disable_subscription,
    enable_subscription,
    rotate_secret,
)

from tl_cli.webhook_common import ACTOR, SOURCE, factory, scope_of, service_errors


def register(app: typer.Typer) -> None:
    """Attach the dlq group and the lifecycle commands to the `webhook` app."""
    dlq = typer.Typer(help="The dead-letter queue.", no_args_is_help=True)
    app.add_typer(dlq, name="dlq")

    @dlq.command("ls")
    def dlq_ls(
        ctx: typer.Context,
        subscription: Annotated[
            str | None, typer.Option("--subscription", help="Only this subscription id.")
        ] = None,
    ) -> None:
        """List dead-lettered deliveries, oldest first, one tab-separated line each."""
        with service_errors(), factory(ctx) as opened:
            with opened(readonly=True) as uow:
                rows = queries.list_dlq(uow, subscription)
            cells = (
                "delivery_id",
                "subscription_id",
                "seq",
                "event_id",
                "attempts",
                "last_status",
                "dead_reason",
                "dead_at",
            )
            for row in rows:
                typer.echo("\t".join(str(row[cell]) for cell in cells))

    @dlq.command("redrive")
    def dlq_redrive(
        ctx: typer.Context,
        subscription_id: Annotated[str, typer.Argument(help="Subscription id.")],
        delivery: Annotated[
            list[str] | None,
            typer.Option("--delivery", help="Only this delivery id; repeatable. Default: all."),
        ] = None,
    ) -> None:
        """Re-enqueue dead letters of one subscription."""
        with service_errors(), factory(ctx) as opened:
            count = Dispatcher(opened).redrive(subscription_id, delivery)
            typer.echo(f"redriven {count}")

    @app.command("disable")
    def disable(
        ctx: typer.Context,
        subscription_id: Annotated[str, typer.Argument(help="Subscription id.")],
        project: Annotated[str | None, typer.Option("--project")] = None,
        company: Annotated[bool, typer.Option("--company")] = False,
    ) -> None:
        """Stop a subscription receiving events (reason: owner)."""
        with service_errors(), factory(ctx) as opened:
            scope = scope_of(project, company)
            cmd = DisableWebhookSubscription(
                actor=ACTOR, source=SOURCE, scope=scope, subscription_id=subscription_id
            )
            with opened() as uow:
                disable_subscription(uow, cmd)
            typer.echo(f"disabled {subscription_id}")

    @app.command("enable")
    def enable(
        ctx: typer.Context,
        subscription_id: Annotated[str, typer.Argument(help="Subscription id.")],
        project: Annotated[str | None, typer.Option("--project")] = None,
        company: Annotated[bool, typer.Option("--company")] = False,
    ) -> None:
        """Start a disabled subscription again, from now on (replay what it missed)."""
        with service_errors(), factory(ctx) as opened:
            scope = scope_of(project, company)
            cmd = EnableWebhookSubscription(
                actor=ACTOR, source=SOURCE, scope=scope, subscription_id=subscription_id
            )
            with opened() as uow:
                enable_subscription(uow, cmd)
            typer.echo(f"enabled {subscription_id}")

    @app.command("rotate-secret")
    def rotate_secret_command(
        ctx: typer.Context,
        subscription_id: Annotated[str, typer.Argument(help="Subscription id.")],
        project: Annotated[str | None, typer.Option("--project")] = None,
        company: Annotated[bool, typer.Option("--company")] = False,
        overlap_hours: Annotated[
            float, typer.Option("--overlap-hours", help="How long the old secret keeps signing.")
        ] = 24.0,
    ) -> None:
        """Issue a new signing secret (printed once); the old one signs for the overlap."""
        with service_errors(), factory(ctx) as opened:
            scope = scope_of(project, company)
            cmd = RotateWebhookSecret(
                actor=ACTOR,
                source=SOURCE,
                scope=scope,
                subscription_id=subscription_id,
                overlap_hours=overlap_hours,
            )
            with opened() as uow:
                issued = rotate_secret(uow, cmd)
            typer.echo(f"secret_id {issued.secret_id}")
            typer.echo(f"secret {issued.secret}")
            typer.echo("keep the secret: it is not shown again", err=True)
