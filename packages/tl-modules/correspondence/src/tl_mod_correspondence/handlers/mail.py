"""Email in: an ``.eml`` file becomes a received item with its files (brief 9 M10).

``read_email`` parses the message in the resource envelope (``eml_isolated``): bounded, text only,
nothing fetched or followed; a message that is over a bound or holds a hostile character is refused
with a fixed text (``InvalidItemError``). ``ingest_email`` then makes the item in one unit of work:

1. the item is numbered and received (``email`` medium, `internal`); a message whose Message-ID is
   already in the register is refused;
2. the party is matched from the sender's address (a contact's email, else the party that owns the
   domain), and likewise each recipient;
3. the item joins the thread its headers, item numbers or subject point to (``references`` too);
4. the whole original is kept in the module-only slot ``message``, and each attachment goes into the
   slot ``attachment`` **the way a person's upload goes**: the item's upload guard and the file
   scan apply to it.

If anything fails nothing is written. The text of the message that becomes record text was checked
by the parser. There is no SMTP and nothing leaves the machine. The ingest is called by the CLI
(embedded); it is not an API command, because a command body is limited to 1 MiB and a message to
10 MiB.
"""

from __future__ import annotations

from pydantic import ConfigDict, Field, field_validator
from tl_core.services.commands import Command, CommandResult
from tl_core.uow import UnitOfWork

from tl_mod_correspondence import files, registry
from tl_mod_correspondence.eml import EmlAddress, EmlRefused, ParsedMessage
from tl_mod_correspondence.eml_isolated import parse_eml_isolated
from tl_mod_correspondence.errors import InvalidItemError
from tl_mod_correspondence.handlers.common import correlated, require_project, today
from tl_mod_correspondence.handlers.create import create_item
from tl_mod_correspondence.handlers.models import Recipient
from tl_mod_correspondence.handlers.threads import assign_thread
from tl_mod_correspondence.limits import MAX_TEXT
from tl_mod_correspondence.names import SLOT_ATTACHMENT, SLOT_MESSAGE
from tl_mod_correspondence.textcheck import clean_optional_text

NO_SUBJECT = "(no subject)"
HTML_ONLY = "(This message has only an HTML part; the original is kept in the message file.)"


class IngestEmail(Command):
    """Carrier of an email ingest: who, from where, and the file name the message came with."""

    model_config = ConfigDict(extra="forbid")

    original_name: str | None = Field(default=None, max_length=MAX_TEXT)

    @field_validator("original_name")
    @classmethod
    def _clean_original_name(cls, value: str | None) -> str | None:
        return clean_optional_text(value)


def read_email(data: bytes) -> ParsedMessage:
    """Parse ``data`` in the envelope. Raises ``InvalidItemError`` (a fixed text) when refused."""
    try:
        return parse_eml_isolated(data)
    except EmlRefused as exc:
        raise InvalidItemError(f"the email was refused: {exc}") from exc


def _recipients(uow: UnitOfWork, scope: str, addresses: tuple[EmlAddress, ...]) -> list[Recipient]:
    out: list[Recipient] = []
    for address in addresses:
        party = registry.party_by_email(uow.conn(), scope, address.email) if address.email else None
        out.append(
            Recipient(
                name=address.name,
                email=address.email,
                party_id=party.id if party is not None else None,
            )
        )
    return out


def ingest_email(
    uow: UnitOfWork, cmd: IngestEmail, parsed: ParsedMessage, original: bytes
) -> CommandResult:
    """Make the received item for ``parsed`` and store the original and the attachments.

    Raises ``CorrespondenceScopeError``, ``InvalidItemError`` (a message id already received, a
    date, a text) and the file service's refusals (a file the scan rejects, the guard). Nothing is
    written when it raises.
    """
    require_project(cmd)
    cmd = correlated(cmd)
    if parsed.message_id is not None:
        known = registry.find_by_message_id(uow.conn(), cmd.scope, parsed.message_id)
        if known is not None:
            raise InvalidItemError(f"message {parsed.message_id} is already item {known.number}")
    sender = EmlAddress(parsed.from_name, parsed.from_email)
    party = registry.party_by_email(uow.conn(), cmd.scope, sender.email) if sender.email else None
    made = create_item(
        uow,
        cmd,
        subject=parsed.subject or NO_SUBJECT,
        direction="in",
        medium="email",
        received_via="email",
        to=_recipients(uow, cmd.scope, parsed.to),
        cc=_recipients(uow, cmd.scope, parsed.cc),
        message_id=parsed.message_id,
        in_reply_to=parsed.in_reply_to,
        from_party_id=party.id if party is not None else None,
        from_name=sender.name or sender.email,
        sent_on=parsed.sent_on,
        received_on=today(),
        body=parsed.body if parsed.body is not None else (HTML_ONLY if parsed.html_only else None),
        received=True,
    )
    item = registry.get_item(uow.conn(), made.stream_id)
    assert item is not None
    threaded = assign_thread(uow, cmd, item, parsed.references)
    base = {
        "actor": cmd.actor,
        "source": cmd.source,
        "scope": cmd.scope,
        "record_id": made.stream_id,
        "correlation_id": cmd.correlation_id or "",
    }
    files.store_file(
        uow,
        slot=SLOT_MESSAGE,
        filename=cmd.original_name or f"{made.key}.eml",
        content_type="message/rfc822",
        data=original,
        by_module=True,
        **base,
    )
    for attachment in parsed.attachments:
        files.store_file(
            uow,
            slot=SLOT_ATTACHMENT,
            filename=attachment.filename,
            content_type=attachment.content_type,
            data=attachment.data,
            by_module=False,
            **base,
        )
    current = registry.get_item(uow.conn(), made.stream_id)
    return CommandResult(
        stream_id=made.stream_id,
        key=made.key,
        version=current.version if current else made.version,
        events=[*made.events, *threaded],
    )
