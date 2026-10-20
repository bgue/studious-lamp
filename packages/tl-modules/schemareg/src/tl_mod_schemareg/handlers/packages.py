"""The commands of a package's life: draft, revise, analyse, submit, review, publish, retire.

Who may run what (FANOUT D2, enforced by the entry points through ``commands.API_COMMANDS``):
drafting, revising, analysing and submitting are any signed-in person and only the actor that
drafted the package; sending it back, approving, publishing, deprecating and retiring are the
administrator's. The approver is never the author or the submitter.

The gates (FANOUT D4): ``SubmitSchemaPackage`` needs reports made for the content as it is now and
refuses ``breaking`` and ``forbidden`` changes and lint errors; ``PublishSchemaPackage`` needs an
Approved package, re-checks that it still composes and that the version it was compared with is
still the one below it, and appends the core event ``SchemaPackage.Published``. A package that is
published is immutable: its content never changes again.
"""

from __future__ import annotations

from pydantic import ConfigDict, Field
from tl_core.ledger import NewEvent
from tl_core.services.commands import Command, CommandResult
from tl_core.services.records import create_module_record
from tl_core.text import clean_optional_text
from tl_core.uow import UnitOfWork
from tl_schema.classify import ClassificationReport
from tl_schema.compile import SchemaCompileError
from tl_schema.packages import PackageDoc
from tl_schema.registry import PackageError

from tl_mod_schemareg import analysis, registry
from tl_mod_schemareg.common import (
    append,
    bump,
    canonical,
    correlated,
    scoped,
    sha256_text,
    transition,
)
from tl_mod_schemareg.errors import (
    AdoptionError,
    DuplicateSchemaPackageError,
    InvalidSchemaPackageError,
    NotTheAuthorError,
    SchemaPackageNotFoundError,
    SchemaPackageStateError,
    SelfReviewError,
    StaleAnalysisError,
)
from tl_mod_schemareg.limits import MAX_CHANGELOG, MAX_COMMENT, MAX_REASON, MAX_REPORT_BYTES
from tl_mod_schemareg.names import (
    ADOPTION,
    ADOPTION_PINNED,
    APPROVED,
    DEPRECATED,
    DRAFT,
    IN_REVIEW,
    PACKAGE_ANALYSED,
    PACKAGE_APPROVED,
    PACKAGE_CHANGES_REQUESTED,
    PACKAGE_DEPRECATED,
    PACKAGE_DRAFTED,
    PACKAGE_PUBLISHED,
    PACKAGE_RETIRED,
    PACKAGE_REVISED,
    PACKAGE_SUBMITTED,
    PUBLISHED,
    SCHEMA_PACKAGE,
)


class DraftSchemaPackage(Command):
    """Draft a package version from its YAML. The scope is the package's own."""

    model_config = ConfigDict(extra="forbid")

    content: str = Field(min_length=1)
    changelog: str | None = Field(default=None, max_length=MAX_CHANGELOG)


class ReviseSchemaPackage(Command):
    """Replace the content of a draft (its name, version, kind and project stay)."""

    model_config = ConfigDict(extra="forbid")

    package_id: str
    content: str = Field(min_length=1)
    changelog: str | None = Field(default=None, max_length=MAX_CHANGELOG)


class AnalyseSchemaPackage(Command):
    """Make the classification and impact reports of a draft."""

    model_config = ConfigDict(extra="forbid")

    package_id: str


class SubmitSchemaPackage(Command):
    """Send an analysed draft to review."""

    model_config = ConfigDict(extra="forbid")

    package_id: str


class RequestSchemaChanges(Command):
    """Send a package in review back to its author."""

    model_config = ConfigDict(extra="forbid")

    package_id: str
    reason: str = Field(min_length=1, max_length=MAX_REASON)


class ApproveSchemaPackage(Command):
    """Approve a package in review."""

    model_config = ConfigDict(extra="forbid")

    package_id: str
    comment: str | None = Field(default=None, max_length=MAX_COMMENT)


class PublishSchemaPackage(Command):
    """Publish an approved package: the version becomes adoptable (and, for a project's own
    package, comes into force). With ``auto_adopt`` the projects that pin the version below move to
    this one when the change is purely additive."""

    model_config = ConfigDict(extra="forbid")

    package_id: str
    auto_adopt: bool = False


class DeprecateSchemaPackage(Command):
    """Stop new adoptions of a published version."""

    model_config = ConfigDict(extra="forbid")

    package_id: str
    reason: str = Field(min_length=1, max_length=MAX_REASON)
    replacement: str | None = Field(default=None, max_length=200)


class RetireSchemaPackage(Command):
    """Take a deprecated version out of every effective schema."""

    model_config = ConfigDict(extra="forbid")

    package_id: str
    reason: str = Field(min_length=1, max_length=MAX_REASON)


def load(uow: UnitOfWork, package_id: str) -> registry.PackageRow:
    """The package, or ``SchemaPackageNotFoundError``."""
    row = registry.get_package(uow.conn(), package_id)
    if row is None:
        raise SchemaPackageNotFoundError(f"no schema package {package_id!r}")
    return row


def _require_state(row: registry.PackageRow, *states: str) -> None:
    if row.state not in states:
        raise SchemaPackageStateError(
            f"{row.key} is {row.state}; this needs it to be {' or '.join(states)}"
        )


def _require_author(row: registry.PackageRow, cmd: Command) -> None:
    if cmd.actor != row.drafted_by:
        raise NotTheAuthorError(f"{row.key} was drafted by another actor; only they work on it")


def _require_other_than_authors(row: registry.PackageRow, cmd: Command) -> None:
    if cmd.actor in (row.drafted_by, row.submitted_by):
        raise SelfReviewError(f"{cmd.actor} wrote or submitted {row.key} and cannot approve it")


def _current_analysis(row: registry.PackageRow) -> ClassificationReport:
    """The stored classification, when the reports were made for this very content."""
    if (
        row.analysed_sha256 is None
        or row.analysed_sha256 != row.content_sha256
        or row.classification is None
        or row.impact_sha256 is None
    ):
        raise StaleAnalysisError(
            f"{row.key} has no classification and impact reports for its current content; "
            "analyse it first"
        )
    return ClassificationReport.model_validate(row.classification)


def handle_draft_schema_package(uow: UnitOfWork, cmd: DraftSchemaPackage) -> CommandResult:
    """Create the draft; raises ``InvalidSchemaPackageError`` or ``DuplicateSchemaPackageError``."""
    cmd = correlated(cmd)
    doc = analysis.parse_content(cmd.content)
    held = analysis.provider()
    if held.registry().origin(doc.package, doc.version) is not None:
        raise DuplicateSchemaPackageError(f"{doc.key()} is already in force in this registry")
    if registry.find_package(uow.conn(), doc.package, doc.version) is not None:
        raise DuplicateSchemaPackageError(f"{doc.key()} is already drafted")
    scoped_cmd = scoped(cmd, analysis.scope_of(doc))
    return create_module_record(
        uow,
        scoped_cmd,
        record_type=SCHEMA_PACKAGE,
        title=doc.key(),
        key=doc.key(),
        composed_key=True,
        description=(doc.title or doc.description)[:500],
        extra_events=[
            NewEvent(
                event_type=PACKAGE_DRAFTED,
                payload={
                    "package": doc.package,
                    "version": doc.version,
                    "kind": doc.kind,
                    "project": doc.project,
                    "package_title": doc.title,
                    "content": cmd.content,
                    "content_sha256": sha256_text(cmd.content),
                    "changelog": clean_optional_text(cmd.changelog),
                    "drafted_by": cmd.actor,
                },
            )
        ],
    )


def handle_revise_schema_package(uow: UnitOfWork, cmd: ReviseSchemaPackage) -> CommandResult:
    """Replace a draft's content. The earlier reports no longer hold."""
    cmd = correlated(cmd)
    row = load(uow, cmd.package_id)
    _require_state(row, DRAFT)
    _require_author(row, cmd)
    doc = analysis.parse_content(cmd.content)
    if (doc.package, doc.version, doc.kind, doc.project) != (
        row.package,
        row.version,
        row.kind,
        row.project,
    ):
        raise InvalidSchemaPackageError(
            f"the name, version, kind and project of {row.key} cannot change; "
            "draft another version instead"
        )
    cmd = scoped(cmd, row.scope)
    done = append(
        uow,
        cmd,
        row.id,
        SCHEMA_PACKAGE,
        [
            NewEvent(
                event_type=PACKAGE_REVISED,
                payload={
                    "content": cmd.content,
                    "content_sha256": sha256_text(cmd.content),
                    "package_title": doc.title,
                    "changelog": clean_optional_text(cmd.changelog),
                },
            )
        ],
    )
    return CommandResult(
        stream_id=row.id, key=row.key, version=done.new_version, events=done.events
    )


def handle_analyse_schema_package(uow: UnitOfWork, cmd: AnalyseSchemaPackage) -> CommandResult:
    """Classify the change and assess its impact, for the content as it is now."""
    cmd = correlated(cmd)
    row = load(uow, cmd.package_id)
    _require_state(row, DRAFT)
    _require_author(row, cmd)
    doc = analysis.parse_content(row.content)
    try:
        made = analysis.analyse(uow.conn(), doc)
    except ValueError as exc:  # a version that is not higher than the one below it
        raise InvalidSchemaPackageError(str(exc)) from exc
    classification = made.classification.model_dump(mode="json")
    impact = made.impact.model_dump(mode="json")
    if len(canonical(classification)) + len(canonical(impact)) > MAX_REPORT_BYTES:
        raise InvalidSchemaPackageError("the reports are too large to store; split the change")
    cmd = scoped(cmd, row.scope)
    done = append(
        uow,
        cmd,
        row.id,
        SCHEMA_PACKAGE,
        [
            NewEvent(
                event_type=PACKAGE_ANALYSED,
                payload={
                    "base_ref": made.base_ref,
                    "classification": classification,
                    "classification_digest": made.classification.digest,
                    "worst_class": made.classification.worst,
                    "impact": impact,
                    "impact_sha256": made.impact.digest,
                    "content_sha256": row.content_sha256,
                },
            )
        ],
    )
    return CommandResult(
        stream_id=row.id, key=row.key, version=done.new_version, events=done.events
    )


def handle_submit_schema_package(uow: UnitOfWork, cmd: SubmitSchemaPackage) -> CommandResult:
    """Send the draft to review. Raises ``StaleAnalysisError`` and ``InvalidSchemaPackageError``."""
    cmd = correlated(cmd)
    row = load(uow, cmd.package_id)
    _require_state(row, DRAFT)
    _require_author(row, cmd)
    report = _current_analysis(row)
    if report.blocks_submit:
        blocking = [c for c in report.changes if c.cls in ("breaking", "forbidden")]
        raise InvalidSchemaPackageError(
            f"{row.key} makes changes that are not allowed in place: "
            + "; ".join(f"{c.path}: {c.detail}" for c in blocking[:5])
        )
    problems = analysis.lint_errors(analysis.parse_content(row.content))
    if problems:
        raise InvalidSchemaPackageError(
            f"{row.key} has lint errors: "
            + "; ".join(f"{i.rule} {i.path}: {i.message}" for i in problems[:5])
        )
    cmd = scoped(cmd, row.scope)
    moved = transition(uow, cmd, row.id, "submit")
    done = append(
        uow,
        cmd,
        row.id,
        SCHEMA_PACKAGE,
        [
            NewEvent(
                event_type=PACKAGE_SUBMITTED,
                payload={"submitted_by": cmd.actor, "classification_digest": report.digest},
            )
        ],
    )
    return CommandResult(
        stream_id=row.id,
        key=row.key,
        version=done.new_version,
        events=[*moved.events, *done.events],
    )


def handle_request_schema_changes(uow: UnitOfWork, cmd: RequestSchemaChanges) -> CommandResult:
    """Send a package in review back to Draft."""
    cmd = correlated(cmd)
    row = load(uow, cmd.package_id)
    _require_state(row, IN_REVIEW)
    cmd = scoped(cmd, row.scope)
    moved = transition(uow, cmd, row.id, "request_changes", reason=cmd.reason)
    done = append(
        uow,
        cmd,
        row.id,
        SCHEMA_PACKAGE,
        [NewEvent(event_type=PACKAGE_CHANGES_REQUESTED, payload={"reason": cmd.reason})],
    )
    return CommandResult(
        stream_id=row.id,
        key=row.key,
        version=done.new_version,
        events=[*moved.events, *done.events],
    )


def handle_approve_schema_package(uow: UnitOfWork, cmd: ApproveSchemaPackage) -> CommandResult:
    """Approve a package in review. The author and the submitter cannot."""
    cmd = correlated(cmd)
    row = load(uow, cmd.package_id)
    _require_state(row, IN_REVIEW)
    _require_other_than_authors(row, cmd)
    report = _current_analysis(row)
    cmd = scoped(cmd, row.scope)
    moved = transition(uow, cmd, row.id, "approve")
    done = append(
        uow,
        cmd,
        row.id,
        SCHEMA_PACKAGE,
        [
            NewEvent(
                event_type=PACKAGE_APPROVED,
                payload={
                    "approver": cmd.actor,
                    "comment": clean_optional_text(cmd.comment),
                    "classification_digest": report.digest,
                },
            )
        ],
    )
    return CommandResult(
        stream_id=row.id,
        key=row.key,
        version=done.new_version,
        events=[*moved.events, *done.events],
    )


def handle_publish_schema_package(uow: UnitOfWork, cmd: PublishSchemaPackage) -> CommandResult:
    """Publish an approved package. Raises the errors of the gates listed in the module text."""
    cmd = correlated(cmd)
    row = load(uow, cmd.package_id)
    _require_state(row, APPROVED)
    report = _current_analysis(row)
    if row.approved_digest != report.digest:
        raise StaleAnalysisError(f"{row.key} was approved for another classification; review again")
    doc = analysis.parse_content(row.content)
    _before, _after, _scope = analysis.trial_schemas(doc)  # still composes? (raises if not)
    held = analysis.provider()
    base = analysis.base_of(held.registry(), doc)
    if (base.key() if base is not None else None) != row.base_ref:
        raise StaleAnalysisError(
            f"a version below {row.key} was published after it was analysed "
            f"(compared with {row.base_ref}, now {base.key() if base else None}); "
            "send it back and analyse it again"
        )
    cmd = scoped(cmd, row.scope)
    moved = transition(uow, cmd, row.id, "publish")
    pins = (
        _adoptable(uow, row, doc, row.base_ref)
        if cmd.auto_adopt and row.kind == "company" and report.auto_adoptable
        else []
    )
    published = append(
        uow,
        cmd,
        row.id,
        SCHEMA_PACKAGE,
        [
            NewEvent(
                event_type=PACKAGE_PUBLISHED,
                payload={
                    "package": row.package,
                    "version": row.version,
                    "record_id": row.id,
                    "kind": row.kind,
                    "worst_class": report.worst,
                    "content_sha256": row.content_sha256,
                    "auto_adopted": sorted(p.project for p in pins),
                },
            )
        ],
    )
    events = [*moved.events, *published.events]
    for pin in pins:
        events.extend(
            append(
                uow,
                scoped(cmd, pin.scope),
                pin.id,
                ADOPTION,
                [
                    NewEvent(
                        event_type=ADOPTION_PINNED,
                        payload={
                            "project": pin.project,
                            "package": row.package,
                            "version": row.version,
                            "previous_version": pin.version,
                            "worst_class": "additive",
                            "impact_sha256": None,
                            "adopted_by": cmd.actor,
                            "auto": True,
                        },
                    )
                ],
            ).events
        )
    bump()
    return CommandResult(
        stream_id=row.id, key=row.key, version=published.new_version, events=events
    )


def _adoptable(
    uow: UnitOfWork, row: registry.PackageRow, doc: PackageDoc, base_key: str | None
) -> list[registry.AdoptionRow]:
    """Pins of the version below that can move to this one: the schema still composes for them."""
    if base_key is None:
        return []
    held = analysis.provider()
    found: list[registry.AdoptionRow] = []
    for pin in registry.list_adoptions(uow.conn(), package=row.package):
        if f"{pin.package}@{pin.version}" != base_key:
            continue
        pins = {**held.pins_of(pin.scope), row.package: row.version}
        try:
            held.trial(pin.scope, [doc], pins=pins)
        except (PackageError, SchemaCompileError):
            continue  # a project it does not fit keeps its pin
        found.append(pin)
    return found


def handle_deprecate_schema_package(uow: UnitOfWork, cmd: DeprecateSchemaPackage) -> CommandResult:
    """Stop new adoptions of a published version; projects that pin it keep it."""
    cmd = correlated(cmd)
    row = load(uow, cmd.package_id)
    _require_state(row, PUBLISHED)
    cmd = scoped(cmd, row.scope)
    moved = transition(uow, cmd, row.id, "deprecate", reason=cmd.reason)
    done = append(
        uow,
        cmd,
        row.id,
        SCHEMA_PACKAGE,
        [
            NewEvent(
                event_type=PACKAGE_DEPRECATED,
                payload={"reason": cmd.reason, "replacement": clean_optional_text(cmd.replacement)},
            )
        ],
    )
    bump()
    return CommandResult(
        stream_id=row.id,
        key=row.key,
        version=done.new_version,
        events=[*moved.events, *done.events],
    )


def handle_retire_schema_package(uow: UnitOfWork, cmd: RetireSchemaPackage) -> CommandResult:
    """Retire a deprecated version. Refused while a project pins it."""
    cmd = correlated(cmd)
    row = load(uow, cmd.package_id)
    _require_state(row, DEPRECATED)
    pinned = [
        a.project
        for a in registry.list_adoptions(uow.conn(), package=row.package)
        if a.version == row.version
    ]
    if pinned:
        raise AdoptionError(
            f"{row.key} is still pinned by {', '.join(sorted(pinned))}; move them off it first"
        )
    cmd = scoped(cmd, row.scope)
    moved = transition(uow, cmd, row.id, "retire", reason=cmd.reason)
    done = append(
        uow,
        cmd,
        row.id,
        SCHEMA_PACKAGE,
        [NewEvent(event_type=PACKAGE_RETIRED, payload={"reason": cmd.reason})],
    )
    bump()
    return CommandResult(
        stream_id=row.id,
        key=row.key,
        version=done.new_version,
        events=[*moved.events, *done.events],
    )


__all__ = [
    "AnalyseSchemaPackage",
    "ApproveSchemaPackage",
    "DeprecateSchemaPackage",
    "DraftSchemaPackage",
    "PublishSchemaPackage",
    "RequestSchemaChanges",
    "RetireSchemaPackage",
    "ReviseSchemaPackage",
    "SubmitSchemaPackage",
]
