"""The admin's agent stop calls over HTTP (P2-X2, ADR-0029 decision 6).

Failures raise the embedded exception classes, as the admin client does (``ForbiddenError``,
``AccountNotFoundError``). The stopped list answers the held count the caller may see.
"""

from __future__ import annotations

from tl_core.services.agent_stop import AgentStopResult, StoppedAgent

from tl_api.client.base import ApiClientBase


class AgentStopApi(ApiClientBase):
    def stop_agent(self, agent: str, reason: str | None = None) -> AgentStopResult:
        """Stop an agent (``POST /admin/agents/stop``). `changed` is false when already stopped."""
        data = self._post_json("/admin/agents/stop", {"agent": agent, "reason": reason})
        return self._model(AgentStopResult, data)

    def resume_agent(self, agent: str) -> AgentStopResult:
        """Resume a stopped agent (``POST /admin/agents/resume``).

        `changed` is false when the agent was not stopped.
        """
        data = self._post_json("/admin/agents/resume", {"agent": agent})
        return self._model(AgentStopResult, data)

    def list_stopped_agents(self, limit: int = 200) -> list[StoppedAgent]:
        """The stopped agents with their held counts (``GET /admin/agents/stopped``)."""
        data = self._get_json("/admin/agents/stopped", {"limit": limit})
        return self._models(StoppedAgent, data)
