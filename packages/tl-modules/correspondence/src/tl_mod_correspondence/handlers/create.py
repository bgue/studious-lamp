"""Making an item: the one place the first events of a correspondence item are built.

``ReceiveCorrespondence`` (an item that arrived), ``DraftCorrespondence`` (a letter we write) and
the email ingest all call ``create_item``. It allocates the number from the numbering pattern,
appends ``Record.Created`` and ``Correspondence.Defined`` (and the clearances of a privileged
item), and moves a received item to Received. The checks that make the payload trustworthy are here
so that no caller can skip them: dates are real and near, a named party exists in the scope, a
domain and subtype are known, a text has no control character, a class is one of the three.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from tl_core.ledger import NewEvent
from tl_core.services.commands import Command, CommandResult
from tl_core.services.records import create_module_record
from tl_core.uow import UnitOfWork

from tl_mod_correspondence import catalog, registry
from tl_mod_correspondence.errors import InvalidItemError
from tl_mod_correspondence.handlers.common import append, plausible_date, transition
from tl_mod_correspondence.handlers.confidentiality import granted_events
from tl_mod_correspondence.handlers.models import Recipient
from tl_mod_correspondence.limits import MAX_BODY, MAX_RECIPIENTS
from tl_mod_correspondence.names import CORR_DEFINED, CORRESPONDENCE, DIRECTIONS
from tl_mod_correspondence.textcheck import clean_body


def check_recipients(uow: UnitOfWork, cmd: Command, recipients: Sequence[Recipient]) -> None:
    """Each named party exists in the command's scope; the list is bounded."""
    if len(recipients) > MAX_RECIPIENTS:
        raise InvalidItemError(f"at most {MAX_RECIPIENTS} recipients")
    check_party(uow, cmd, [r.party_id for r in recipients])


def check_party(uow: UnitOfWork, cmd: Command, party_ids: Sequence[str | None]) -> None:
    for party_id in party_ids:
        if party_id is None:
            continue
        found = registry.get_party(uow.conn(), party_id)
        if found is None or found.scope != cmd.scope:
            raise InvalidItemError(f"party {party_id!r} is not a party of {cmd.scope}")


def check_body(body: str | None) -> str | None:
    if body is None:
        return None
    if len(body) > MAX_BODY:
        raise InvalidItemError(f"the text of an item is at most {MAX_BODY} characters")
    try:
        return clean_body(body)
    except ValueError as exc:
        raise InvalidItemError(str(exc)) from exc


def create_item(
    uow: UnitOfWork,
    cmd: Command,
    *,
    subject: str,
    direction: str,
    medium: str,
    received_via: str,
    to: Sequence[Recipient] = (),
    cc: Sequence[Recipient] = (),
    external_ref: str | None = None,
    message_id: str | None = None,
    in_reply_to: str | None = None,
    from_party_id: str | None = None,
    from_name: str | None = None,
    sent_on: str | None = None,
    received_on: str | None = None,
    body: str | None = None,
    confidentiality: str = "internal",
    clearances: Sequence[str] = (),
    responds_to_id: str | None = None,
    response_required: bool = False,
    response_due: str | None = None,
    domain: str | None = None,
    subtype: str | None = None,
    received: bool = False,
    record_type: str = CORRESPONDENCE,
    numbering: Mapping[str, str] | None = None,
    domain_events: Sequence[NewEvent] = (),
) -> CommandResult:
    """Create an item: ``Record.Created``, ``Correspondence.Defined`` and, for ``received=True``,
    the move to Received. ``direction`` is in, out or internal.

    ``record_type`` is the type of the item: the core item for General and Document control, the
    Technical or Commercial type for those domains (their commands pass it, with ``numbering``
    holding the ``kind`` field of the domain's pattern and ``domain_events`` the events that
    write the domain row). The domain and subtype must belong to that record type.

    Raises ``InvalidItemError`` (a date, a party, a text, a vocabulary word),
    ``UnknownDomainError`` and the numbering errors of the core (``NoNumberingPatternError``).
    """
    if direction not in DIRECTIONS:
        raise InvalidItemError(f"direction is one of {', '.join(DIRECTIONS)}")
    if (domain is None) != (subtype is None):
        raise InvalidItemError("give the domain and the subtype together, or neither")
    if domain is not None and subtype is not None:
        definition = catalog.check_subtype(cmd.scope, domain, subtype)
        if definition.item_record_type != record_type:
            raise InvalidItemError(
                f"domain {domain!r} has items of its own kind; an item of that kind is made "
                "with the commands of the domain, and a letter cannot be filed into it"
                if record_type == CORRESPONDENCE
                else f"domain {domain!r} does not make items of this kind"
            )
    check_recipients(uow, cmd, [*to, *cc])
    check_party(uow, cmd, [from_party_id])
    try:
        sent = plausible_date(sent_on, "sent_on")
        arrived = plausible_date(received_on, "received_on")
        due = plausible_date(response_due, "response_due")
    except ValueError as exc:
        raise InvalidItemError(str(exc)) from exc
    text = check_body(body)
    made = create_module_record(
        uow, cmd, record_type=record_type, title=subject, key=None, numbering=dict(numbering or {})
    )
    payload: dict[str, Any] = {
        "number": made.key,
        "direction": direction,
        "medium": medium,
        "received_via": received_via,
        "external_ref": external_ref,
        "message_id": message_id,
        "in_reply_to": in_reply_to,
        "from_party_id": from_party_id,
        "from_name": from_name,
        "to": [r.as_payload() for r in to],
        "cc": [r.as_payload() for r in cc],
        "sent_on": sent,
        "received_on": arrived,
        "body": text,
        "confidentiality": confidentiality,
        "responds_to_id": responds_to_id,
        "response_required": response_required,
        "response_due": due,
        "domain": domain,
        "subtype": subtype,
    }
    events = [NewEvent(event_type=CORR_DEFINED, payload=payload)]
    events += granted_events(list(clearances), "named when the item was made")
    events += list(domain_events)
    done = append(uow, cmd, made.stream_id, record_type, events, expected=made.version)
    version, all_events = done.new_version, [*made.events, *done.events]
    if received:
        moved = transition(uow, cmd, made.stream_id, "receive")
        version, all_events = moved.version, [*all_events, *moved.events]
    return CommandResult(stream_id=made.stream_id, key=made.key, version=version, events=all_events)
