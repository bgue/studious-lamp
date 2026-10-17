"""The expected failures of the cost module. Each takes a readable message.

They subclass ``ServiceError``; ``tl_api.errors`` maps each to a status and a stable code.
"""

from __future__ import annotations

from tl_core.services.errors import ServiceError


class CostError(ServiceError):
    """Base of the module's expected failures."""


class CostScopeError(CostError):
    """Cost codes and snapshots belong to a project scope."""


class InvalidCostSnapshotError(CostError):
    """The snapshot's period, date or figures are not usable; the message says which."""


class CostCodeNotFoundError(CostError):
    """No cost code with that id or code in the scope."""


class CostImportRefusedError(CostError):
    """The rows of the import cannot be applied; ``issues`` lists each problem."""

    def __init__(self, message: str, issues: list[str] | None = None) -> None:
        super().__init__(message)
        self.issues: list[str] = issues if issues is not None else []
