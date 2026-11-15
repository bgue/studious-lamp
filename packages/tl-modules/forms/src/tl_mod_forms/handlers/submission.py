"""Submission commands: save a draft, discard it, submit (P2-FORMS S3, decisions D6, D10, D11).

The refusals run in one order (D11) and each carries a fixed text, never an answer: the scope is a
project; the subject, when named, is visible (a hidden, absent or other-project subject answers
``MSG_UNKNOWN`` before any answer is read); the submission is the actor's own; the template is
fillable; the version; the save bound; the answers.

Numbering (D6): the first save makes the record with no key. ``SubmitForm`` of a draft allocates the
key and writes it with ``Record.Updated`` in the same unit of work as ``Submission.Submitted`` and
the ``submit`` transition. A submit with no draft takes the number at creation. A resubmit of a
returned form keeps its number; a discarded draft never took one.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, Any

from sqlalchemy import text
from tl_core.forms.rules import validate_answers
from tl_core.ledger import NewEvent
from tl_core.numbering.allocator import allocate_key, segment_values
from tl_core.numbering.config import numbering_for
from tl_core.services.commands import CommandResult
from tl_core.services.errors import NoNumberingPatternError
from tl_core.services.records import create_module_record
from tl_core.settings.layers import project_of_scope
from tl_core.settings.resolver import value_of
from tl_core.uow import UnitOfWork
from tl_core.util import new_ulid

from tl_mod_forms.errors import (
    MSG_DRAFT_SAVES,
    MSG_NOT_FILLABLE,
    MSG_NOT_PUBLISHED,
    FormAnswersError,
    FormRuleError,
    FormStateError,
)
from tl_mod_forms.handlers.common import (
    Submission,
    Template,
    append,
    correlated,
    load_submission,
    load_template,
    move,
    require_project,
    require_subject,
    require_version,
    silent,
    today,
)
from tl_mod_forms.names import (
    DRAFT,
    DRAFT_SAVES_MAX,
    PUBLISHED,
    RETIRED,
    RETURNED,
    SUBMISSION,
    SUBMISSION_DRAFT_DISCARDED,
    SUBMISSION_DRAFT_SAVED,
    SUBMISSION_SUBMITTED,
    T_DISCARD,
    T_SUBMIT,
)

if TYPE_CHECKING:
    from tl_mod_forms.commands import DiscardFormDraft, SaveFormDraft, SubmitForm

_TAKEN_SQL = text("SELECT 1 FROM cur_core_record WHERE scope = :scope AND key = :key")
_FILLABLE_STATES = (DRAFT, RETURNED)
_UNKNOWN_KEY = re.compile(r"^unknown key .* in answer$", re.DOTALL)


def _require_state(sub: Submission, command: str, *states: str) -> None:
    if sub.state not in states:
        raise FormStateError(
            f"a form that is {sub.state} does not take {command}; it needs {' or '.join(states)}"
        )


def _require_fillable(template: Template, *, existing: bool) -> None:
    """D10: only a general template (not bound, not public). A new draft needs it Published; an
    existing draft may finish after the template is Retired (the answers pin it)."""
    if template.bound_record_type is not None or template.intake is not None:
        raise FormRuleError(MSG_NOT_FILLABLE)
    allowed = (PUBLISHED, RETIRED) if existing else (PUBLISHED,)
    if template.state not in allowed:
        raise FormRuleError(MSG_NOT_PUBLISHED)


def _safe(problem: str, ids: set[str]) -> str:
    """A rule's problem text with what it names kept to field ids: a question id that is not the
    template's (an answer's own text) is not repeated."""
    head, sep, rest = problem.partition(": ")
    rest = _UNKNOWN_KEY.sub("unknown key in answer", rest)  # the name of a key is the sender's too
    if not sep:
        return problem
    return f"{head if head in ids or head in ('answer', 'answers') else 'an answer'}: {rest}"


def _check_answers(template: Template, answers: list[dict[str, Any]], *, partial: bool) -> None:
    problems = validate_answers(
        template.fields, answers, fmt=template.format_version, partial=partial
    )
    if problems:
        ids = {str(f.get("id")) for f in template.fields}
        raise FormAnswersError(tuple(_safe(p, ids) for p in problems))


def _prepare(
    uow: UnitOfWork, cmd: SaveFormDraft | SubmitForm, command: str
) -> tuple[Template, Submission | None]:
    """D11 steps 1 to 5: scope, subject, own submission and its state, template, version."""
    require_project(cmd)
    require_subject(uow, cmd, cmd.subject_id)
    existing: Submission | None = None
    if cmd.draft_id is not None:
        existing = load_submission(uow, cmd, cmd.draft_id, own=True)
        _require_state(existing, command, *_FILLABLE_STATES)
        template = load_template(uow, str(existing.row["template_id"]))
        _require_fillable(template, existing=True)
        require_version(uow, existing.id, cmd.expected_version)
    else:
        assert cmd.template_id is not None
        template = load_template(uow, cmd.template_id)
        _require_fillable(template, existing=False)
    return template, existing


def _pin(template: Template, existing: Submission | None) -> dict[str, Any]:
    """The template the answers are for: copied from the template at the first save, from the
    draft after (a draft keeps the version and hash it was started with)."""
    if existing is None:
        return {
            "template_id": template.id,
            "template_version": template.version,
            "template_hash": template.content_hash,
            "answer_class": template.answer_class,
        }
    row = existing.row
    return {
        "template_id": row["template_id"],
        "template_version": row["template_version"],
        "template_hash": row["template_hash"],
        "answer_class": row["answer_class"],
    }


def handle_save_form_draft(uow: UnitOfWork, cmd: SaveFormDraft) -> CommandResult:
    """Save a draft with the answers so far. The first save makes the record with no number."""
    cmd = correlated(cmd)
    template, existing = _prepare(uow, cmd, "SaveFormDraft")
    saves = 0 if existing is None else int(existing.row["draft_saves"])
    limit = int(value_of(uow.conn(), DRAFT_SAVES_MAX, project=project_of_scope(cmd.scope)))
    if saves >= limit:
        raise FormRuleError(MSG_DRAFT_SAVES)
    _check_answers(template, cmd.answers, partial=True)
    saved = NewEvent(
        event_type=SUBMISSION_DRAFT_SAVED,
        payload=silent(
            {
                **_pin(template, existing),
                "subject_id": cmd.subject_id,
                "answers": cmd.answers,
                "save_no": saves + 1,
            }
        ),
    )
    if existing is not None:
        done = append(uow, cmd, existing.id, SUBMISSION, [saved])
        return CommandResult(
            stream_id=existing.id, key=existing.key, version=done.new_version, events=done.events
        )
    stream_id = new_ulid()
    made = uow.append(
        stream_id=stream_id,
        stream_type=SUBMISSION,
        scope=cmd.scope,
        expected_version=0,
        events=[
            NewEvent(
                event_type="Record.Created",
                payload={
                    "record_type": SUBMISSION,
                    "key": None,
                    "title": template.title,
                    "description": None,
                    "psets": {},
                },
            ),
            saved,
        ],
        actor=cmd.actor,
        source=cmd.source,
        correlation_id=cmd.correlation_id or new_ulid(),
        causation_id=cmd.causation_id,
    )
    return CommandResult(
        stream_id=stream_id, key=None, version=made.new_version, events=made.events
    )


def _allocate(uow: UnitOfWork, cmd: SubmitForm, sub_id: str) -> str:
    """The number of a submission, taken at submit."""
    conn = uow.conn()
    pattern = numbering_for(conn).find(cmd.scope, SUBMISSION)
    if pattern is None:
        raise NoNumberingPatternError(
            f"no numbering pattern for {SUBMISSION!r} in scope {cmd.scope!r}"
        )
    return allocate_key(
        uow,
        pattern=pattern,
        scope=cmd.scope,
        values=segment_values(pattern, cmd.scope, None),
        record_id=sub_id,
        record_type=SUBMISSION,
        actor=cmd.actor,
        source=cmd.source,
        correlation_id=cmd.correlation_id,
        causation_id=cmd.causation_id,
        is_taken=lambda key: (
            conn.execute(_TAKEN_SQL, {"scope": cmd.scope, "key": key}).first() is not None
        ),
    ).key


def handle_submit_form(uow: UnitOfWork, cmd: SubmitForm) -> CommandResult:
    """Submit a form: the answers are complete. A draft takes its number here; a form with no draft
    takes it at creation; a returned form keeps the one it has."""
    cmd = correlated(cmd)
    template, existing = _prepare(uow, cmd, "SubmitForm")
    _check_answers(template, cmd.answers, partial=False)
    submitted = NewEvent(
        event_type=SUBMISSION_SUBMITTED,
        payload=silent(
            {
                **_pin(template, existing),
                "subject_id": cmd.subject_id,
                "answers": cmd.answers,
                "submitted_on": today(),
            }
        ),
    )
    if existing is None:
        made = create_module_record(
            uow,
            cmd,
            record_type=SUBMISSION,
            title=template.title,
            key=None,
            extra_events=[submitted],
        )
        moved = move(uow, cmd, made.stream_id, T_SUBMIT)
        return CommandResult(
            stream_id=made.stream_id,
            key=made.key,
            version=moved.version,
            events=[*made.events, *moved.events],
        )
    key = existing.key
    events: list[NewEvent] = []
    if key is None:
        key = _allocate(uow, cmd, existing.id)
        events.append(
            NewEvent(event_type="Record.Updated", payload={"changes": {"key": [None, key]}})
        )
    events.append(submitted)
    done = append(uow, cmd, existing.id, SUBMISSION, events)
    moved = move(uow, cmd, existing.id, T_SUBMIT)
    return CommandResult(
        stream_id=existing.id, key=key, version=moved.version, events=[*done.events, *moved.events]
    )


def handle_discard_form_draft(uow: UnitOfWork, cmd: DiscardFormDraft) -> CommandResult:
    """Discard a draft of the actor's own; it never takes a number."""
    require_project(cmd)
    cmd = correlated(cmd)
    sub = load_submission(uow, cmd, cmd.submission_id, own=True)
    _require_state(sub, "DiscardFormDraft", DRAFT)
    require_version(uow, sub.id, cmd.expected_version)
    done = append(
        uow,
        cmd,
        sub.id,
        SUBMISSION,
        [NewEvent(event_type=SUBMISSION_DRAFT_DISCARDED, payload=silent({}))],
    )
    moved = move(uow, cmd, sub.id, T_DISCARD)
    return CommandResult(
        stream_id=sub.id, key=sub.key, version=moved.version, events=[*done.events, *moved.events]
    )


__all__ = ["handle_discard_form_draft", "handle_save_form_draft", "handle_submit_form"]
