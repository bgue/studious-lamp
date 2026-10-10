"""The simulation orchestrator as an MCP server (brief 29.5: "its own MCP server").

Tools: ``sim_create``, ``sim_advance``, ``sim_inject``, ``sim_status`` and ``sim_assert``.

    uv run python -m tl_sim.mcp_server    # stdio; TL_SIM_DIR, TL_API_URL, TL_TOKENS as `tl sim`

Each tool is one call into ``tl_sim.api`` with the ``SimEnv`` the server was built with. The tools
change the world (they write through the suite's API), so they are not read-only; none of them is
destructive. A failure the simulator knows (``RunError``, ``ScenarioError``, an API error, bad
arguments) becomes a ``ToolError`` whose text is the message; anything else is a bug and surfaces.
"""

from __future__ import annotations

from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from typing import Annotated, Any

from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from mcp.types import ToolAnnotations
from pydantic import Field, ValidationError
from tl_api.errors import ApiError
from tl_core.services.errors import ServiceError

from tl_sim import api
from tl_sim.scenario_loader import ScenarioError
from tl_sim.state import RunError

INSTRUCTIONS = (
    "Plays a simulated construction project against the Throughline API. `sim_create` makes a run "
    "from a scenario name or YAML path and writes its seed records; `sim_advance` plays working "
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


@contextmanager
def _known_failures() -> Iterator[None]:
    try:
        yield
    except ToolError:
        raise
    except ValidationError as exc:  # before ValueError, which it subclasses
        raise ToolError(
            "; ".join(f"{'.'.join(str(p) for p in e['loc'])}: {e['msg']}" for e in exc.errors())
        ) from exc
    except (RunError, ScenarioError, ApiError, ServiceError, ValueError) as exc:
        raise ToolError(str(exc) or exc.__class__.__name__) from exc


def build_server(env: api.SimEnv) -> MCPServer:
    """An MCP server whose tools act on the runs and the API that ``env`` names."""
    server = MCPServer("throughline-sim", instructions=INSTRUCTIONS)

    @server.tool(annotations=WRITES)
    def sim_create(
        scenario: Annotated[
            str, Field(min_length=1, max_length=256, description="A bundled name or a YAML path.")
        ],
        run_id: RunId = None,
    ) -> dict[str, Any]:
        """Create a run from a scenario, provision the actors and write the seed records."""
        with _known_failures():
            return api.sim_create(env, scenario, run_id=run_id)

    @server.tool(annotations=WRITES)
    def sim_advance(
        run_id: RunId = None,
        days: Annotated[int, Field(ge=1, le=366, description="Working days to play.")] = 1,
    ) -> dict[str, Any]:
        """Play working days; each actor acts in its own slot and its ground truth is logged."""
        with _known_failures():
            return api.sim_advance(env, run_id, days=days)

    @server.tool(annotations=WRITES)
    def sim_inject(
        event: Event,
        args: Annotated[
            dict[str, Any] | None,
            Field(
                description="material_late: item, days. design_revision: count. post: actor, body."
            ),
        ] = None,
        run_id: RunId = None,
    ) -> dict[str, Any]:
        """Queue an event for the next day played."""
        with _known_failures():
            return api.sim_inject(env, run_id, event, args)

    @server.tool(annotations=READS)
    def sim_status(run_id: RunId = None) -> dict[str, Any]:
        """The run's day, next date, ground-truth counts by intent and their digest."""
        with _known_failures():
            return api.sim_status(env, run_id)

    @server.tool(annotations=READS)
    def sim_assert(run_id: RunId = None) -> dict[str, Any]:
        """Compare the ground truth with the suite; `failures` lists every difference."""
        with _known_failures():
            return api.sim_assert(env, run_id)

    return server


def main(argv: Sequence[str] | None = None) -> int:
    del argv  # the environment variables are the only configuration
    build_server(api.SimEnv.from_env()).run("stdio")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
