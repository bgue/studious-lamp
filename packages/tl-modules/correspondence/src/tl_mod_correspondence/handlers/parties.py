"""Parties and their contacts: who we write to and who writes to us (brief 9 M10).

A **party** is an organisation on a project (the client, the engineer, a subcontractor, an
authority), known by a short code. Its **contacts** are the people at that party; a contact can be
limited to one domain and can be marked an authorised representative. Contacts are rows of the
party, not records: they change by events of the party (``Party.ContactAdded`` and
``Party.ContactEnded``), and an ended contact stays in the history. Parties carry no
confidentiality class. Registering and changing them is a document controller's act.
"""

from __future__ import annotations

import re
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator
from tl_core.ledger import NewEvent
from tl_core.services.commands import Command, CommandResult
from tl_core.services.records import create_module_record
from tl_core.uow import UnitOfWork

from tl_mod_correspondence import registry
from tl_mod_correspondence.errors import InvalidPartyError, PartyNotFoundError
from tl_mod_correspondence.handlers.common import append, correlated, require_project
from tl_mod_correspondence.handlers.models import PartyRole, non_blank
from tl_mod_correspondence.limits import (
    MAX_CONTACTS,
    MAX_DOMAINS,
    MAX_EMAIL,
    MAX_NUMBER,
    MAX_REASON,
    MAX_TEXT,
)
from tl_mod_correspondence.names import (
    PARTY,
    PARTY_CONTACT_ADDED,
    PARTY_CONTACT_ENDED,
    PARTY_DEFINED,
    PARTY_RETIRED,
)
from tl_mod_correspondence.textcheck import clean_optional_text, clean_text

_CODE = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,63}")
_DOMAIN = re.compile(r"[a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?(\.[a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?)+")
_EMAIL = re.compile(r"[^@\s<>()\[\]\\,;:\"]{1,64}@[a-z0-9.-]{1,190}")
_DOMAIN_CODE = re.compile(r"[a-z][a-z0-9_]{0,31}")


class ContactIn(BaseModel):
    """A person at a party."""

    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=MAX_TEXT)
    email: str | None = Field(default=None, max_length=MAX_EMAIL)
    title: str | None = Field(default=None, max_length=MAX_TEXT)
    domain: str | None = Field(
        default=None, max_length=32, description="A correspondence domain code; none means all."
    )
    is_authorised: bool = False

    @field_validator("name")
    @classmethod
    def _name(cls, value: str) -> str:
        return clean_text(non_blank(value))

    @field_validator("title")
    @classmethod
    def _title(cls, value: str | None) -> str | None:
        return clean_optional_text(value)

    @field_validator("email")
    @classmethod
    def _email(cls, value: str | None) -> str | None:
        if value is None:
            return None
        address = value.strip().lower()
        if _EMAIL.fullmatch(address) is None:
            raise ValueError(f"{value!r} is not an email address")
        return address

    @field_validator("domain")
    @classmethod
    def _domain(cls, value: str | None) -> str | None:
        if value is not None and _DOMAIN_CODE.fullmatch(value) is None:
            raise ValueError("a domain code is lower case: a letter, then letters, digits or _")
        return value


class RegisterParty(Command):
    """Register a party under its code, with its email domains and first contacts."""

    model_config = ConfigDict(extra="forbid")

    code: str = Field(min_length=1, max_length=64)
    name: str = Field(min_length=1, max_length=MAX_TEXT)
    project_role: PartyRole
    email_domains: list[str] = Field(default_factory=list, max_length=MAX_DOMAINS)
    contacts: list[ContactIn] = Field(default_factory=list, max_length=MAX_CONTACTS)

    @field_validator("code")
    @classmethod
    def _code(cls, value: str) -> str:
        if _CODE.fullmatch(value) is None:
            raise ValueError("a party code is letters, digits, '_', '.' or '-' (at most 64)")
        return value

    @field_validator("name")
    @classmethod
    def _name(cls, value: str) -> str:
        return clean_text(non_blank(value))

    @field_validator("email_domains")
    @classmethod
    def _domains(cls, value: list[str]) -> list[str]:
        cleaned = [d.strip().lower() for d in value]
        if len(set(cleaned)) != len(cleaned):
            raise ValueError("an email domain is listed once")
        for domain in cleaned:
            if _DOMAIN.fullmatch(domain) is None:
                raise ValueError(f"{domain!r} is not an email domain")
        return cleaned


class AddContact(Command):
    """Add a contact to a party."""

    model_config = ConfigDict(extra="forbid")

    party_id: str = Field(max_length=MAX_NUMBER)
    contact: ContactIn


class EndContact(Command):
    """End a contact (the person left, or changed role). The history keeps them."""

    model_config = ConfigDict(extra="forbid")

    party_id: str = Field(max_length=MAX_NUMBER)
    position: int = Field(ge=0, le=MAX_CONTACTS * 50)
    reason: str | None = Field(default=None, max_length=MAX_REASON)


class RetireParty(Command):
    """Retire a party that is no longer used. Items that name it keep the reference."""

    model_config = ConfigDict(extra="forbid")

    party_id: str = Field(max_length=MAX_NUMBER)
    reason: str = Field(max_length=MAX_REASON)

    @field_validator("reason")
    @classmethod
    def _reason(cls, value: str) -> str:
        return non_blank(value)


def _contact_payload(contact: ContactIn) -> dict[str, Any]:
    return {
        "name": contact.name,
        "email": contact.email,
        "title": contact.title,
        "domain": contact.domain,
        "is_authorised": contact.is_authorised,
    }


def _load_party(uow: UnitOfWork, cmd: Command, party_id: str) -> registry.PartyRow:
    found = registry.get_party(uow.conn(), party_id)
    if found is None or found.scope != cmd.scope:
        raise PartyNotFoundError(f"no party {party_id!r} in scope {cmd.scope!r}")
    return found


def handle_register_party(uow: UnitOfWork, cmd: RegisterParty) -> CommandResult:
    """Append ``Record.Created`` (key = the code) and ``Party.Defined`` with the first contacts.

    Raises ``CorrespondenceScopeError``, ``DuplicateKeyError`` (the code is taken in the scope)
    and ``InvalidPartyError`` (a contact's domain, or an email domain used by another party).
    """
    require_project(cmd)
    cmd = correlated(cmd)
    for other in registry.list_parties(uow.conn(), cmd.scope, include_inactive=True):
        clash = set(other.email_domains) & set(cmd.email_domains)
        if clash and other.is_active:
            raise InvalidPartyError(
                f"email domain {sorted(clash)[0]} already belongs to party {other.code}"
            )
    made = create_module_record(uow, cmd, record_type=PARTY, title=cmd.name, key=cmd.code)
    done = append(
        uow,
        cmd,
        made.stream_id,
        PARTY,
        [
            NewEvent(
                event_type=PARTY_DEFINED,
                payload={
                    "code": cmd.code,
                    "project_role": cmd.project_role,
                    "email_domains": cmd.email_domains,
                    "contacts": [_contact_payload(c) for c in cmd.contacts],
                },
            )
        ],
        expected=made.version,
    )
    return CommandResult(
        stream_id=made.stream_id,
        key=made.key,
        version=done.new_version,
        events=[*made.events, *done.events],
    )


def handle_add_contact(uow: UnitOfWork, cmd: AddContact) -> CommandResult:
    """Append ``Party.ContactAdded`` at the next position.

    Raises ``PartyNotFoundError``, ``InvalidPartyError`` (the party is retired, or has too many
    contacts).
    """
    cmd = correlated(cmd)
    party = _load_party(uow, cmd, cmd.party_id)
    if not party.is_active:
        raise InvalidPartyError(f"party {party.code} is retired")
    existing = registry.contacts_of(uow.conn(), party.id, include_ended=True)
    if len(existing) >= MAX_CONTACTS:
        raise InvalidPartyError(f"party {party.code} already has {MAX_CONTACTS} contacts")
    position = max((c.position for c in existing), default=-1) + 1
    done = append(
        uow,
        cmd,
        party.id,
        PARTY,
        [
            NewEvent(
                event_type=PARTY_CONTACT_ADDED,
                payload={"position": position, **_contact_payload(cmd.contact)},
            )
        ],
    )
    return CommandResult(
        stream_id=party.id, key=party.code, version=done.new_version, events=list(done.events)
    )


def handle_end_contact(uow: UnitOfWork, cmd: EndContact) -> CommandResult:
    """Append ``Party.ContactEnded``. ``InvalidPartyError`` when there is no such active contact."""
    cmd = correlated(cmd)
    party = _load_party(uow, cmd, cmd.party_id)
    active = {c.position for c in registry.contacts_of(uow.conn(), party.id)}
    if cmd.position not in active:
        raise InvalidPartyError(f"party {party.code} has no active contact {cmd.position}")
    done = append(
        uow,
        cmd,
        party.id,
        PARTY,
        [
            NewEvent(
                event_type=PARTY_CONTACT_ENDED,
                payload={"position": cmd.position, "reason": cmd.reason},
            )
        ],
    )
    return CommandResult(
        stream_id=party.id, key=party.code, version=done.new_version, events=list(done.events)
    )


def handle_retire_party(uow: UnitOfWork, cmd: RetireParty) -> CommandResult:
    """Append ``Party.Retired``. ``InvalidPartyError`` when it is already retired."""
    cmd = correlated(cmd)
    party = _load_party(uow, cmd, cmd.party_id)
    if not party.is_active:
        raise InvalidPartyError(f"party {party.code} is already retired")
    done = append(
        uow,
        cmd,
        party.id,
        PARTY,
        [NewEvent(event_type=PARTY_RETIRED, payload={"reason": cmd.reason})],
    )
    return CommandResult(
        stream_id=party.id, key=party.code, version=done.new_version, events=list(done.events)
    )
