"""In-memory integration records for `FakeClient` (P1-I7): the registry reads and the commands a
screen runs. Provided and final; the tickets do not change it.

It follows the services where it is cheap: a switch that is already in the state asked for raises
``IntegrationStateError``, an unknown id ``IntegrationNotFoundError``, an admin command by a
non-admin ``ForbiddenError`` (``is_admin = False``), and an accept of a value that is not waiting
``IntegrationStateError``. ``integration_calls`` records ``(name, scope, fields)``.
"""

from __future__ import annotations

from typing import Any

from tl_core.auth.errors import ForbiddenError
from tl_core.integration.errors import IntegrationNotFoundError, IntegrationStateError
from tl_core.integration.registry import KINDS
from tl_core.services.commands import CommandResult

#: command -> (kind it changes, id field, id column)
_SWITCHES = {
    "EnableRule": ("rules", "rule_id", "rule_id", True),
    "DisableRule": ("rules", "rule_id", "rule_id", False),
    "SetInboundEndpointEnabled": ("endpoints", "endpoint_id", "endpoint_id", None),
    "SetEnricherEnabled": ("enrichers", "enricher_id", "enricher_id", None),
    "SetIntegrationAppEnabled": ("apps", "app_id", "app_id", None),
}
_ADMIN = frozenset(_SWITCHES) | {"RetryInboundDelivery"}


class FakeIntegrationSupport:
    """Mixin for `FakeClient`: call `_init_integration()` from its `__init__`."""

    def _init_integration(self) -> None:
        self._integration: dict[str, list[dict[str, Any]]] = {kind: [] for kind in KINDS}
        self.is_admin_integration = True
        self.integration_calls: list[tuple[str, str, dict[str, Any]]] = []

    def seed_integration(self, kind: str, **row: Any) -> dict[str, Any]:
        """Add one row of ``kind`` (the columns of the projection table, JSON parsed)."""
        assert kind in KINDS, kind
        self._integration[kind].append(row)
        return row

    # --- reads -------------------------------------------------------------------------------

    def list_integration(
        self, kind: str, *, state: str | None = None, limit: int = 200
    ) -> list[dict[str, Any]]:
        self.calls.append("list_integration")  # type: ignore[attr-defined]
        if kind not in KINDS:
            raise IntegrationNotFoundError(f"no integration kind {kind}")
        if kind == "deliveries" and not self.is_admin_integration:
            raise ForbiddenError("this needs the admin role")
        rows = list(self._integration[kind])
        if state is not None:
            column = "acceptance_state" if kind == "enrichments" else "state"
            rows = [r for r in rows if r.get(column) == state]
        return [dict(r) for r in rows[:limit]]

    # --- commands ----------------------------------------------------------------------------

    def integration_command(self, name: str, scope: str, **fields: Any) -> CommandResult:
        self.calls.append("integration_command")  # type: ignore[attr-defined]
        self.integration_calls.append((name, scope, dict(fields)))
        if name in _ADMIN and not self.is_admin_integration:
            raise ForbiddenError(f"{name} needs the admin role")
        if name in _SWITCHES:
            kind, field, column, fixed = _SWITCHES[name]
            row = self._row(kind, column, fields[field])
            wanted = fixed if fixed is not None else bool(fields["enabled"])
            if bool(row["enabled"]) is wanted:
                raise IntegrationStateError(f"already {'on' if wanted else 'off'}")
            row["enabled"] = wanted
        elif name in ("AcceptEnrichment", "RejectEnrichment"):
            row = self._row("enrichments", "value_id", fields["value_id"])
            if row["acceptance_state"] != "proposed":
                raise IntegrationStateError(f"the value is {row['acceptance_state']}, not waiting")
            if name == "AcceptEnrichment":
                row["acceptance_state"] = "accepted"
            else:
                row["acceptance_state"] = "rejected"
                row["reason"] = fields["reason"]
            row["decided_by"] = getattr(self, "actor", "user:dev")
        elif name == "RetryInboundDelivery":
            row = self._row("deliveries", "delivery_id", fields["delivery_id"])
            if row["state"] not in ("failed", "killed"):
                raise IntegrationStateError(
                    f"the delivery is {row['state']}; only a failed one retries"
                )
            row.update(state="queued", error_code=None, error_message=None)
        elif name not in ("RunEnricher", "InvokeAction"):
            raise ValueError(f"{name} is not a command a screen runs")
        return CommandResult(stream_id="fake-" + name, key=None, version=1, events=[])

    def _row(self, kind: str, column: str, value: str) -> dict[str, Any]:
        for row in self._integration[kind]:
            if row.get(column) == value:
                return row
        raise IntegrationNotFoundError(f"no {kind[:-1]} {value}")
