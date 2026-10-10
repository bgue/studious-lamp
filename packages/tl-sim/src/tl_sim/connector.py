"""``HttpConnector``: the orchestrator's door to a running suite (API over HTTP, MCP for proposals).

``provision`` makes one dev token per simulated identity in the token file the server reads
(``tl_api.tokens.add_token``, ADR-0005: dev identity, not an auth model). The role actors stand in
for people, so they are ``user:sim-<role>``: the API refuses record-changing commands from an
``agent:*`` token (agents propose, people accept). The one simulated agent is
``agent:sim-assistant``. A token already issued for a run is kept in the run state and reused when
the run is reopened.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from pathlib import Path

from tl_api.client import ApiClient
from tl_api.tokens import add_token

from tl_sim.client import HttpSimClient, Keys, McpCaller, connect
from tl_sim.clock import SimClock
from tl_sim.mcp_caller import stdio_caller
from tl_sim.orchestrator import ASSISTANT, ORCHESTRATOR
from tl_sim.reader import HttpReader, SimReader
from tl_sim.scenario import Scenario
from tl_sim.state import RunError
from tl_sim.types import SimClient


class HttpConnector:
    def __init__(
        self,
        base_url: str,
        tokens_path: Path,
        *,
        run_id: str,
        db_path: Path | None = None,
        mcp: Callable[[str], McpCaller | None] | None = None,
    ) -> None:
        self.base_url = base_url
        self.tokens_path = tokens_path
        self.run_id = run_id
        self.db_path = db_path
        self._mcp = mcp

    @property
    def scope(self) -> str:
        return f"project:sim-{self.run_id}"

    def check(self, scenario: Scenario) -> None:
        """The agent's MCP server opens the ledger file; without it nothing could be proposed."""
        if scenario.actors.assistant is None or self._mcp is not None:
            return
        if self.db_path is None or not self.db_path.is_file():
            raise RunError(
                f"the scenario has an assistant (an agent that proposes over MCP) but there is "
                f"no ledger file at {self.db_path}; run `tl init`, or set TL_DB or `tl --db`"
            )

    def provision(self, identities: Sequence[str]) -> dict[str, str]:
        return {identity: add_token(self.tokens_path, identity) for identity in identities}

    def client(
        self, identity: str, clock: SimClock, keys: Keys, tokens: dict[str, str]
    ) -> SimClient:
        api = connect(self.base_url, tokens[identity], clock)
        return HttpSimClient(
            api,
            run_id=self.run_id,
            scope=self.scope,
            clock=clock,
            keys=keys,
            identity=identity,
            mcp=self._mcp_for(identity),
        )

    def _mcp_for(self, identity: str) -> McpCaller | None:
        """The agent reaches the MCP server (a process on the ledger file); people do not."""
        if self._mcp is not None:
            return self._mcp(identity)
        if identity == ASSISTANT and self.db_path is not None:
            return stdio_caller(identity, self.db_path)
        return None

    def reader(self, tokens: dict[str, str]) -> SimReader:
        return HttpReader(ApiClient(self.base_url, tokens[ORCHESTRATOR]), self.scope)
