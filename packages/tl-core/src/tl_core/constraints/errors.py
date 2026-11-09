"""The expected failures of the core constraints (ADR-0024). Fixed messages, never a cell of input.

They subclass ``ServiceError``; ``tl_api.errors`` maps each to a status and a stable code.
"""

from __future__ import annotations

from tl_core.services.errors import ServiceError


class ConstraintError(ServiceError):
    """Base of the constraint failures."""


class ConstraintRuleError(ConstraintError):
    """A rule of a constraint's fields: owner, category, dates, target, check name and hash."""


class ConstraintSourceError(ConstraintError):
    """The caller may not raise or clear a constraint of that source (a person raises ``manual``;
    a module clears only what is not ``manual``)."""


class ConstraintStateError(ConstraintError):
    """The constraint is in a state that does not take the command."""


class PhaseNotGatedError(ConstraintError):
    """A blocking constraint names a phase that no guard of the subject's workflow names."""


#: The refusal of a person's clear of a check-raised constraint without the waive word (fixed).
MSG_WAIVE_WORD = "clearing a check-raised constraint needs the core.constraint.waive access word"
