"""``rebuild_projections``: reset projectors of the dev database and replay the ledger into them
(brief 25.3 and 25.4, FANOUT D12). The ledger is never written; only projection rows change."""

from __future__ import annotations

from typing import Annotated

from mcp.server.mcpserver import MCPServer
from mcp.types import ToolAnnotations
from pydantic import BaseModel, Field
from sqlalchemy.exc import SQLAlchemyError
from tl_adapters import db as adapters_db
from tl_core.projection.defaults import default_registry

from tl_mcp.dev.errors import DevToolFailure
from tl_mcp.dev.runtime import DevContext, guarded

REBUILD = ToolAnnotations(
    read_only_hint=False, destructive_hint=False, idempotent_hint=True, open_world_hint=False
)
MAX_ONLY_ITEMS = 20
MAX_ONLY_CHARS = 64


class RebuildOutput(BaseModel):
    """The answer of ``rebuild_projections``."""

    replayed: int  # events replayed from the ledger
    projectors: list[str]  # the projectors rebuilt, in registry order
    dialect: str  # "sqlite" or "postgres"


def register(server: MCPServer, ctx: DevContext) -> None:
    @server.tool(annotations=REBUILD)
    def rebuild_projections(
        only: Annotated[
            list[Annotated[str, Field(max_length=MAX_ONLY_CHARS)]] | None,
            Field(
                max_length=MAX_ONLY_ITEMS,
                description="Projector names to rebuild; default: all of them.",
            ),
        ] = None,
    ) -> RebuildOutput:
        """Reset projectors of the dev database and replay the whole ledger into them, in one
        transaction (on a SQLite file under dev/ or a temp directory, or a local tl_test*/tl_dev*
        Postgres). If the replay fails nothing changes. The ledger is not touched.

        Projector names: core_record, pset_values, links, numbering, workflow, files,
        webhook_subscriptions, webhook_state, proposals, feed, outbox.
        """
        with guarded(ctx, "rebuild_projections", {"only": only}):
            if ctx.target.kind == "sqlite":
                assert ctx.target.path is not None
                if not ctx.target.path.exists():
                    raise DevToolFailure(
                        "the dev database does not exist yet: run `tl init` or the seed tool"
                    )
            names = [projector.name for projector in default_registry().all()]
            if only:
                unknown = sorted(set(only) - set(names))
                if unknown:
                    raise ValueError(
                        f"unknown projector(s): {', '.join(unknown)}; valid: {', '.join(names)}"
                    )
            selected = [name for name in names if not only or name in only]
            try:
                replayed = adapters_db.rebuild_projections(ctx.target.db_arg, types=only or None)
            except SQLAlchemyError as exc:
                raise DevToolFailure(f"rebuild failed: {type(exc).__name__}") from exc
            return RebuildOutput(replayed=replayed, projectors=selected, dialect=ctx.target.dialect)
