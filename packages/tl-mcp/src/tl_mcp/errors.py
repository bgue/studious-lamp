"""Turns the failures a tool or resource can meet into MCP tool errors, after the authorise hook.

Every tool and resource body runs inside :func:`guarded`. The hook is called first with
``(actor, "mcp.<tool>", resource)``; then any expected failure becomes a ``ToolError`` whose text
the agent sees: the service's own message, and for a query syntax error the position.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager

from mcp.server.mcpserver.exceptions import ResourceError, ToolError
from pydantic import ValidationError
from tl_api.auth import Forbidden
from tl_api.errors import ApiError
from tl_core.ledger import ConcurrencyError
from tl_core.query import QuerySyntaxError
from tl_core.services.errors import ServiceError

from tl_mcp.context import McpContext


def describe(exc: BaseException) -> str:
    """One line an agent can act on."""
    if isinstance(exc, QuerySyntaxError):
        return f"query syntax error at position {exc.position}: {exc}"
    if isinstance(exc, ValidationError):
        return "; ".join(f"{'.'.join(str(p) for p in e['loc'])}: {e['msg']}" for e in exc.errors())
    return str(exc) or exc.__class__.__name__


@contextmanager
def guarded(
    ctx: McpContext, tool: str, resource: str, *, error: type[Exception] = ToolError
) -> Iterator[None]:
    """Authorise, then run the body; expected failures become ``error`` (``ToolError``, or
    ``ResourceError`` for resources) carrying a message the agent can read."""
    try:
        ctx.authorize(ctx.actor, f"mcp.{tool}", resource)
        yield
    except (ToolError, ResourceError):
        raise
    except Forbidden as exc:
        raise error(f"not allowed: {exc}") from exc
    except (ServiceError, ConcurrencyError, ValidationError, ValueError) as exc:
        raise error(describe(exc)) from exc
    except ApiError as exc:  # the shared query-parameter helpers raise this
        raise error(exc.message) from exc
