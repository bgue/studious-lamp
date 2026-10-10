"""Turns the failures a tool or resource can meet into MCP tool errors, after the authorise hook.

Every tool and resource body runs inside :func:`guarded`. The hook is called first with
``(actor, "mcp.<tool>", resource)``; then any expected failure becomes a ``ToolError`` whose text
the agent sees: the service's own message, and for a query syntax error the position.
"""

from __future__ import annotations

import urllib.parse
from collections.abc import Iterator, Sequence
from contextlib import contextmanager

from mcp.server.mcpserver.exceptions import ResourceError, ToolError
from pydantic import ValidationError
from tl_api.auth import Forbidden
from tl_api.errors import ApiError
from tl_core.ledger import ConcurrencyError
from tl_core.query import QuerySyntaxError
from tl_core.services.errors import ServiceError
from tl_lake import GuardError, LakeError, LakeLockTimeout, LakeNotInitialisedError, QueryError

from tl_mcp.context import McpContext

LAKE_NOT_SYNCED = "the lake has not been synced yet: run `tl lake sync`"
LAKE_BUSY = "the lake is busy: try again in a moment"


def describe_lake_error(exc: LakeError) -> str:
    """What an agent may read about a lake failure: a fixed sentence, never a server path.

    Lake exceptions carry the lake directory or an operating-system message with a path, so only
    a ``QueryError`` (whose text the lake service has already stripped of paths) is passed on.
    """
    if isinstance(exc, LakeNotInitialisedError):
        return LAKE_NOT_SYNCED
    if isinstance(exc, LakeLockTimeout):
        return LAKE_BUSY
    if isinstance(exc, QueryError):
        return str(exc)
    return f"the lake is unavailable ({type(exc).__name__}); see the server log"


def describe(exc: BaseException) -> str:
    """One line an agent can act on."""
    if isinstance(exc, LakeError):
        return describe_lake_error(exc)
    if isinstance(exc, QuerySyntaxError):
        return f"query syntax error at position {exc.position}: {exc}"
    if isinstance(exc, GuardError):
        return f"refused: {exc}"
    if isinstance(exc, ValidationError):
        return "; ".join(f"{'.'.join(str(p) for p in e['loc'])}: {e['msg']}" for e in exc.errors())
    return str(exc) or exc.__class__.__name__


MAX_PART = 128  # scope, key, record id and record type


def check_parts(parts: Sequence[tuple[str, str]]) -> None:
    """Raise ``ValueError`` for an empty or oversized identifier part (before any hook runs)."""
    for name, value in parts:
        if not value.strip():
            raise ValueError(f"{name} must not be empty")
        if len(value) > MAX_PART:
            raise ValueError(f"{name} is longer than {MAX_PART} characters")


def resource_name(kind: str, *parts: str) -> str:
    """The unambiguous resource string the hook sees: ``record:project%3AP1/K-1``."""
    return f"{kind}:" + "/".join(urllib.parse.quote(part, safe="") for part in parts)


@contextmanager
def guarded(
    ctx: McpContext,
    tool: str,
    resource: str,
    *,
    error: type[Exception] = ToolError,
    parts: Sequence[tuple[str, str]] = (),
) -> Iterator[None]:
    """Check ``parts``, authorise, then run the body.

    Expected failures become ``error`` (``ToolError``, or ``ResourceError`` for resources) with a
    message the agent can read. ``parts`` (name, value) pairs must be non-empty and at most
    ``MAX_PART`` characters; that is checked before the authorise hook runs.
    """
    try:
        check_parts(parts)
        ctx.authorize(ctx.actor, f"mcp.{tool}", resource)
        yield
    except (ToolError, ResourceError):
        raise
    except Forbidden as exc:
        raise error(f"not allowed: {exc}") from exc
    except (ServiceError, ConcurrencyError, ValidationError, ValueError, LakeError) as exc:
        raise error(describe(exc)) from exc
    except ApiError as exc:  # the shared query-parameter helpers raise this
        raise error(exc.message) from exc
