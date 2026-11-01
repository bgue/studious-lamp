"""The expected failures of the awp module. Each takes a fixed message, never a cell of the input.

They subclass ``ServiceError``; ``tl_api.errors`` maps each to a status and a stable code (the
registry line is supervisor glue).
"""

from __future__ import annotations

from tl_core.services.errors import ServiceError


class AwpError(ServiceError):
    """Base of the module's expected failures."""


class AwpScopeError(AwpError):
    """The awp records belong to a project scope."""


class CodeNotFoundError(AwpError):
    """No record with that code in the project (or one the viewer may not read)."""


class DuplicateCodeError(AwpError):
    """The code is already used in the project."""


class WbsRuleError(AwpError):
    """A rule of the WBS shape: depth, node count, leaf-only, position, cycles."""


class AllocationError(AwpError):
    """An allocation list breaks a rule: size, range, repeats, sum, unknown or retired target."""


class RetiredError(AwpError):
    """The node or area is retired and takes no new allocation, change or retirement."""


class InUseError(AwpError):
    """A package that is not void still names the node or area."""


class PathRuleError(AwpError):
    """The path of construction breaks a rule: size, repeats, missing area, position."""


class StaleVersionError(AwpError):
    """The path changed since the caller read it (``expected_version`` is not the current)."""
