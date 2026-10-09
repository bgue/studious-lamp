"""Expected, user-correctable command failures (brief 5.1). Each takes a human-readable message."""


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
