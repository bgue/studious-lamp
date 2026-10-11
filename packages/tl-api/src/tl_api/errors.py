"""The error table: every expected failure, its HTTP status and its stable machine code (O4).

This is the one place that maps tl_core's exceptions to HTTP. The server turns an exception into
``{"error": <code>, "message": <text>, ...extras}`` and the HTTP client turns that body back into
the same exception class, so a remote caller handles ``RecordNotFoundError`` exactly as an embedded
one does. Adding a ``ServiceError`` subclass without a row here fails ``test_error_table.py``.

Statuses: 404 not found, 409 concurrency, state conflict or failed guard, 422 validation (the
request is well formed but cannot be applied), 400 for malformed input (query text, upload
tokens), and the file statuses suggested in the files plan (413, 415, 403, 410, 503).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, cast

from pydantic import BaseModel, ValidationError
from tl_core.auth import errors as auth
from tl_core.extypes import errors as ext
from tl_core.ledger import ConcurrencyError
from tl_core.query import QuerySyntaxError
from tl_core.services import errors as svc
from tl_core.webhooks import subscriptions as wh
from tl_core.workflow.engine import GuardResult


@dataclass(frozen=True)
class ErrorSpec:
    exc: type[Exception]
    error: str  # stable machine code; part of the API contract
    status: int


def _rows() -> tuple[ErrorSpec, ...]:
    s = ErrorSpec
    return (
        s(ConcurrencyError, "concurrency_conflict", 409),
        s(QuerySyntaxError, "query_syntax", 400),
        # --- records and psets ---------------------------------------------------------------
        s(svc.KeyRequiredError, "key_required", 422),
        s(svc.DuplicateKeyError, "duplicate_key", 409),
        s(svc.UnsupportedRecordTypeError, "unsupported_record_type", 422),
        s(svc.RecordNotFoundError, "record_not_found", 404),
        s(svc.RecordVoidedError, "record_voided", 409),
        s(svc.AlreadyVoidedError, "already_voided", 409),
        s(svc.NoChangesError, "no_changes", 422),
        s(svc.UnsupportedFieldError, "unsupported_field", 422),
        s(svc.UnknownPsetError, "unknown_pset", 422),
        s(svc.LayerError, "layer_error", 422),
        s(svc.PsetValidationError, "pset_validation", 422),
        s(svc.InvalidScopeError, "invalid_scope", 422),
        # --- links ---------------------------------------------------------------------------
        s(svc.LinkNotFoundError, "link_not_found", 404),
        s(svc.InvalidLinkTransitionError, "invalid_link_transition", 409),
        s(svc.DuplicateLinkError, "duplicate_link", 409),
        s(svc.SuggestionDeclinedError, "suggestion_declined", 409),
        s(svc.UnknownRelationError, "unknown_relation", 422),
        s(svc.SelfLinkError, "self_link", 422),
        s(svc.CrossScopeLinkError, "cross_scope_link", 422),
        # --- numbering -----------------------------------------------------------------------
        s(svc.NumberingError, "numbering_error", 422),
        s(svc.NoNumberingPatternError, "no_numbering_pattern", 422),
        s(svc.NumberingValueError, "numbering_value", 422),
        s(svc.GapFreeError, "gap_free", 422),
        s(svc.NotAvailableError, "not_available", 501),
        # --- workflow ------------------------------------------------------------------------
        s(svc.NoWorkflowError, "no_workflow", 422),
        s(svc.UnknownTransitionError, "unknown_transition", 422),
        s(svc.InvalidStateError, "invalid_state", 409),
        s(svc.GuardFailedError, "guard_failed", 409),
        # --- files ---------------------------------------------------------------------------
        s(svc.FileError, "file_error", 400),
        s(svc.UnknownSlotError, "unknown_slot", 422),
        s(svc.FileTypeNotAcceptedError, "file_type_not_accepted", 415),
        s(svc.FileTooLargeError, "file_too_large", 413),
        s(svc.UploadTokenError, "upload_token", 400),
        s(svc.UploadIncompleteError, "upload_incomplete", 400),
        s(svc.UploadVerificationError, "upload_verification", 400),
        s(svc.ContentRejectedError, "content_rejected", 422),
        s(svc.UnknownFileError, "file_not_found", 404),
        s(svc.FileQuarantinedError, "file_quarantined", 403),
        s(svc.FileRejectedError, "file_rejected", 410),
        s(svc.InvalidFileTransitionError, "invalid_file_transition", 409),
        s(svc.ObjectMissingError, "object_missing", 503),
        # --- transactions (P0-I5): nothing was written; the caller may retry ---------------
        s(svc.RetryableTransactionError, "retry_transaction", 503),
        s(svc.LockTimeoutError, "lock_timeout", 503),
        # --- webhook subscriptions (P0-I5) ---------------------------------------------------
        s(wh.SubscriptionNotFoundError, "subscription_not_found", 404),
        s(wh.InvalidSubscriptionError, "invalid_subscription", 422),
        s(wh.AlreadyInStateError, "already_in_state", 409),
        s(wh.SubscriptionNotActiveError, "subscription_not_active", 409),
        # --- activity feed (P0-I6) -----------------------------------------------------------
        s(svc.PostNotFoundError, "post_not_found", 404),
        s(svc.PostRetractedError, "post_retracted", 409),
        s(svc.ReactionsDisabledError, "reactions_disabled", 403),
        s(svc.NotPostAuthorError, "not_post_author", 403),
        # --- proposals (P0-I6 workstream B) --------------------------------------------------
        s(svc.ProposalNotFoundError, "proposal_not_found", 404),
        s(svc.ProposalNotPendingError, "proposal_not_pending", 409),
        s(svc.InvalidProposalError, "invalid_proposal", 422),
        s(svc.BudgetExceededError, "budget_exceeded", 429),
        s(svc.ProposalDeciderError, "proposal_decider", 403),
        # --- extension types (P0-I8 workstream B) ---------------------------------------------
        s(ext.UnknownTypeError, "type_not_found", 404),
        s(ext.TypeNotActiveError, "type_not_active", 409),
        s(ext.BodyRequiredError, "body_required", 422),
        s(ext.BodyNotAllowedError, "body_not_allowed", 422),
        s(ext.BodyValidationError, "body_invalid", 422),
        s(ext.BodyNotFoundError, "body_not_found", 404),
        s(ext.BodyQuarantinedError, "body_quarantined", 403),
        s(ext.BodyHashMismatchError, "body_hash_mismatch", 502),
        s(ext.BodyStoreUnavailableError, "body_store_unavailable", 503),
        # --- settings (P0-I8 workstream A) ---------------------------------------------------
        s(svc.SettingError, "setting_error", 422),
        s(svc.UnknownSettingError, "unknown_setting", 404),
        s(svc.InvalidSettingValueError, "invalid_setting_value", 422),
        s(svc.SettingScopeError, "setting_scope", 422),
        s(svc.SettingLockedError, "setting_locked", 409),
        s(svc.SettingOutOfBoundsError, "setting_out_of_bounds", 422),
        s(svc.ReasonRequiredError, "reason_required", 422),
        s(svc.RiskNotAcceptedError, "risk_not_accepted", 422),
        s(svc.SecretSettingUnavailableError, "secret_setting_unavailable", 422),
        s(svc.SettingNotLockableError, "setting_not_lockable", 422),
        s(svc.SettingChangeNotFoundError, "setting_change_not_found", 404),
        s(svc.SettingsDocumentError, "settings_document", 422),
        s(svc.SettingRevertNotLatestError, "setting_revert_not_latest", 409),
        # --- accounts and sign-in (P1-I0, ADR-0009) -----------------------------------------
        s(auth.InvalidCredentialsError, "invalid_credentials", 401),
        s(auth.AccountLockedError, "account_locked", 423),
        s(auth.AccountDisabledError, "account_disabled", 403),
        s(auth.ForbiddenError, "forbidden", 403),
        s(auth.LastAdminError, "last_admin", 409),
        s(auth.WeakPasswordError, "weak_password", 422),
        s(auth.UsernameTakenError, "username_taken", 409),
        s(auth.AccountNotFoundError, "account_not_found", 404),
        s(auth.AgentTokenNotFoundError, "agent_token_not_found", 404),
        s(auth.InvalidAccountError, "invalid_account", 422),
        s(auth.AccountStateError, "account_state", 409),
    )


ERROR_TABLE: tuple[ErrorSpec, ...] = _rows()
"""Every mapped exception class. ``ServiceError`` itself is deliberately absent: an unmapped
subclass is a bug (``test_error_table.py``), not a silent 500."""

#: Codes the API raises without a tl_core exception behind them.
HTTP_ERRORS: dict[str, int] = {
    "validation_error": 422,
    "invalid_argument": 422,
    "effective_time_forbidden": 400,
    "invalid_effective_time": 400,
    "unauthorized": 401,
    "agent_must_propose": 403,  # an agent token ran a record-changing command (tl_api.auth)
    "not_found": 404,
    "method_not_allowed": 405,
    "unavailable": 503,
    "internal_error": 500,
}

_BY_CLASS: dict[type[Exception], ErrorSpec] = {spec.exc: spec for spec in ERROR_TABLE}
_BY_CODE: dict[str, ErrorSpec] = {spec.error: spec for spec in ERROR_TABLE}


class ErrorBody(BaseModel):
    """The JSON body of every error response."""

    error: str
    message: str
    position: int | None = None  # query_syntax: 0-based character offset
    issues: list[dict[str, Any]] | list[str] | None = None  # validation: one entry per problem
    results: list[dict[str, Any]] | None = None  # guard_failed: every guard, passed or not
    locked_until: str | None = None  # account_locked: ISO-8601 UTC end of the lock


class ApiError(Exception):
    """An error body the table has no exception class for (HTTP-level errors, unknown codes)."""

    def __init__(
        self, status: int, error: str, message: str, body: dict[str, Any] | None = None
    ) -> None:
        super().__init__(message)
        self.status = status
        self.error = error
        self.message = message
        self.body: dict[str, Any] = body if body is not None else {}


class ApiValidationError(ApiError):
    """A 422 ``validation_error``: the request body or parameters were invalid."""


def spec_for(exc: BaseException) -> ErrorSpec | None:
    """The table row for ``exc``: the first class on its MRO that has one, else ``None``."""
    for klass in type(exc).__mro__:
        found = _BY_CLASS.get(cast("type[Exception]", klass))
        if found is not None:
            return found
    return None


def validation_issues(exc: ValidationError) -> list[dict[str, Any]]:
    return [{"loc": [str(p) for p in e["loc"]], "msg": e["msg"]} for e in exc.errors()]


def body_for(exc: BaseException) -> tuple[int, ErrorBody] | None:
    """``(status, body)`` for an expected failure, or ``None`` when ``exc`` is not one."""
    if isinstance(exc, ValidationError):
        issues = validation_issues(exc)
        message = "; ".join(f"{'.'.join(i['loc'])}: {i['msg']}" for i in issues)
        return 422, ErrorBody(error="validation_error", message=message, issues=issues)
    spec = spec_for(exc)
    if spec is None:
        return None
    body = ErrorBody(error=spec.error, message=str(exc) or spec.error)
    if isinstance(exc, QuerySyntaxError):
        body.position = exc.position
    elif isinstance(exc, svc.GuardFailedError):
        body.results = [
            r.model_dump(mode="json") if isinstance(r, BaseModel) else dict(r) for r in exc.results
        ]
    elif isinstance(
        exc, (svc.PsetValidationError, ext.BodyValidationError, auth.WeakPasswordError)
    ):
        body.issues = list(exc.issues)
    elif isinstance(exc, auth.AccountLockedError):
        body.locked_until = exc.locked_until
    return spec.status, body


def exception_for(status: int, body: dict[str, Any]) -> Exception:
    """Rebuild the exception an error response stands for (the HTTP client calls this).

    A code in the table gives its tl_core class with the original message; any other body gives
    an ``ApiError`` (``ApiValidationError`` for ``validation_error``).
    """
    code = str(body.get("error", ""))
    message = str(body.get("message", code or f"HTTP {status}"))
    spec = _BY_CODE.get(code)
    if spec is not None:
        if spec.exc is QuerySyntaxError:
            return QuerySyntaxError(message, int(body.get("position") or 0))
        if spec.exc is svc.GuardFailedError:
            return svc.GuardFailedError(
                message, [GuardResult(**r) for r in body.get("results") or []]
            )
        if spec.exc is svc.PsetValidationError:
            return svc.PsetValidationError(message, [str(i) for i in body.get("issues") or []])
        if spec.exc is ext.BodyValidationError:
            return ext.BodyValidationError(message, [str(i) for i in body.get("issues") or []])
        if spec.exc is auth.WeakPasswordError:
            return auth.WeakPasswordError(message, [str(i) for i in body.get("issues") or []])
        if spec.exc is auth.AccountLockedError:
            until = body.get("locked_until")
            return auth.AccountLockedError(message, None if until is None else str(until))
        return spec.exc(message)
    cls = ApiValidationError if code == "validation_error" else ApiError
    return cls(status, code or "unknown", message, body)
