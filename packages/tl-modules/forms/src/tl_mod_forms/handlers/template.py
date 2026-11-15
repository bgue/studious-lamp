"""Template commands: draft, edit, publish, revise, retire (P2-FORMS S3, decision D9).

One record per version. A Draft is always clean under ``validate_questions`` (an incomplete
template is not stored). Publishing fixes the content hash and does not retire the predecessor;
retiring is its own command. Every state move is a ``by_module`` transition run in the same unit of
work as the module's own event.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from sqlalchemy import text
from tl_core.forms.rules import content_hash, intake_problems, validate_questions
from tl_core.ledger import NewEvent
from tl_core.services.commands import CommandResult
from tl_core.services.records import create_module_record
from tl_core.uow import UnitOfWork

from tl_mod_forms.errors import (
    MSG_INTAKE_FIELDS,
    MSG_NOTHING,
    MSG_ONE_DRAFT,
    FormRuleError,
    FormStateError,
    FormTemplateError,
)
from tl_mod_forms.handlers.common import (
    Template,
    append,
    correlated,
    load_template,
    move,
    require_company,
    require_version,
    silent,
    today,
)
from tl_mod_forms.names import (
    DRAFT,
    PUBLISHED,
    RETIRED,
    T_PUBLISH,
    T_RETIRE,
    TEMPLATE,
    TEMPLATE_CREATED,
    TEMPLATE_EDITED,
    TEMPLATE_PUBLISHED,
    TEMPLATE_RETIRED,
    TEMPLATE_TABLE,
)

if TYPE_CHECKING:
    from tl_mod_forms.commands import (
        DraftFormTemplate,
        EditFormTemplate,
        PublishFormTemplate,
        RetireFormTemplate,
        ReviseFormTemplate,
    )

_BACK_SQL = text(f"SELECT supersedes_id FROM {TEMPLATE_TABLE} WHERE id = :id")
_FORWARD_SQL = text(f"SELECT id FROM {TEMPLATE_TABLE} WHERE supersedes_id = :id")
_MAX_LINEAGE = 1000
_EDIT_COLUMN = {"fields": "form_fields"}


def _require_state(template: Template, command: str, *states: str) -> None:
    if template.state not in states:
        raise FormStateError(
            f"a template that is {template.state} does not take {command}; "
            f"it needs {' or '.join(states)}"
        )


def _problems(template_like: dict[str, Any], fmt: int) -> list[str]:
    """What stops a template being stored as a Draft: its questions and its intake flags."""
    found = list(validate_questions(template_like["fields"], fmt=fmt))
    if template_like["intake"] is None and (
        template_like["purpose"] is not None or template_like["accepts_as"] is not None
    ):
        found.append(MSG_INTAKE_FIELDS)
    return found


def _created_event(version: int, supersedes: str | None, body: dict[str, Any]) -> NewEvent:
    fields = body["fields"]
    return NewEvent(
        event_type=TEMPLATE_CREATED,
        payload=silent(
            {
                "format_version": body["format_version"],
                "form_fields": fields,
                "field_count": len(fields),
                "version": version,
                "supersedes_id": supersedes,
                "bound_record_type": body["bound_record_type"],
                "answer_class": body["answer_class"],
                "intake": body["intake"],
                "purpose": body["purpose"],
                "accepts_as": body["accepts_as"],
            }
        ),
    )


def handle_draft_form_template(uow: UnitOfWork, cmd: DraftFormTemplate) -> CommandResult:
    """A new template, Draft, version 1, key ``TPL-0001``."""
    require_company(cmd)
    cmd = correlated(cmd)
    body: dict[str, Any] = {
        "format_version": cmd.format_version,
        "fields": cmd.fields,
        "bound_record_type": cmd.bound_record_type,
        "answer_class": cmd.answer_class,
        "intake": cmd.intake,
        "purpose": cmd.purpose,
        "accepts_as": cmd.accepts_as,
    }
    problems = _problems(body, cmd.format_version)
    if problems:
        raise FormTemplateError(tuple(problems))
    return create_module_record(
        uow,
        cmd,
        record_type=TEMPLATE,
        title=cmd.title,
        key=None,
        extra_events=[_created_event(1, None, body)],
    )


def handle_edit_form_template(uow: UnitOfWork, cmd: EditFormTemplate) -> CommandResult:
    """Change fields of a Draft template; the result must be clean."""
    require_company(cmd)
    cmd = correlated(cmd)
    template = load_template(uow, cmd.template_id)
    _require_state(template, "EditFormTemplate", DRAFT)
    require_version(uow, template.id, cmd.expected_version)
    current: dict[str, Any] = {
        "title": template.title,
        "fields": template.fields,
        "answer_class": template.answer_class,
        "intake": template.intake,
        "purpose": template.purpose,
        "accepts_as": template.accepts_as,
    }
    changes: dict[str, list[Any]] = {}
    for name in [n for n in current if n in cmd.model_fields_set]:
        new = getattr(cmd, name)
        if new != current[name]:
            changes[name] = [current[name], new]
    if not changes:
        raise FormRuleError(MSG_NOTHING)
    result = {
        name: changes[name][1] if name in changes else value for name, value in current.items()
    }
    problems = _problems(result, template.format_version)
    if problems:
        raise FormTemplateError(tuple(problems))
    events: list[NewEvent] = []
    if "title" in changes:
        events.append(
            NewEvent(event_type="Record.Updated", payload={"changes": {"title": changes["title"]}})
        )
    payload_changes = {_EDIT_COLUMN.get(n, n): pair for n, pair in changes.items()}
    if "fields" in changes:
        payload_changes["field_count"] = [len(template.fields), len(result["fields"])]
    events.append(
        NewEvent(event_type=TEMPLATE_EDITED, payload=silent({"changes": payload_changes}))
    )
    done = append(uow, cmd, template.id, TEMPLATE, events)
    return CommandResult(
        stream_id=template.id, key=template.key, version=done.new_version, events=done.events
    )


def handle_publish_form_template(uow: UnitOfWork, cmd: PublishFormTemplate) -> CommandResult:
    """Draft to Published: the questions are checked again (a public template also needs
    ``intake_problems`` clean) and the content hash is set."""
    require_company(cmd)
    cmd = correlated(cmd)
    template = load_template(uow, cmd.template_id)
    _require_state(template, "PublishFormTemplate", DRAFT)
    require_version(uow, template.id, cmd.expected_version)
    problems = validate_questions(template.fields, fmt=template.format_version)
    if template.intake == "public":
        problems += intake_problems(
            template.fields, purpose=template.purpose or "", accepts_as=template.accepts_as or []
        )
    if problems:
        raise FormTemplateError(tuple(problems))
    digest = content_hash(template.fields, fmt=template.format_version)
    done = append(
        uow,
        cmd,
        template.id,
        TEMPLATE,
        [
            NewEvent(
                event_type=TEMPLATE_PUBLISHED,
                payload=silent({"published_on": today(), "content_hash": digest}),
            )
        ],
    )
    moved = move(uow, cmd, template.id, T_PUBLISH)
    return CommandResult(
        stream_id=template.id,
        key=template.key,
        version=moved.version,
        events=[*done.events, *moved.events],
    )


def _lineage(uow: UnitOfWork, template_id: str) -> list[str]:
    """Every template of the lineage of ``template_id`` (its root and all that supersede it)."""
    conn = uow.conn()
    root = template_id
    for _ in range(_MAX_LINEAGE):
        before = conn.execute(_BACK_SQL, {"id": root}).scalar_one_or_none()
        if before is None:
            break
        root = str(before)
    found = [root]
    queue = [root]
    while queue and len(found) < _MAX_LINEAGE:
        for row in conn.execute(_FORWARD_SQL, {"id": queue.pop()}):
            found.append(str(row.id))
            queue.append(str(row.id))
    return found


def handle_revise_form_template(uow: UnitOfWork, cmd: ReviseFormTemplate) -> CommandResult:
    """A Published or Retired template to a new Draft, version n+1 (``supersedes_id`` is the old
    record). A lineage holds one open Draft."""
    require_company(cmd)
    cmd = correlated(cmd)
    template = load_template(uow, cmd.template_id)
    _require_state(template, "ReviseFormTemplate", PUBLISHED, RETIRED)
    require_version(uow, template.id, cmd.expected_version)
    lineage = _lineage(uow, template.id)
    top = 0
    for member in lineage:
        other = load_template(uow, member)
        top = max(top, other.version)
        if other.state == DRAFT:
            raise FormRuleError(MSG_ONE_DRAFT)
    body: dict[str, Any] = {
        "format_version": template.format_version,
        "fields": template.fields,
        "bound_record_type": template.bound_record_type,
        "answer_class": template.answer_class,
        "intake": template.intake,
        "purpose": template.purpose,
        "accepts_as": template.accepts_as,
    }
    return create_module_record(
        uow,
        cmd,
        record_type=TEMPLATE,
        title=template.title,
        key=None,
        extra_events=[_created_event(top + 1, template.id, body)],
    )


def handle_retire_form_template(uow: UnitOfWork, cmd: RetireFormTemplate) -> CommandResult:
    """Published or Draft to Retired, the final state."""
    require_company(cmd)
    cmd = correlated(cmd)
    template = load_template(uow, cmd.template_id)
    _require_state(template, "RetireFormTemplate", PUBLISHED, DRAFT)
    require_version(uow, template.id, cmd.expected_version)
    done = append(
        uow,
        cmd,
        template.id,
        TEMPLATE,
        [NewEvent(event_type=TEMPLATE_RETIRED, payload=silent({"retired_on": today()}))],
    )
    moved = move(uow, cmd, template.id, T_RETIRE)
    return CommandResult(
        stream_id=template.id,
        key=template.key,
        version=moved.version,
        events=[*done.events, *moved.events],
    )


__all__ = [
    "handle_draft_form_template",
    "handle_edit_form_template",
    "handle_publish_form_template",
    "handle_retire_form_template",
    "handle_revise_form_template",
]
