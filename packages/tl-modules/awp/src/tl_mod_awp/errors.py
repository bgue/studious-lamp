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
    """The path or the package changed since the caller read it (``expected_version`` is not the
    current version)."""


class UnknownListCodeError(AwpError):
    """A code is not a usable value of the code list it must come from (reason, discipline,
    commodity, unit)."""


class CwpRuleError(AwpError):
    """A rule of a package's fields: dates, budget, quantities, contractor, a missing area."""


class CwpStateError(AwpError):
    """The package is in a state that does not take the command (frozen from Release, closed,
    void, not yet in development)."""


class ReleaseRefusedError(AwpError):
    """The package does not meet the preconditions of a release."""


class PackageRuleError(AwpError):
    """A rule of an owner package record: type, number, dates."""


class IwpRuleError(AwpError):
    """A rule of an IWP's fields: dates, hours, crew text, foreman, a group of a split."""


class IwpStateError(AwpError):
    """The IWP is in a state that does not take the command (frozen from Ready, terminal)."""


class ScopeRuleError(AwpError):
    """A rule of an IWP's scope: a repeat, a missing member, an unusable record, a size bound."""


class ScopeTakenError(AwpError):
    """A scope item already belongs to another IWP that is not finished."""
