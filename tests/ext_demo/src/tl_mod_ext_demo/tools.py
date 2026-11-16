"""The agent tool of the ext_demo module (ADR-0029).

The tool is closed to agents until an allow row names the action `mcp.ext_demo_get_note`. It
reads under `guarded`, which sets the lowest clearance, so a hidden note answers as a missing one.
"""

from __future__ import annotations

from mcp.server.mcpserver import MCPServer
from mcp.types import ToolAnnotations
from tl_core import confidentiality
from tl_core.services.errors import RecordNotFoundError
from tl_mcp.context import McpContext
from tl_mcp.errors import guarded, resource_name

from . import MODULE, MSG_NOT_FOUND
from .views import NoteView, get_note

READ_ONLY = ToolAnnotations(read_only_hint=True, destructive_hint=False, open_world_hint=False)


def register_tools(server: MCPServer, ctx: McpContext) -> None:
    @server.tool(name="ext_demo_get_note", annotations=READ_ONLY)
    def ext_demo_get_note(scope: str, key: str) -> NoteView:
        """One note of a project (scope `project:<id>`). A hidden note answers as a missing one."""
        with guarded(ctx, "ext_demo_get_note", resource_name(MODULE, scope, key)):
            with ctx.factory(True) as uow:
                found = get_note(uow.conn(), scope, key, viewer=confidentiality.current_viewer())
            if found is None:
                raise RecordNotFoundError(MSG_NOT_FOUND)
            return found
