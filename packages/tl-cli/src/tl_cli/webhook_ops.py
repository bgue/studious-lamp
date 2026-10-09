"""The `tl webhook` group, part 2: dlq ls / redrive, disable, enable, rotate-secret (brief 18.4).

`register(app)` adds these commands to the `webhook` group; `webhook.py` calls it. Each subcommand
parses options, makes one call into `tl_core.webhooks`, and prints.

STUB (P0-I5-T26): the five command bodies marked `raise NotImplementedError` are the ticket. Remove
this paragraph when done.
"""

from __future__ import annotations

from typing import Annotated

import typer


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
        raise NotImplementedError

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
        raise NotImplementedError

    @app.command("disable")
    def disable(
        ctx: typer.Context,
        subscription_id: Annotated[str, typer.Argument(help="Subscription id.")],
        project: Annotated[str | None, typer.Option("--project")] = None,
        company: Annotated[bool, typer.Option("--company")] = False,
    ) -> None:
        """Stop a subscription receiving events (reason: owner)."""
        raise NotImplementedError

    @app.command("enable")
    def enable(
        ctx: typer.Context,
        subscription_id: Annotated[str, typer.Argument(help="Subscription id.")],
        project: Annotated[str | None, typer.Option("--project")] = None,
        company: Annotated[bool, typer.Option("--company")] = False,
    ) -> None:
        """Start a disabled subscription again, from now on (replay what it missed)."""
        raise NotImplementedError

    @app.command("rotate-secret")
    def rotate_secret(
        ctx: typer.Context,
        subscription_id: Annotated[str, typer.Argument(help="Subscription id.")],
        project: Annotated[str | None, typer.Option("--project")] = None,
        company: Annotated[bool, typer.Option("--company")] = False,
        overlap_hours: Annotated[
            float, typer.Option("--overlap-hours", help="How long the old secret keeps signing.")
        ] = 24.0,
    ) -> None:
        """Issue a new signing secret (printed once); the old one signs for the overlap."""
        raise NotImplementedError
