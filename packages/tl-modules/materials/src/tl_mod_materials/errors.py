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


class MtoPublishRefusedError(MaterialsError):
    """A derived document cannot be published as a take-off (kind, rows, work package)."""


class MtoLineNotFoundError(MaterialsError):
    """No take-off line with that key in the project."""


class MtoLineInUseError(MaterialsError):
    """The take-off line has a reservation or an issue, so it cannot be reassigned or taken back."""


class WorkPackageNotFoundError(MaterialsError):
    """No work package with that number in the project."""


class ReceiptNotFoundError(MaterialsError):
    """No receipt with that id in the project."""


class ReceiptStateError(MaterialsError):
    """The receipt is not in a state that takes the command (revise, inspect, decide, void)."""


class MtrRequiredError(MaterialsError):
    """A line is of a category that needs a material test report; none is attached."""


class CostCodeNotFoundError(MaterialsError):
    """No cost code with that id in the project."""


class MovementRuleError(MaterialsError):
    """A movement breaks a rule of its kind (a field it needs or may not carry, a lot or location
    it cannot use). The message names the movement by its index."""


class InsufficientStockError(MaterialsError):
    """The lot does not hold enough at the location (available, reserved or issued) for the
    movement. The message names the movement by its index."""
