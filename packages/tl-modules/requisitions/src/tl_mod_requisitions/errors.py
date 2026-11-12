"""The expected failures of the requisitions module. Each takes a fixed message, never a cell of the
input and never an id the viewer could not read.

They subclass ``ServiceError``; ``tl_api.errors`` maps each to a status and a stable code (the
registry line is supervisor glue). A refusal of who may act is core's ``ForbiddenError``.
"""

from __future__ import annotations

from tl_core.services.errors import ServiceError


class RequisitionError(ServiceError):
    """Base of the module's expected failures."""


class RequisitionScopeError(RequisitionError):
    """Requisitions belong to a project scope."""


class RequisitionRuleError(RequisitionError):
    """A rule of the fields: dates, quantities, a code, an id that names no usable record."""


class RequisitionStateError(RequisitionError):
    """The requisition or work order is in a state that does not take the command (final ones
    take none)."""


class StaleVersionError(RequisitionError):
    """The record changed since the caller read it (``expected_version`` is not the current
    version)."""
