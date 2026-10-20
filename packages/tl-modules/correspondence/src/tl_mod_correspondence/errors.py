"""The expected failures of the correspondence module (brief 5.1). Each takes a readable message.

They subclass ``ServiceError``, so every entry point that turns a service failure into an error line
or an HTTP status handles them; ``tl_api.errors`` maps each to a status and a stable code.
A record the viewer may not read answers as ``RecordNotFoundError`` of the core (ADR-0016), never
with an error of this module that would tell a hidden item from a missing one.
"""

from __future__ import annotations

from tl_core.services.errors import ServiceError


class CorrespondenceError(ServiceError):
    """Base of the module's expected failures."""


class CorrespondenceScopeError(CorrespondenceError):
    """Correspondence belongs to a project scope."""


class ItemNotFoundError(CorrespondenceError):
    """No correspondence item with that id or number in the scope."""


class ItemStateError(CorrespondenceError):
    """The item is not in a state that allows the change."""


class InvalidItemError(CorrespondenceError):
    """The values of an item cannot be used (a direction, a date, a recipient, a reference)."""


class ItemBackdatedError(CorrespondenceError):
    """A date is in the future, or before today without the reason the record needs."""


class UnknownDomainError(CorrespondenceError):
    """No domain (or no subtype of it) with that code applies in the scope."""


class ThreadNotFoundError(CorrespondenceError):
    """No thread with that id or number in the scope."""


class ClockNotFoundError(CorrespondenceError):
    """No response clock with that id in the scope."""


class ClockStateError(CorrespondenceError):
    """The clock is not in a state that allows the change (for example pausing a closed clock)."""


class InvalidClockError(CorrespondenceError):
    """The parameters of a clock cannot be used (a length, a type, a threshold, a date)."""


class CalendarUnavailableError(CorrespondenceError):
    """The calendar is unknown, or the count would leave the range it covers (fail closed)."""


class PartyNotFoundError(CorrespondenceError):
    """No party with that id or code in the scope."""


class InvalidPartyError(CorrespondenceError):
    """The values of a party or a contact cannot be used."""


class ClauseNotFoundError(CorrespondenceError):
    """No contract clause with that id or number in the scope."""


class InvalidClauseError(CorrespondenceError):
    """The values of a contract clause cannot be used."""


class ClearanceError(CorrespondenceError):
    """A clearance cannot be granted or withdrawn (the item is not privileged, or a repeat)."""


class LetterRenderError(CorrespondenceError):
    """The letter cannot be filled or rendered from the item and its template."""
