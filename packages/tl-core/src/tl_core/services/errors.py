"""Expected, user-correctable command failures (brief 5.1). Each takes a human-readable message."""

from typing import Any


class ServiceError(Exception):
    """Base class for expected, user-correctable command failures."""


class KeyRequiredError(ServiceError): ...  # CreateRecord without a key


class DuplicateKeyError(ServiceError): ...  # (scope, key) already exists, voided or not


class UnsupportedRecordTypeError(ServiceError): ...  # record_type other than "core.Record"


class RecordNotFoundError(ServiceError): ...  # stream_id unknown, or it belongs to another scope


class RecordVoidedError(ServiceError): ...  # update of a voided record


class AlreadyVoidedError(ServiceError): ...  # void of a voided record


class NoChangesError(ServiceError): ...  # update where nothing differs


class UnsupportedFieldError(ServiceError): ...  # update of a field outside title/description/psets


class UnknownPsetError(
    ServiceError
): ...  # pset (or record type) not in the scope's effective schema


class LayerError(
    ServiceError
): ...  # key or pset does not belong to the requested layer, or the layer is not writable


class PsetValidationError(ServiceError):
    """Values break a structural rule (type, unknown key, null). ``issues`` lists each one."""

    def __init__(self, message: str, issues: list[str] | None = None) -> None:
        super().__init__(message)
        self.issues: list[str] = issues if issues is not None else []


class InvalidScopeError(ServiceError): ...  # scope is neither "company" nor "project:<id>"


# --- links (P0-I3) -----------------------------------------------------------------------------


class LinkNotFoundError(ServiceError): ...  # link_id unknown, or it belongs to another scope


class InvalidLinkTransitionError(ServiceError): ...  # the link's status does not allow this event


class DuplicateLinkError(ServiceError): ...  # a live link with the same ends and relation exists


class SuggestionDeclinedError(ServiceError): ...  # a person declined this suggestion before


class UnknownRelationError(ServiceError): ...  # relation code not in the vocabulary (or an inverse)


class SelfLinkError(ServiceError): ...  # a record cannot be linked to itself


class CrossScopeLinkError(ServiceError): ...  # target is in another project (brief 3: company only)


# --- numbering (P0-I3) -------------------------------------------------------------------------


class NumberingError(ServiceError): ...  # base class for numbering failures


class NoNumberingPatternError(KeyRequiredError): ...  # key omitted and no pattern applies


class NumberingValueError(NumberingError): ...  # a pattern segment has no usable value


class GapFreeError(NumberingError): ...  # standalone allocation from a gap-free pattern


class NotAvailableError(NumberingError): ...  # a stubbed capability (reserved ranges)


# --- workflow (P0-I3) --------------------------------------------------------------------------


class NoWorkflowError(ServiceError): ...  # no workflow definition applies to the record


class UnknownTransitionError(ServiceError): ...  # transition name unknown, or not from this state


class InvalidStateError(ServiceError): ...  # the record's status is not a state of its workflow


class GuardFailedError(ServiceError):
    """One or more guards of a transition failed. ``results`` lists every guard, passed or not."""

    def __init__(self, message: str, results: list[Any] | None = None) -> None:
        super().__init__(message)
        self.results: list[Any] = results if results is not None else []
