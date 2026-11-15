"""Helpers the forms handlers share: scope, versions, appends, the loaders of a template and a
submission.

Every submission id a command is given goes through ``load_submission`` (``require_visible`` first,
ADR-0016): a record the viewer may not read, one in another project, one of another type, a draft
of another author and one that does not exist all answer ``RecordNotFoundError`` with the same
words, ``MSG_UNKNOWN``. Nothing here puts an answer in a text.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from sqlalchemy import text
from tl_core import confidentiality
from tl_core.ledger import AppendResult, NewEvent
from tl_core.services.commands import Command, CommandResult
from tl_core.services.errors import RecordNotFoundError
from tl_core.services.workflow import TransitionWorkflow, handle_transition_workflow
from tl_core.uow import UnitOfWork
from tl_core.util import new_ulid, utcnow

from tl_mod_forms.errors import (
    MSG_PROJECT,
    MSG_STALE,
    MSG_UNKNOWN,
    FormsScopeError,
    StaleVersionError,
)
from tl_mod_forms.names import (
    DISCARDED,
    DRAFT,
    FEED_NONE,
    SUBMISSION,
    SUBMISSION_TABLE,
    TEMPLATE,
    TEMPLATE_TABLE,
)

MSG_COMPANY = "a form template belongs to the company"
_VERSION_SQL = text("SELECT version FROM cur_core_record WHERE id = :id")
_STATUS_SQL = text("SELECT status FROM cur_core_record WHERE id = :id")
_ENVELOPE_SQL = text(
    "SELECT id, key, title, scope, type, voided FROM cur_core_record WHERE id = :id"
)
_TEMPLATE_SQL = text(f"SELECT * FROM {TEMPLATE_TABLE} WHERE id = :id")
_SUBMISSION_SQL = text(f"SELECT * FROM {SUBMISSION_TABLE} WHERE id = :id")


def require_project(cmd: Command) -> None:
    if not cmd.scope.startswith("project:"):
        raise FormsScopeError(MSG_PROJECT)


def require_company(cmd: Command) -> None:
    if cmd.scope != "company":
        raise FormsScopeError(MSG_COMPANY)


def correlated[C: Command](cmd: C) -> C:
    """``cmd`` with a correlation id, so every event of the command carries the same one."""
    if cmd.correlation_id is not None:
        return cmd
    return cmd.model_copy(update={"correlation_id": new_ulid()})


def today() -> str:
    """The server's day, ``YYYY-MM-DD`` (receipt time is the only time in v1)."""
    return utcnow().date().isoformat()


def version_of(uow: UnitOfWork, record_id: str) -> int:
    found = uow.conn().execute(_VERSION_SQL, {"id": record_id}).scalar_one_or_none()
    if found is None:
        raise LookupError(f"no record {record_id!r}")
    return int(found)


def require_version(uow: UnitOfWork, record_id: str, expected: int | None) -> None:
    """``StaleVersionError`` unless the record is at ``expected`` (``None`` skips the check)."""
    if expected is not None and version_of(uow, record_id) != expected:
        raise StaleVersionError(MSG_STALE)


def record_state(uow: UnitOfWork, record_id: str, initial: str) -> str:
    found = uow.conn().execute(_STATUS_SQL, {"id": record_id}).scalar_one_or_none()
    return initial if found is None else str(found)


def append(
    uow: UnitOfWork, cmd: Command, stream_id: str, stream_type: str, events: list[NewEvent]
) -> AppendResult:
    """Append ``events`` to a stream at its current version."""
    return uow.append(
        stream_id=stream_id,
        stream_type=stream_type,
        scope=cmd.scope,
        expected_version=version_of(uow, stream_id),
        events=events,
        actor=cmd.actor,
        source=cmd.source,
        correlation_id=cmd.correlation_id or new_ulid(),
        causation_id=cmd.causation_id,
    )


def silent(payload: dict[str, Any]) -> dict[str, Any]:
    """``payload`` with the feed policy of the events that make no card."""
    return {**payload, "feed_policy": FEED_NONE}


def move(uow: UnitOfWork, cmd: Command, record_id: str, transition: str) -> CommandResult:
    """Run workflow transition ``transition`` of a record as the module (no roles guard)."""
    return handle_transition_workflow(
        uow,
        TransitionWorkflow(
            actor=cmd.actor,
            source=cmd.source,
            scope=cmd.scope,
            correlation_id=cmd.correlation_id,
            causation_id=cmd.causation_id,
            stream_id=record_id,
            expected_version=version_of(uow, record_id),
            transition=transition,
            reason=None,
        ),
        by_module=True,
    )


def jsonl(value: Any, default: Any) -> Any:
    """A JSON column cell as a value (``default`` when it is empty)."""
    return default if value is None else json.loads(value)


@dataclass(frozen=True)
class Template:
    """A template as the handlers read it: the envelope, the typed row and the state."""

    id: str
    key: str | None
    title: str
    state: str
    version: int
    format_version: int
    fields: list[dict[str, Any]]
    bound_record_type: str | None
    answer_class: str | None
    intake: str | None
    purpose: str | None
    accepts_as: list[str] | None
    supersedes_id: str | None
    content_hash: str | None


def load_template(uow: UnitOfWork, template_id: str) -> Template:
    """The template; ``RecordNotFoundError`` (``MSG_UNKNOWN``) when it is absent or not one. A
    template holds no project text, so the hidden-looks-missing rule does not apply to it."""
    conn = uow.conn()
    env = conn.execute(_ENVELOPE_SQL, {"id": template_id}).first()
    row = conn.execute(_TEMPLATE_SQL, {"id": template_id}).mappings().first()
    if env is None or row is None or env.type != TEMPLATE:
        raise RecordNotFoundError(MSG_UNKNOWN)
    return Template(
        id=str(env.id),
        key=None if env.key is None else str(env.key),
        title=str(env.title),
        state=record_state(uow, template_id, DRAFT),
        version=int(row["template_version"]),
        format_version=int(row["format_version"]),
        fields=jsonl(row["form_fields_json"], []),
        bound_record_type=row["bound_record_type"],
        answer_class=row["answer_class"],
        intake=row["intake"],
        purpose=row["purpose"],
        accepts_as=jsonl(row["accepts_as_json"], None),
        supersedes_id=row["supersedes_id"],
        content_hash=row["content_hash"],
    )


@dataclass(frozen=True)
class Submission:
    """A submission as the handlers read it: the envelope, the typed row and the state."""

    id: str
    key: str | None
    state: str
    row: dict[str, Any]

    @property
    def author(self) -> str | None:
        return self.row["author"]


def load_submission(uow: UnitOfWork, cmd: Command, submission_id: str, *, own: bool) -> Submission:
    """The submission in ``cmd.scope``; ``RecordNotFoundError`` (``MSG_UNKNOWN``) when it is hidden,
    absent, in another project or not a submission, and when it is a draft (or a discarded one) of
    another author. With ``own`` the actor must be the author whatever the state."""
    conn = uow.conn()
    try:
        confidentiality.require_visible(conn, submission_id)
    except RecordNotFoundError:
        raise RecordNotFoundError(MSG_UNKNOWN) from None
    env = conn.execute(_ENVELOPE_SQL, {"id": submission_id}).first()
    row = conn.execute(_SUBMISSION_SQL, {"id": submission_id}).mappings().first()
    if env is None or row is None or env.type != SUBMISSION or env.scope != cmd.scope:
        raise RecordNotFoundError(MSG_UNKNOWN)
    state = record_state(uow, submission_id, DRAFT)
    if (own or state in (DRAFT, DISCARDED)) and row["author"] != cmd.actor:
        raise RecordNotFoundError(MSG_UNKNOWN)
    return Submission(
        id=str(env.id),
        key=None if env.key is None else str(env.key),
        state=state,
        row=dict(row),
    )


def require_subject(uow: UnitOfWork, cmd: Command, subject_id: str | None) -> None:
    """The record a form is about: visible to the viewer and in the command's project, else
    ``RecordNotFoundError`` (``MSG_UNKNOWN``, the same words for a hidden and an absent one)."""
    if subject_id is None:
        return
    conn = uow.conn()
    try:
        confidentiality.require_visible(conn, subject_id)
    except RecordNotFoundError:
        raise RecordNotFoundError(MSG_UNKNOWN) from None
    env = conn.execute(_ENVELOPE_SQL, {"id": subject_id}).first()
    if env is None or env.scope != cmd.scope or bool(env.voided):
        raise RecordNotFoundError(MSG_UNKNOWN)
