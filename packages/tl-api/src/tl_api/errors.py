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
from tl_core.derivation.registry import ExtractorLoadError
from tl_core.extypes import errors as ext
from tl_core.integration import errors as integ
from tl_core.ledger import ConcurrencyError
from tl_core.query import QuerySyntaxError
from tl_core.services import errors as svc
from tl_core.threads import errors as thr
from tl_core.webhooks import subscriptions as wh
from tl_core.workflow.engine import GuardResult
from tl_mod_correspondence import errors as corr
from tl_mod_cost import errors as cost
from tl_mod_documents import errors as doc
from tl_mod_documents.imports.apply import ImportRefusedError
from tl_mod_engineering import errors as eng
from tl_mod_schedule import errors as sched

#: What a client is told when an installed extractor cannot be loaded (detail: the server log).
EXTRACTOR_UNAVAILABLE = (
    "an extractor could not be loaded; the administrator can see why in the server log"
)


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
        s(svc.ReservedKeyError, "reserved_key", 422),
        s(svc.ReservedLinkSourceError, "reserved_link_source", 422),
        s(svc.ReservedIdentifierError, "reserved_identifier", 422),
        s(svc.RoleClaimError, "role_claim_refused", 422),
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
        # --- integration layer (P1-I7 WS-A) ----------------------------------------------------
        s(integ.InvalidIntegrationError, "invalid_integration", 422),
        s(integ.IntegrationNotFoundError, "integration_not_found", 404),
        s(integ.DuplicateIntegrationError, "duplicate_integration", 409),
        s(integ.IntegrationStateError, "integration_state", 409),
        s(integ.ActionAccessError, "action_access", 403),
        s(integ.CommandAccessError, "command_access", 403),
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
        s(svc.ProposalAccessError, "proposal_access", 403),
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
        s(auth.AuthBusyError, "auth_busy", 503),
        # --- engineering module (P1-I1): registry, tag classes, tags, imports ----------------
        s(eng.EngineeringError, "engineering_error", 422),
        s(eng.RegistryScopeError, "registry_scope", 422),
        s(eng.DuplicateStandardError, "duplicate_standard", 409),
        s(eng.StandardNotFoundError, "standard_not_found", 404),
        s(eng.UnknownCodeListError, "unknown_code_list", 404),
        s(eng.UnknownCodeError, "unknown_code", 422),
        s(eng.DuplicateCodeValueError, "duplicate_code_value", 409),
        s(eng.ListClosedError, "list_closed", 409),
        s(eng.CrosswalkRequiredError, "crosswalk_required", 422),
        s(eng.InvalidCrosswalkError, "invalid_crosswalk", 422),
        s(eng.InvalidSupersessionError, "invalid_supersession", 422),
        s(eng.AlreadyClosedError, "already_closed", 409),
        s(eng.InvalidPatternError, "invalid_pattern", 422),
        s(eng.DuplicateTagClassError, "duplicate_tag_class", 409),
        s(eng.TagClassNotFoundError, "tag_class_not_found", 404),
        s(eng.InvalidTagClassError, "invalid_tag_class", 422),
        s(eng.TagNotFoundError, "tag_not_found", 404),
        s(eng.TagSupersededError, "tag_superseded", 409),
        s(eng.InvalidTagNumberError, "invalid_tag_number", 422),
        s(eng.StandardsLoadError, "standards_load", 422),
        s(eng.ImportApplyError, "import_apply", 422),
        # --- documents module (P1-I2): documents, revisions, renditions, transmittals, reviews --
        s(doc.DocumentsError, "documents_error", 422),
        s(doc.ProjectScopeError, "project_scope", 422),
        s(doc.BackdatedError, "backdated", 422),
        s(doc.DocumentNotFoundError, "document_not_found", 404),
        s(doc.DocumentClosedError, "document_closed", 409),
        s(doc.InvalidDocumentNumberError, "invalid_document_number", 422),
        s(doc.InvalidDocumentTypeError, "invalid_document_type", 422),
        s(doc.UnknownSchemeError, "unknown_scheme", 422),
        s(doc.InvalidRevisionCodeError, "invalid_revision_code", 422),
        s(doc.RevisionNotFoundError, "revision_not_found", 404),
        s(doc.OpenRevisionError, "open_revision", 409),
        s(doc.RevisionStateError, "revision_state", 409),
        s(doc.RevisionSequenceError, "revision_sequence", 409),
        s(doc.InvalidIssueStatusError, "invalid_issue_status", 422),
        s(doc.NoRenditionError, "no_rendition", 409),
        s(doc.RenditionNotAllowedError, "rendition_not_allowed", 409),
        s(doc.FileNotAvailableError, "file_not_available", 422),
        s(doc.InvalidPinError, "invalid_pin", 422),
        s(doc.TransmittalNotFoundError, "transmittal_not_found", 404),
        s(doc.TransmittalStateError, "transmittal_state", 409),
        s(doc.InvalidTransmittalError, "invalid_transmittal", 422),
        s(doc.ReviewNotFoundError, "review_not_found", 404),
        s(doc.ReviewStateError, "review_state", 409),
        s(doc.InvalidReviewError, "invalid_review", 422),
        s(ImportRefusedError, "import_refused", 422),  # `tl doc import`; no route offers it yet
        s(doc.NotYourReviewError, "not_your_review", 403),
        s(doc.SchemaNotFoundError, "schema_not_found", 404),
        s(doc.InvalidDocumentSchemaError, "invalid_document_schema", 422),
        s(doc.DerivedNotFoundError, "derived_not_found", 404),
        s(doc.DerivedStateError, "derived_state", 409),
        s(doc.InvalidSourceError, "invalid_source", 422),
        s(doc.JobNotFoundError, "job_not_found", 404),
        s(doc.JobStateError, "job_state", 409),
        s(doc.DerivationNotConfiguredError, "derivation_unavailable", 503),
        s(doc.ValidationFailedError, "validation_failed", 422),
        s(doc.ValidationLimitError, "validation_limit", 422),
        s(doc.SchemaUnusableError, "schema_unusable", 422),
        s(ExtractorLoadError, "extractor_unavailable", 503),
        # --- correspondence module (P1-I5): items, threads, clocks, parties, clauses -----------
        s(corr.CorrespondenceError, "correspondence_error", 422),
        s(corr.CorrespondenceScopeError, "correspondence_scope", 422),
        s(corr.ItemNotFoundError, "correspondence_not_found", 404),
        s(corr.ItemStateError, "correspondence_state", 409),
        s(corr.InvalidItemError, "invalid_correspondence", 422),
        s(corr.ItemBackdatedError, "correspondence_backdated", 422),
        s(corr.UnknownDomainError, "unknown_domain", 422),
        s(corr.ThreadNotFoundError, "thread_not_found", 404),
        s(corr.ClockNotFoundError, "clock_not_found", 404),
        s(corr.ClockStateError, "clock_state", 409),
        s(corr.InvalidClockError, "invalid_clock", 422),
        s(corr.CalendarUnavailableError, "calendar_unavailable", 422),
        s(corr.PartyNotFoundError, "party_not_found", 404),
        s(corr.InvalidPartyError, "invalid_party", 422),
        s(corr.ClauseNotFoundError, "clause_not_found", 404),
        s(corr.InvalidClauseError, "invalid_clause", 422),
        s(corr.ClearanceError, "clearance", 422),
        s(corr.LetterRenderError, "letter_render", 422),
        s(corr.EvidenceDateError, "evidence_date", 422),
        s(corr.ExportClassError, "export_class", 422),
        s(corr.ExportTooLargeError, "export_too_large", 422),
        s(doc.PublishRefusedError, "publish_refused", 422),
        s(doc.CompensationRefusedError, "compensation_refused", 409),
        # --- record threads and dispatch (P1-I7 workstream B) ---------------------------------
        s(thr.ThreadError, "thread_error", 422),
        s(thr.ThreadsDisabledError, "threads_disabled", 403),
        s(thr.ThreadMessageNotFoundError, "thread_message_not_found", 404),
        s(thr.NotMessageAuthorError, "not_message_author", 403),
        s(thr.MessageRetractedError, "message_retracted", 409),
        s(thr.MessageNotEditableError, "message_not_editable", 409),
        s(thr.DispatchDisabledError, "dispatch_disabled", 403),
        s(thr.DispatchForbiddenError, "dispatch_forbidden", 403),
        s(thr.DispatchStaleError, "dispatch_stale", 409),
        s(thr.DispatchRefusedError, "dispatch_refused", 422),
        s(thr.DispatchSyntaxError, "dispatch_syntax", 422),
        # --- cost module (P1-I4): cost codes and period snapshots -------------------------------
        s(cost.CostError, "cost_error", 422),
        s(cost.CostScopeError, "cost_scope", 422),
        s(cost.InvalidCostSnapshotError, "invalid_cost_snapshot", 422),
        s(cost.CostCodeNotFoundError, "cost_code_not_found", 404),
        s(cost.CostImportRefusedError, "cost_import_refused", 422),
        s(cost.CostFileError, "cost_file", 422),
        # --- schedule module (P1-I4): schedules, XER snapshots, activity links ---------------
        s(sched.ScheduleError, "schedule_error", 422),
        s(sched.ScheduleScopeError, "schedule_scope", 422),
        s(sched.InvalidScheduleError, "invalid_schedule", 422),
        s(sched.ScheduleNotFoundError, "schedule_not_found", 404),
        s(sched.SnapshotNotFoundError, "snapshot_not_found", 404),
        s(sched.SnapshotStateError, "snapshot_state", 409),
        s(sched.SourceFileError, "source_file", 422),
        s(sched.DuplicateSnapshotError, "duplicate_snapshot", 409),
        s(sched.StaleSnapshotError, "stale_snapshot", 409),
        s(sched.ActivityNotFoundError, "activity_not_found", 404),
        s(sched.NoCurrentSnapshotError, "no_current_snapshot", 409),
        s(sched.ScheduleNotConfiguredError, "schedule_unavailable", 503),
        s(sched.TablesMismatchError, "tables_mismatch", 409),
        s(sched.TooManyLinksError, "too_many_links", 409),
        s(sched.TooManyOpenSnapshotsError, "too_many_open_snapshots", 409),
        s(sched.TooManyReferencesError, "too_many_references", 409),
        s(sched.FutureDataDateError, "future_data_date", 409),
        s(sched.TypedRowsMissingError, "typed_rows_missing", 409),
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
    "rate_limited": 429,  # too many failed sign-ins from one address (tl_api.ratelimit)
    "payload_too_large": 413,  # a body over the limit of /auth, /admin or /commands (tl_api.auth)
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
    message = str(exc) or spec.error
    if isinstance(exc, ExtractorLoadError):  # the server log has the detail, the client has this
        message = EXTRACTOR_UNAVAILABLE
    body = ErrorBody(error=spec.error, message=message)
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
    elif isinstance(exc, (eng.InvalidTagNumberError, doc.InvalidDocumentNumberError)):
        body.issues = list(exc.issues)  # one dict per problem: segment, rule, level, message
    elif isinstance(
        exc,
        (
            eng.StandardsLoadError,
            eng.ImportApplyError,
            doc.InvalidDocumentSchemaError,
            doc.PublishRefusedError,
            doc.CompensationRefusedError,
        ),
    ):
        body.issues = list(exc.problems)
    elif isinstance(exc, thr.DispatchRefusedError):
        body.issues = list(exc.problems)  # one {code, message} per problem of the plan
    elif isinstance(exc, cost.CostImportRefusedError):
        body.issues = list(exc.issues)
    elif isinstance(exc, cost.CostFileError):
        body.issues = [{"code": exc.code, "row": exc.row}]
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
        if spec.exc is eng.InvalidTagNumberError:
            return eng.InvalidTagNumberError(
                message, [dict(i) for i in body.get("issues") or [] if isinstance(i, dict)]
            )
        if spec.exc is doc.InvalidDocumentNumberError:
            return doc.InvalidDocumentNumberError(
                message, [dict(i) for i in body.get("issues") or [] if isinstance(i, dict)]
            )
        if spec.exc is eng.StandardsLoadError:
            return eng.StandardsLoadError(message, [str(i) for i in body.get("issues") or []])
        if spec.exc is eng.ImportApplyError:
            return eng.ImportApplyError(message, [str(i) for i in body.get("issues") or []])
        if spec.exc in (
            doc.InvalidDocumentSchemaError,
            doc.PublishRefusedError,
            doc.CompensationRefusedError,
        ):
            return spec.exc(message, [str(i) for i in body.get("issues") or []])
        if spec.exc is thr.DispatchRefusedError:
            return thr.DispatchRefusedError(
                message, [dict(i) for i in body.get("issues") or [] if isinstance(i, dict)]
            )
        if spec.exc is cost.CostImportRefusedError:
            return cost.CostImportRefusedError(message, [str(i) for i in body.get("issues") or []])
        if spec.exc is cost.CostFileError:
            first = next((i for i in body.get("issues") or [] if isinstance(i, dict)), {})
            row = first.get("row")
            return cost.CostFileError(
                str(first.get("code") or "cost_file"),
                message,
                row if isinstance(row, int) else None,
            )
        if spec.exc is auth.AccountLockedError:
            until = body.get("locked_until")
            return auth.AccountLockedError(message, None if until is None else str(until))
        return spec.exc(message)
    cls = ApiValidationError if code == "validation_error" else ApiError
    return cls(status, code or "unknown", message, body)
