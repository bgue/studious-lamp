"""The expected failures of the materials module. Each takes a fixed, readable message.

They subclass ``ServiceError``; ``tl_api.errors`` maps each to a status and a stable code. A message
is fixed words plus a record code or a field name; it never repeats a cell of a file.
"""

from __future__ import annotations

from tl_core.services.errors import ServiceError


class MaterialsError(ServiceError):
    """Base of the module's expected failures."""


class MaterialsScopeError(MaterialsError):
    """The command was sent for the wrong scope (company for the library, a project otherwise)."""


class InvalidQuantityError(MaterialsError):
    """A quantity is not ASCII digits, is zero, has over 3 decimals or is over the bound."""


class InvalidValueError(MaterialsError):
    """A field holds a value its list or shape does not allow; the message names the field."""


class ItemNotFoundError(MaterialsError):
    """No item of the library, or no project item, with that code."""


class ItemRetiredError(MaterialsError):
    """The library item is retired; it cannot be adopted or ordered."""


class ItemInUseError(MaterialsError):
    """The item is used by a project item, so its unit cannot change."""


class ItemAlreadyAdoptedError(MaterialsError):
    """The project already holds a copy of the item."""


class NoChangesError(MaterialsError):
    """The command changes nothing."""


class LocationNotFoundError(MaterialsError):
    """No location with that code in the project."""


class LocationTreeError(MaterialsError):
    """The location tree rule is broken (root, parent, depth, kind, retire)."""


class PoLineNotFoundError(MaterialsError):
    """No PO line with that key in the project."""


class DuplicatePoLineError(MaterialsError):
    """The PO line is already mirrored in the project."""


class LotNotFoundError(MaterialsError):
    """No stock lot with that key in the project."""
