"""``McpCaller``: how the simulator's one agent reaches the suite's MCP server.

``McpClientCaller(target)`` opens an MCP client session per call with ``mcp.Client``. The target is
a ``StdioServerParameters`` (a real server process, ``python -m tl_mcp --actor agent:sim-assistant
--db <ledger>``) or an in-memory ``MCPServer`` (tests).

Two kinds of failure, kept apart:

* The server answered "no" to a tool call (``ToolError``: a duplicate link, an unknown record, an
  exhausted budget, a bad argument): ``ProposalRefusedError`` with the server's own message.
  ``is_duplicate_link`` is the one refusal a realistic day shrugs off; the rest are bugs or
  limits that must surface.
* The server could not be reached, died or did not answer in ``timeout_s`` (30 s by default):
  ``McpUnavailableError``, a ``RunError`` that names the cause and, for a server process, the
  text it printed on stderr (found by starting it once more with its input closed).

The MCP server does not read ``X-TL-Effective-At`` (FANOUT D5 covers the API), so a proposal made
over MCP is stamped with real time; the decision on it and its effect are stamped through the API
(``tl_api.routes.proposals``) and carry simulated time.
"""

from __future__ import annotations

import asyncio
import subprocess
import sys
from pathlib import Path
from typing import Any

from mcp import Client, StdioServerParameters
from mcp.server.mcpserver import MCPServer

from tl_sim.state import RunError

DEFAULT_TIMEOUT_S = 30.0
DUPLICATE_LINK = "link already exists between these records"
DIAGNOSE_TIMEOUT_S = 10.0
STDERR_LIMIT = 600


class ProposalRefusedError(Exception):
    """The MCP server refused a tool call. The message is the server's, for the log."""

    @property
    def is_duplicate_link(self) -> bool:
        return DUPLICATE_LINK in str(self)


class McpUnavailableError(RunError):
    """The MCP server could not be reached, died or timed out. The message says why."""


def _diagnose(params: StdioServerParameters) -> str:
    """What the server process prints when started with its input closed (a bad ledger path)."""
    try:
        done = subprocess.run(
            [params.command, *params.args],
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            timeout=DIAGNOSE_TIMEOUT_S,
            check=False,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        return f"the server could not be started: {exc}"
    text = " ".join(done.stderr.split())
    return text[:STDERR_LIMIT] if done.returncode != 0 and text else ""


class McpClientCaller:
    """Calls one tool of an MCP server and returns its structured result."""

    def __init__(
        self, target: MCPServer | StdioServerParameters, *, timeout_s: float = DEFAULT_TIMEOUT_S
    ) -> None:
        self._target = target
        self._timeout_s = timeout_s

    def call_tool(self, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        try:
            return asyncio.run(asyncio.wait_for(self._call(name, arguments), self._timeout_s))
        except ProposalRefusedError:
            raise
        except TimeoutError as exc:
            raise McpUnavailableError(
                f"the MCP server did not answer {name} within {self._timeout_s:g} s{self._why()}"
            ) from exc
        except (Exception, BaseExceptionGroup) as exc:  # noqa: BLE001 - any transport failure
            raise McpUnavailableError(
                f"cannot reach the MCP server for {name}: {type(exc).__name__}{self._why()}"
            ) from exc

    def _why(self) -> str:
        if isinstance(self._target, StdioServerParameters):
            detail = _diagnose(self._target)
            return f"; the server said: {detail}" if detail else ""
        return ""

    async def _call(self, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        async with Client(self._target, read_timeout_seconds=self._timeout_s) as client:
            result = await client.call_tool(name, arguments)
        if result.is_error:
            text = " ".join(getattr(part, "text", "") for part in result.content).strip()
            raise ProposalRefusedError(text or f"{name} was refused")
        return dict(result.structured_content or {})


def stdio_caller(actor: str, db: Path, *, timeout_s: float = DEFAULT_TIMEOUT_S) -> McpClientCaller:
    """A caller that starts ``python -m tl_mcp`` for ``actor`` on the ledger file ``db``."""
    params = StdioServerParameters(
        command=sys.executable,
        args=["-m", "tl_mcp", "--actor", actor, "--db", str(db)],
    )
    return McpClientCaller(params, timeout_s=timeout_s)
