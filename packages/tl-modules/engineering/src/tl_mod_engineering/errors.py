"""The expected failures of the engineering module (brief 5.1). Each takes a readable message.

They subclass ``ServiceError``, so every entry point that turns a service failure into an error line
or an HTTP status handles them; ``tl_api.errors`` maps each to a status and a stable code.
"""

from __future__ import annotations

from typing import Any

from tl_core.services.errors import ServiceError


class EngineeringError(ServiceError):
    """Base of the module's expected failures."""


class RegistryScopeError(EngineeringError):
    """A registry entry or tag class must live in ``company`` scope; a tag in a project scope."""


class DuplicateStandardError(EngineeringError):
    """The scope already holds this kind, code and edition."""


class StandardNotFoundError(EngineeringError):
    """No registry entry with that id (or code) in the scope."""


class UnknownCodeListError(EngineeringError):
    """No active code list of that name."""


class UnknownCodeError(EngineeringError):
    """The list has no such value, or the value cannot be used (retired, outside its dates)."""


class DuplicateCodeValueError(EngineeringError):
    """The scope already defines this value of this list."""


class ListClosedError(EngineeringError):
    """A project may not add values to a closed list."""


class CrosswalkRequiredError(EngineeringError):
    """A project value of an extensible list must map to a company value."""


class InvalidCrosswalkError(EngineeringError):
    """The crosswalk names no active company value of the list."""


class AlreadyClosedError(EngineeringError):
    """The entry is already superseded or retired."""


class InvalidPatternError(EngineeringError):
    """A numbering pattern definition cannot be used."""


class DuplicateTagClassError(EngineeringError):
    """The scope already holds an active class with this code."""


class TagClassNotFoundError(EngineeringError):
    """No tag class with that id or code."""


class InvalidTagClassError(EngineeringError):
    """A tag class definition or change cannot be used."""


class TagNotFoundError(EngineeringError):
    """No tag with that id or number in the scope."""


class TagSupersededError(EngineeringError):
    """The tag has been replaced; it takes no more changes."""


class InvalidTagNumberError(EngineeringError):
    """The tag number does not fit the numbering pattern. ``issues`` lists each problem."""

    def __init__(self, message: str, issues: list[dict[str, Any]] | None = None) -> None:
        super().__init__(message)
        self.issues: list[dict[str, Any]] = issues if issues is not None else []
