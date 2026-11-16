"""The expected failures of the permits module. Each takes a fixed message, never a cell of the
input and never an id the viewer could not read.

Each subclasses a core error class that already has a row in ``tl_api.errors`` (there is no errors
hook yet), so the API maps it by its base. A refusal of who may act is core's ``ForbiddenError``.
"""

from __future__ import annotations

from tl_core.ledger import ConcurrencyError
from tl_core.services.errors import GuardFailedError, InvalidScopeError, InvalidStateError


class PermitScopeError(InvalidScopeError):
    """Permits belong to a project scope."""


class PermitStateError(InvalidStateError):
    """The permit is in a state that does not take the command."""


class PermitRuleError(GuardFailedError):
    """A rule of the fields or of the life of a permit (a window, the longest validity)."""


class PermitBlockedError(GuardFailedError):
    """The issue guards refuse: the message names the blocker codes."""


class StaleVersionError(ConcurrencyError):
    """The record changed since the caller read it (``expected_version`` is not current)."""
