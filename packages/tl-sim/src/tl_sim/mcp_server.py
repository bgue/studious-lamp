"""The simulation orchestrator as an MCP server (brief 29.5: "its own MCP server").

Tools: ``sim_create``, ``sim_advance``, ``sim_inject``, ``sim_status`` and ``sim_assert``.

    uv run python -m tl_sim.mcp_server [--actor user:sim-orchestrator]    # stdio
    # TL_SIM_DIR, TL_API_URL, TL_TOKENS as for `tl sim`

Each tool is one call into ``tl_sim.api`` with the ``SimEnv`` the server was built with, made after
the authorise hook (the ``tl_mcp`` convention: ``hook(actor, "sim.<tool>", resource)``, allow-all
today, ADR-0005). The tools that play or create change the world (they write through the suite's
API), so they are not read-only; none of them is destructive.

Remote callers get less than the CLI: ``sim_create`` takes a bundled scenario name only, never a
path (``load_bundled_scenario``), and an error shows ``ScenarioError.public``, which holds no path,
file content or parser text. A failure the simulator knows becomes a ``ToolError``; anything else
is a bug and surfaces as the SDK's generic error.
"""

from __future__ import annotations

import argparse
import urllib.parse
from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from typing import Annotated, Any

from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from mcp.types import ToolAnnotations
from pydantic import Field, ValidationError
from tl_api.auth import Forbidden, authorize
from tl_api.errors import ApiError
from tl_api.tokens import check_actor
from tl_core.services.errors import ServiceError

from tl_sim import api
from tl_sim.scenario import MAX_INJECT_KEYS
from tl_sim.scenario_loader import BUNDLED_NAME, ScenarioError
from tl_sim.state import RunError

DEFAULT_ACTOR = "user:sim-orchestrator"
Authorizer = api.Authorizer

INSTRUCTIONS = (
    "Plays a simulated construction project against the Throughline API. `sim_create` makes a run "
    "from a bundled scenario name and writes its seed records; `sim_advance` plays working "
    "days; `sim_inject` queues material_late, design_revision or post for the next day played; "
    "`sim_status` shows the day and the ground-truth counts; `sim_assert` compares what the "
    "scenario intended with what the suite holds. `run_id` may be left out while one run exists."
)

WRITES = ToolAnnotations(read_only_hint=False, destructive_hint=False, open_world_hint=False)
READS = ToolAnnotations(read_only_hint=True, destructive_hint=False, open_world_hint=False)

RunId = Annotated[
    str | None,
    Field(max_length=24, description="The run id; optional while exactly one run exists."),
]
Event = Annotated[str, Field(max_length=32, description="material_late, design_revision or post.")]
ScenarioName = Annotated[
    str,
    Field(
        pattern=f"^{BUNDLED_NAME}$",
        description="The name of a bundled scenario, for example north-unit-small. Not a path.",
    ),
]


def _resource(kind: str, value: str | None) -> str:
    return f"{kind}:" + urllib.parse.quote(value or "-", safe="")


@contextmanager
def _guarded(hook: Authorizer, actor: str, tool: str, resource: str) -> Iterator[None]:
    """Authorise first, then run the body; expected failures become a ``ToolError``."""
    try:
        hook(actor, f"sim.{tool}", resource)
        yield
    except ToolError:
        raise
    except Forbidden as exc:
        raise ToolError(f"not allowed: {exc}") from exc
    except ValidationError as exc:  # before ValueError, which it subclasses
        raise ToolError(
            "; ".join(f"{'.'.join(str(p) for p in e['loc'])}: {e['msg']}" for e in exc.errors())
        ) from exc
    except ScenarioError as exc:
        raise ToolError(exc.public) from exc
    except (RunError, ApiError, ServiceError, ValueError) as exc:
        raise ToolError(str(exc) or exc.__class__.__name__) from exc


def build_server(
    env: api.SimEnv, *, actor: str = DEFAULT_ACTOR, authorize_hook: Authorizer = authorize
) -> MCPServer:
    """An MCP server whose tools act on the runs and the API that ``env`` names, as ``actor``."""
    check_actor(actor)
    server = MCPServer("throughline-sim", instructions=INSTRUCTIONS)

    @server.tool(annotations=WRITES)
    def sim_create(scenario: ScenarioName, run_id: RunId = None) -> dict[str, Any]:
        """Create a run from a bundled scenario, provision the actors and write the seed records."""
        with _guarded(authorize_hook, actor, "create", _resource("scenario", scenario)):
            return api.sim_create(env, scenario, run_id=run_id, bundled_only=True)

    @server.tool(annotations=WRITES)
    def sim_advance(
        run_id: RunId = None,
        days: Annotated[int, Field(ge=1, le=366, description="Working days to play.")] = 1,
    ) -> dict[str, Any]:
        """Play working days; each actor acts in its own slot and its ground truth is logged."""
        with _guarded(authorize_hook, actor, "advance", _resource("run", run_id)):
            return api.sim_advance(env, run_id, days=days)

    @server.tool(annotations=WRITES)
    def sim_inject(
        event: Event,
        args: Annotated[
            dict[str, Any] | None,
            Field(
                max_length=MAX_INJECT_KEYS,
                description="material_late: item, days. design_revision: count (at most 20). "
                "post: actor, body. Strings are at most 2000 characters.",
            ),
        ] = None,
        run_id: RunId = None,
    ) -> dict[str, Any]:
        """Queue an event for the next day played."""
        with _guarded(authorize_hook, actor, "inject", _resource("run", run_id)):
            return api.sim_inject(env, run_id, event, args)

    @server.tool(annotations=READS)
    def sim_status(run_id: RunId = None) -> dict[str, Any]:
        """The run's day, next date, ground-truth counts by intent and their digest."""
        with _guarded(authorize_hook, actor, "status", _resource("run", run_id)):
            return api.sim_status(env, run_id)

    @server.tool(annotations=READS)
    def sim_assert(run_id: RunId = None) -> dict[str, Any]:
        """Compare the ground truth with the suite; `failures` lists every difference."""
        with _guarded(authorize_hook, actor, "assert", _resource("run", run_id)):
            return api.sim_assert(env, run_id)

    return server


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="tl-sim-mcp", description="Simulator MCP server.")
    parser.add_argument("--actor", default=DEFAULT_ACTOR, help="user:<id> or agent:<id>")
    args = parser.parse_args(argv)
    try:
        check_actor(args.actor)
    except ValueError as exc:
        parser.error(str(exc))
    build_server(api.SimEnv.from_env(), actor=args.actor).run("stdio")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
