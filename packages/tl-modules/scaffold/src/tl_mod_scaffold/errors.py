"""The expected failures of the scaffold module. Each takes a fixed or composed message, never a
cell of the input and never an id the viewer could not read.

They subclass ``ServiceError``; ``tl_api.errors`` maps each to a status and a stable code (the
registry line is supervisor glue). A refusal of who may act is core's ``ForbiddenError``.
"""

from __future__ import annotations

from tl_core.services.errors import ServiceError


class ScaffoldError(ServiceError):
    """Base of the module's expected failures."""


class ScaffoldScopeError(ScaffoldError):
    """Scaffolds belong to a project scope."""


class ScaffoldRuleError(ScaffoldError):
    """A rule of the fields or of the request: a time in the future, no green tag, a request that
    does not allow a scaffold, a second scaffold on one request."""


class ScaffoldStateError(ScaffoldError):
    """The scaffold is in a state that does not take the command (a removed one takes none)."""


class DismantleRefused(ScaffoldError):
    """The dismantle check found a reason to keep the scaffold up; the text lists them."""


class StaleVersionError(ScaffoldError):
    """The record changed since the caller read it (``expected_version`` is not the current
    version)."""
