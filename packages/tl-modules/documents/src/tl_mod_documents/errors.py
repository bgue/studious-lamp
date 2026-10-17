"""The expected failures of the documents module (brief 5.1). Each takes a readable message.

They subclass ``ServiceError``, so every entry point that turns a service failure into an error line
or an HTTP status handles them; ``tl_api.errors`` maps each to a status and a stable code.
"""

from __future__ import annotations

from typing import Any

from tl_core.services.errors import ServiceError


class DocumentsError(ServiceError):
    """Base of the module's expected failures."""


class ProjectScopeError(DocumentsError):
    """Documents, revisions and transmittals belong to a project scope."""


class DocumentNotFoundError(DocumentsError):
    """No document with that id or number in the scope."""


class DocumentClosedError(DocumentsError):
    """The document is void or superseded and takes no more changes."""


class InvalidDocumentNumberError(DocumentsError):
    """The document number does not fit the numbering pattern. ``issues`` lists each problem."""

    def __init__(self, message: str, issues: list[dict[str, Any]] | None = None) -> None:
        super().__init__(message)
        self.issues: list[dict[str, Any]] = issues if issues is not None else []


class InvalidDocumentTypeError(DocumentsError):
    """The document type or discipline is not a usable value of its code list."""


class UnknownSchemeError(DocumentsError):
    """No revision scheme with that code, or the scheme file cannot be used."""


class InvalidRevisionCodeError(DocumentsError):
    """The revision code does not belong to the document's scheme, or is not after the last one."""


class RevisionNotFoundError(DocumentsError):
    """No revision with that id or code on the document."""


class OpenRevisionError(DocumentsError):
    """The document already has a revision that is being prepared or reviewed."""


class RevisionStateError(DocumentsError):
    """The revision is not in a state that allows the change."""


class RevisionSequenceError(DocumentsError):
    """A later revision of the document is already issued, so this one cannot be."""


class InvalidIssueStatusError(DocumentsError):
    """The issue status is not one of the scheme file's statuses."""


class NoRenditionError(DocumentsError):
    """A revision needs a PDF or native rendition before it can be issued."""


class RenditionNotAllowedError(DocumentsError):
    """The rendition cannot be added to the revision in its state."""


class FileNotAvailableError(DocumentsError):
    """The file is unknown, not on this revision, not in a rendition slot, or not yet scanned."""


class BackdatedError(DocumentsError):
    """An issue or answer date that is in the future, or before today without a reason."""


class InvalidPinError(DocumentsError):
    """A link's pin names no issued revision of the document."""


class TransmittalNotFoundError(DocumentsError):
    """No transmittal with that id or number in the scope."""


class TransmittalStateError(DocumentsError):
    """The transmittal is not in a state that allows the change."""


class InvalidTransmittalError(DocumentsError):
    """The transmittal as written cannot be used (a revision that is not issued, a repeated one)."""


class ReviewNotFoundError(DocumentsError):
    """No review cycle with that id on the revision."""


class ReviewStateError(DocumentsError):
    """The review cycle is not in a state that allows the change."""


class InvalidReviewError(DocumentsError):
    """The review as written cannot be used (a repeated or unknown reviewer, an unknown outcome)."""


class NotYourReviewError(DocumentsError):
    """Only the reviewer records their own answer; a document controller can record one for them."""


# --- the derivation pipeline (P1-I3, ADR-0014) ----------------------------------------------------


class SchemaNotFoundError(DocumentsError):
    """No document schema with that id, or code and version, in the scope."""


class InvalidDocumentSchemaError(DocumentsError):
    """The document schema as written cannot be used. ``problems`` lists every reason."""

    def __init__(self, message: str, problems: list[str] | None = None) -> None:
        super().__init__(message)
        self.problems: list[str] = problems if problems is not None else [message]


class DerivedNotFoundError(DocumentsError):
    """No derived document with that id or key in the scope."""


class DerivedStateError(DocumentsError):
    """The derived document is not in a state that allows the change."""


class InvalidSourceError(DocumentsError):
    """The file to read cannot be used: not on this revision, in the wrong slot, or unreadable."""


class JobNotFoundError(DocumentsError):
    """No processing job with that id in the scope."""


class JobStateError(DocumentsError):
    """The job is not in a state that allows the change (only a queued job is cancelled)."""


class DerivationNotConfiguredError(DocumentsError):
    """This process has no file service for derived data (it was set up without one)."""


class PublishRefusedError(DocumentsError):
    """The derived document cannot be published as it stands. ``problems`` lists every reason."""

    def __init__(self, message: str, problems: list[str] | None = None) -> None:
        super().__init__(message)
        self.problems: list[str] = problems if problems is not None else [message]


class CompensationRefusedError(DocumentsError):
    """The publication cannot be rolled back as it stands. ``problems`` lists every reason."""

    def __init__(self, message: str, problems: list[str] | None = None) -> None:
        super().__init__(message)
        self.problems: list[str] = problems if problems is not None else [message]


class ValidationFailedError(DocumentsError):
    """Validation could not finish: ``validation_limit`` (time or memory) or ``schema_unusable``.

    The text is fixed: no trace, no path, nothing from the schema or the rows (FANOUT D10).
    """

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
