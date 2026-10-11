"""Expected failures of the extension type registry (P0-I8 workstream B; brief 31).

Each is a ``ServiceError``, so the API maps it to a stable code (``tl_api.errors``) and the HTTP
client turns it back into the same class.
"""

from __future__ import annotations

from tl_core.services.errors import ServiceError


class UnknownTypeError(ServiceError):
    """No registration of that type exists (or the type ref is malformed)."""


class TypeNotActiveError(ServiceError):
    """The type is registered but takes no new instances: deprecated, or its package is gone."""


class BodyRequiredError(ServiceError):
    """An object-backed type needs a body; create it with ``create_extension_record``."""


class BodyNotAllowedError(ServiceError):
    """A body for a managed type, or a direct write to an object-backed record's index fields."""


class BodyValidationError(ServiceError):
    """A body does not validate against its type. ``issues`` lists each problem."""

    def __init__(self, message: str, issues: list[str] | None = None) -> None:
        super().__init__(message)
        self.issues: list[str] = issues if issues is not None else []


class BodyNotFoundError(ServiceError):
    """The record is not object-backed, or has no stored body yet."""


class BodyQuarantinedError(ServiceError):
    """The stored body failed verification earlier; reads wait for a new body or a recheck."""


class BodyStoreUnavailableError(ServiceError):
    """No object store is configured, so record bodies cannot be read or stored."""


class BodyHashMismatchError(ServiceError):
    """The stored object does not match the hash the ledger recorded, or is missing (brief 31.4).

    ``actual`` is the hash of the bytes found, or ``None`` when the object is missing.
    """

    def __init__(
        self,
        message: str,
        *,
        record_id: str = "",
        uri: str = "",
        expected: str = "",
        actual: str | None = None,
    ) -> None:
        super().__init__(message)
        self.record_id = record_id
        self.uri = uri
        self.expected = expected
        self.actual = actual
