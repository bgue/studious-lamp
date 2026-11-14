"""The expected failures of the quality module. Each takes a fixed message, never a cell of the
input and never an id the viewer could not read.

They subclass ``ServiceError``; ``tl_api.errors`` maps each to a status and a stable code (the
registry line is supervisor glue). A refusal of who may act is core's ``ForbiddenError``.
"""

from __future__ import annotations

from tl_core.services.errors import ServiceError


class QualityError(ServiceError):
    """Base of the module's expected failures."""


class QualityScopeError(QualityError):
    """Punch items belong to a project scope."""


class PunchRuleError(QualityError):
    """A rule of the fields: nothing to change, a date, a time in the future."""


class PunchStateError(QualityError):
    """The punch item is in a state that does not take the command (a void one takes none)."""


class StaleVersionError(QualityError):
    """The record changed since the caller read it (``expected_version`` is not the current
    version)."""
