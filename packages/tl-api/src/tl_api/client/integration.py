"""The integration layer over HTTP for a screen: the registry reads and the person's commands.

``list_integration`` is ``GET /integration/<kind>`` (``GET /admin/integration/deliveries`` for the
error queue, an admin's); ``integration_command`` is ``POST /commands/<name>`` for the commands a
registry or review screen runs. The server decides who may: a refusal is the usual
``ForbiddenError`` or ``IntegrationNotFoundError``. No call returns a secret.
"""

from __future__ import annotations

from typing import Any

from tl_core.services.commands import CommandResult

from tl_api.client.base import ApiClientBase, quote

#: The commands a screen may run through ``integration_command`` (the server checks the access).
SCREEN_COMMANDS = frozenset(
    {
        "EnableRule",
        "DisableRule",
        "SetInboundEndpointEnabled",
        "SetEnricherEnabled",
        "SetIntegrationAppEnabled",
        "AcceptEnrichment",
        "RejectEnrichment",
        "RunEnricher",
        "RetryInboundDelivery",
        "InvokeAction",
    }
)


class IntegrationApi(ApiClientBase):
    def list_integration(
        self, kind: str, *, state: str | None = None, limit: int = 200
    ) -> list[dict[str, Any]]:
        """The rows of one kind: apps, actions, rules, endpoints, enrichers, invocations,
        enrichments, or deliveries (admin)."""
        path = (
            "/admin/integration/deliveries"
            if kind == "deliveries"
            else f"/integration/{quote(kind)}"
        )
        params: dict[str, Any] = {"limit": limit}
        if state is not None:
            params["state"] = state
        found = self._get_json(path, params)
        return [dict(row) for row in found["rows"]]

    def integration_command(self, name: str, scope: str, **fields: Any) -> CommandResult:
        """Run one of ``SCREEN_COMMANDS`` (``POST /commands/<name>``) as the token's actor."""
        if name not in SCREEN_COMMANDS:
            raise ValueError(f"{name} is not a command a screen runs")
        body = {"scope": scope, "source": "tui", **fields}
        return CommandResult.model_validate(self._post_json(f"/commands/{name}", body))
