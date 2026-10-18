"""Issue a letter: render the PDF, store it, "send" it (a stub), start the clocks (brief 9 M10).

``IssueCorrespondence`` is the external act: a document controller (or admin) issues a Draft
outgoing letter. In one unit of work it:

1. fills the domain's letter template with the item's number, date, subject, recipients and text;
2. renders a deterministic PDF (``letter.py``, no library) and stores it in the slot ``rendition``;
3. starts the clocks the subtype defines for *issue* (a reply expected in 14 days, say);
4. appends ``Correspondence.Issued`` with ``delivery = "stub"``: **nothing is sent**. Phase 1 has
   no SMTP; the record says so, and a later increment replaces the stub;
5. moves the item to Issued; and, when the letter answers an item that is still waiting for an
   answer, records that answer (``mark_responded``).
"""

from __future__ import annotations

from pydantic import ConfigDict, Field
from tl_core.ledger import Event, NewEvent
from tl_core.services.commands import Command, CommandResult
from tl_core.uow import UnitOfWork

from tl_mod_correspondence import catalog, files, registry
from tl_mod_correspondence.errors import InvalidItemError, ItemStateError, LetterRenderError
from tl_mod_correspondence.handlers.common import (
    append,
    correlated,
    open_item,
    require_state,
    resolve_date,
    transition,
)
from tl_mod_correspondence.handlers.responses import mark_responded
from tl_mod_correspondence.handlers.triage import start_template_clocks
from tl_mod_correspondence.letter import LetterError, LetterFields, compose_letter, render_pdf
from tl_mod_correspondence.limits import MAX_NUMBER, MAX_REASON
from tl_mod_correspondence.names import (
    CORR_ISSUED,
    CORRESPONDENCE,
    ST_DRAFT,
    ST_ISSUED,
    ST_RECEIVED,
    ST_TRIAGED,
)


class IssueCorrespondence(Command):
    """Issue a Draft letter (a document controller's act).

    ``template`` is a letter template of the item's domain (by default the first one for its
    subtype). ``issued_on`` is the date on the letter (today by default; an earlier day needs
    ``date_reason``; never later than today). The send is a stub: nothing leaves the machine.
    """

    model_config = ConfigDict(extra="forbid")

    stream_id: str
    expected_version: int | None = None
    template: str | None = Field(default=None, max_length=MAX_NUMBER)
    issued_on: str | None = Field(default=None, max_length=10)
    date_reason: str | None = Field(default=None, max_length=MAX_REASON)


def _recipient_line(item: registry.ItemRow) -> str:
    names = [r.get("name") or r.get("email") or "" for r in item.to]
    return ", ".join(n for n in names if n)


def handle_issue_correspondence(uow: UnitOfWork, cmd: IssueCorrespondence) -> CommandResult:
    """Render, store, "send", start the issue clocks, append ``Correspondence.Issued``.

    Raises ``RecordNotFoundError`` (unknown, foreign or hidden), ``ItemStateError`` (not a Draft
    outgoing letter), ``InvalidItemError`` (no domain and subtype, or no recipient),
    ``UnknownDomainError``, ``LetterRenderError`` (no such template, a letter the renderer
    refuses, no file service) and the date errors of ``resolve_date``.
    """
    cmd = correlated(cmd)
    item = open_item(uow, cmd, cmd.stream_id)
    require_state(item, ST_DRAFT)
    if item.direction != "out":
        raise ItemStateError(f"item {item.number} was received; only a letter we wrote is issued")
    if item.domain is None or item.subtype is None:
        raise InvalidItemError(
            f"item {item.number} has no domain and subtype; reclassify it before issue"
        )
    recipients = _recipient_line(item)
    if not recipients:
        raise InvalidItemError(f"item {item.number} has no recipient")
    definition = catalog.check_subtype(cmd.scope, item.domain, item.subtype)
    day, date_reason = resolve_date(cmd.issued_on, cmd.date_reason, "the issue day")
    wanted = cmd.template
    templates = [t for t in definition.templates if wanted is None or t.code == wanted]
    if wanted is None:
        templates = [t for t in templates if t.subtype == item.subtype]
    if not templates:
        raise LetterRenderError(
            f"domain {definition.code} has no letter template "
            + (f"{wanted!r}" if wanted else f"for subtype {item.subtype}")
        )
    template = templates[0]
    try:
        lines = compose_letter(
            template.header,
            template.footer,
            LetterFields(
                number=item.number,
                date=day,
                subject=item.subject,
                to=recipients,
                body=item.body or "",
            ),
        )
        pdf = render_pdf(lines, title=f"{item.number} {item.subject}")
    except LetterError as exc:
        raise LetterRenderError(str(exc)) from exc
    stored = files.write_rendition(
        uow,
        actor=cmd.actor,
        source=cmd.source,
        scope=cmd.scope,
        record_id=item.id,
        filename=f"{item.number}.pdf",
        data=pdf,
        correlation_id=cmd.correlation_id or "",
    )
    clock_ids, clock_events = start_template_clocks(
        uow, cmd, item, definition, item.subtype, "issue", day
    )
    done = append(
        uow,
        cmd,
        item.id,
        CORRESPONDENCE,
        [
            NewEvent(
                event_type=CORR_ISSUED,
                payload={
                    "issued_on": day,
                    "date_reason": date_reason,
                    "rendition_file_id": stored.file_id,
                    "rendition_sha256": stored.sha256,
                    "template": template.code,
                    "delivery": "stub",
                    "clock_ids": clock_ids,
                },
            )
        ],
        expected=cmd.expected_version or item.version,
    )
    moved = transition(uow, cmd, item.id, "issue")
    answered: list[Event] = []
    if item.responds_to_id is not None:
        parent = registry.get_item(uow.conn(), item.responds_to_id)
        if parent is not None and parent.state in (ST_RECEIVED, ST_TRIAGED, ST_ISSUED):
            result = mark_responded(
                uow, cmd, parent, response_id=item.id, day=day, reason="a reply was issued"
            )
            answered = list(result.events)
    return CommandResult(
        stream_id=item.id,
        key=item.number,
        version=moved.version,
        events=[*clock_events, *done.events, *moved.events, *answered],
    )
