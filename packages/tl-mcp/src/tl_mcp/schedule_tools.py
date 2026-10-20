"""Schedule tools: propose to publish a schedule snapshot (P1-I4, ADR-0015).

``propose_publish_schedule_snapshot`` never changes anything: it builds the command the API would
run, has it checked by the handler's own rules (a dry run that is rolled back) and files a pending
proposal. A person accepts it in the review queue, and accepting runs the command as that person,
so it needs the document controller or admin role: what the project's current schedule is must
not be changed by anyone who is signed in, and an agent never changes a record itself. The reads
of schedules and cost are in ``tl_mcp.schedule_read_tools``.
"""

from __future__ import annotations

from typing import Annotated

from mcp.server.mcpserver import MCPServer
from pydantic import Field
from tl_core.services import proposals
from tl_mod_schedule import views
from tl_mod_schedule.handlers.publish import PublishScheduleSnapshot

from tl_mcp.context import McpContext
from tl_mcp.errors import MAX_PART, guarded, resource_name
from tl_mcp.write_tools import (  # pyright: ignore[reportPrivateUsage]
    PROPOSES,
    ProposalResult,
    Summary,
    _result,
)

Project = Annotated[
    str,
    Field(min_length=1, max_length=MAX_PART, description="The project id, for example `P123`."),
]
Code = Annotated[
    str, Field(min_length=1, max_length=MAX_PART, description="The schedule's code, `MAIN`.")
]


def propose_publish_impl(
    ctx: McpContext, *, project: str, code: str, number: int, summary: str | None
) -> ProposalResult:
    scope = f"project:{project}"
    with ctx.factory(True) as uow:
        schedule = views.find_schedule(uow.conn(), scope, code)
        snapshot = views.find_snapshot(uow.conn(), schedule, number)
    command = PublishScheduleSnapshot(
        actor=ctx.actor,
        source=proposals.source_for(ctx.actor),
        scope=scope,
        snapshot_id=snapshot.id,
    )
    view = proposals.submit(
        ctx.factory,
        tool="propose_publish_schedule_snapshot",
        agent=ctx.actor,
        command=command,
        summary=summary
        or f"Publish {snapshot.key} (data date {snapshot.data_date}) as the current schedule",
    )
    return _result(view)


def register_schedule_tools(server: MCPServer, ctx: McpContext) -> None:
    """Add the proposing tool to ``server``."""

    @server.tool(annotations=PROPOSES)
    def propose_publish_schedule_snapshot(
        project: Project,
        schedule: Code,
        number: Annotated[
            int, Field(ge=1, le=10**9, description="The snapshot's number within the schedule.")
        ],
        summary: Summary = None,
    ) -> ProposalResult:
        """Propose making a valid schedule snapshot the current schedule.

        Nothing is published now. The proposal is checked now, so an error means it could not be
        applied (the snapshot is not `Valid`, or its data date is not later than the current
        snapshot's). Accepting needs the document controller or admin role. Publishing flags the
        links to activities that are not in the new snapshot, and restores the ones that came
        back. Use `compare_schedule_snapshots` first to see what the new snapshot changes.
        """
        with guarded(
            ctx, "propose_publish_schedule_snapshot", resource_name("schedule", project, schedule)
        ):
            return propose_publish_impl(
                ctx, project=project, code=schedule, number=number, summary=summary
            )
