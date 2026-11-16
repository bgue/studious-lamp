"""The expected failures of the QR module. Each takes a fixed message: never a code, a hash, a
count or an id the viewer could not read.

They subclass core error classes that ``tl_api.errors`` already maps (the first class on the MRO
with a row answers): no registry line is added. A refusal of who may act is core's
``ForbiddenError``.
"""

from __future__ import annotations

from tl_core.services.errors import InvalidScopeError, InvalidStateError, UnsupportedFieldError

MSG_UNKNOWN = "no record with that id"
MSG_BASE = "set api.public_base_url first"
MSG_CAP = "that record has as many live scan codes as it may have; revoke one first"
MSG_EXPIRY = "the expiry is in the past"
MSG_REVOKED = "that scan code is already revoked"
MSG_PROJECT = "a scan code is issued in a project"


class QrScopeError(InvalidScopeError):
    """A scan code is issued in a project scope."""


class QrRuleError(UnsupportedFieldError):
    """A rule of the fields or the settings: the public address, the cap, the expiry (the nearest
    mapped core class with a 422 row)."""


class QrStateError(InvalidStateError):
    """The scan code is in a state that does not take the command (already revoked)."""
