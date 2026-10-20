# P1-I5-T07f — Parties, contacts and contract clauses

Status: ready
Tier: haiku
Labels: module, core
Depends on: — (the models, the projectors and the registry reads are in the tree at the branch point)
Branch: `p1/i5-t07f-parties-clauses`

## Goal
`handlers/parties.py` and `handlers/clauses.py` have their command models and helpers; the six handlers (`handle_register_party`, `handle_add_contact`, `handle_end_contact`, `handle_retire_party`, `handle_define_clause`, `handle_retire_clause`) raise `NotImplementedError`. You implement them by their STEPS comments. A document controller registers the organisations we write to (with their contacts) and the contract clauses a clock can cite. One provided test file must pass on SQLite and on Postgres.

## Brief references (pasted)
> **How a correspondence command is written (D6, D6b, ADR-0010, ADR-0016).** A handler is `handle_x(uow, cmd)`; it runs in an entered unit of work, appends through it and never commits. Every check is made before anything is appended. It reads an item **only** through `open_item`, `load_item` or `registry.get_item` (they apply the confidentiality filter: an item the person may not read answers the same `RecordNotFoundError` as one that does not exist); it never queries the item table itself and never inspects who the caller is: who may call a command is decided by the API (`commands.py`). The module moves its own items through the workflow with `transition(...)` (the generic `TransitionWorkflow` is not allowed on items). Time comes only from `today()` in `handlers/common.py`.
>
> **Command models and docstrings are the contract.** Do not change a model, a field, a docstring or a name in a file you complete; only the function bodies that carry a STEPS comment are yours.
>
> **Parties and clauses (brief 9, M10).** A party has a project role and a contact list; a contact can be limited to a domain and marked an authorised representative. A clause has a time bar (days and day type), the notice it requires, to whom and how it is served. Parties and clauses carry no confidentiality class. Positions of contacts start at 1 and are never reused.

### Learnings that apply
> **L-P1-I5-1.** Postgres cannot infer the type of a bare parameter in `CASE WHEN :p IS NOT NULL ...` (`could not determine data type of parameter $1`), and a Python bool is the portable value for a boolean column. Compute such choices in Python; run the test on both adapters before you report.
>
> **L-P1-I1-6.** A parity run's count is not the SQLite count twice: a case that does not use the `db`/`new_db`/`engine`/`world` fixtures runs once. The counts below are exact.
>
> **L-P1-I3-5.** A test that only passes with the whole module in place is the module's test: run the provided file as it is; do not add helpers to it or to the shared test support (`tl_mod_correspondence/testing.py`).
> **L-P0-I1-6.** ruff's `E501` applies to docstrings and comments at 100 columns, and pyright strict flags `@contextmanager` functions annotated `Iterator[X]`. Wrap prose.
>
> **L-P0-I6C-8 / L-P1-I0B-3.** Write files with the Write tool, not a long `cat > file <<'EOF'` inside a `&&` chain, and never `pkill -f`: kill only a PID you started.
>
> **L-P1-I3B-6.** Copy the provided test byte for byte (`cp`), run `ruff` and `pyright` on the tree, and do not edit the copy: if it cannot pass, stop and report *Blocked*.

## Interfaces (verbatim from the repo at the branch point)
`packages/tl-modules/correspondence/src/tl_mod_correspondence/handlers/parties.py` (the stub you complete; the whole file):
```python
# ruff: noqa: F401, F841
"""Parties and their contacts: who we write to and who writes to us (brief 9 M10).

A **party** is an organisation on a project (the client, the engineer, a subcontractor, an
authority), known by a short code. Its **contacts** are the people at that party; a contact can be
limited to one domain and can be marked an authorised representative. Contacts are rows of the
party, not records: they change by events of the party (``Party.ContactAdded`` and
``Party.ContactEnded``), and an ended contact stays in the history. Parties carry no
confidentiality class. Registering and changing them is a document controller's act.

STUB (P1-I5-T07f): the functions with a STEPS comment are for you to write. When they are
written, delete this paragraph, the STEPS comments and the `ruff: noqa` line at the top.
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
    position: int = Field(ge=1, le=MAX_CONTACTS * 50)
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
    # STEPS
    # 1. `require_project(cmd)`; `cmd = correlated(cmd)`.
    # 2. For each `other` in `registry.list_parties(uow.conn(), cmd.scope,
    #    include_inactive=True)`: `clash = set(other.email_domains) & set(cmd.email_domains)`;
    #    when `clash and other.is_active` raise `InvalidPartyError(f"email domain
    #    {sorted(clash)[0]} already belongs to party {other.code}")`.
    # 3. `made = create_module_record(uow, cmd, record_type=PARTY, title=cmd.name,
    #    key=cmd.code)` (a code already used in the scope raises `DuplicateKeyError` there).
    # 4. `done = append(uow, cmd, made.stream_id, PARTY, [NewEvent(event_type=PARTY_DEFINED,
    #    payload={"code": cmd.code, "project_role": cmd.project_role, "email_domains":
    #    cmd.email_domains, "contacts": [_contact_payload(c) for c in cmd.contacts]})],
    #    expected=made.version)`; return `CommandResult(stream_id=made.stream_id, key=made.key,
    #    version=done.new_version, events=[*made.events, *done.events])`.
    raise NotImplementedError


def handle_add_contact(uow: UnitOfWork, cmd: AddContact) -> CommandResult:
    """Append ``Party.ContactAdded`` at the next position (from 1; a position is never reused).

    Raises ``PartyNotFoundError``, ``InvalidPartyError`` (the party is retired, or has too many
    contacts).
    """
    # STEPS
    # 1. `cmd = correlated(cmd)`; `party = _load_party(uow, cmd, cmd.party_id)`. When `not
    #    party.is_active` raise `InvalidPartyError(f"party {party.code} is retired")`.
    # 2. `existing = registry.contacts_of(uow.conn(), party.id, include_ended=True)`. When
    #    `len(existing) >= MAX_CONTACTS` raise `InvalidPartyError(f"party {party.code} already
    #    has {MAX_CONTACTS} contacts")`.
    # 3. `position = max((c.position for c in existing), default=0) + 1` (positions start at 1
    #    and are never reused, even after a contact ends).
    # 4. `done = append(uow, cmd, party.id, PARTY, [NewEvent(event_type=PARTY_CONTACT_ADDED,
    #    payload={"position": position, **_contact_payload(cmd.contact)})])`; return
    #    `CommandResult(stream_id=party.id, key=party.code, version=done.new_version,
    #    events=list(done.events))`.
    raise NotImplementedError


def handle_end_contact(uow: UnitOfWork, cmd: EndContact) -> CommandResult:
    """Append ``Party.ContactEnded``. ``InvalidPartyError`` when there is no such active contact."""
    # STEPS
    # 1. `cmd = correlated(cmd)`; `party = _load_party(uow, cmd, cmd.party_id)`; `active =
    #    {c.position for c in registry.contacts_of(uow.conn(), party.id)}`. When `cmd.position
    #    not in active` raise `InvalidPartyError(f"party {party.code} has no active contact
    #    {cmd.position}")`.
    # 2. `done = append(uow, cmd, party.id, PARTY, [NewEvent(event_type=PARTY_CONTACT_ENDED,
    #    payload={"position": cmd.position, "reason": cmd.reason})])`; return
    #    `CommandResult(stream_id=party.id, key=party.code, version=done.new_version,
    #    events=list(done.events))`.
    raise NotImplementedError


def handle_retire_party(uow: UnitOfWork, cmd: RetireParty) -> CommandResult:
    """Append ``Party.Retired``. ``InvalidPartyError`` when it is already retired."""
    # STEPS
    # 1. `cmd = correlated(cmd)`; `party = _load_party(uow, cmd, cmd.party_id)`. When `not
    #    party.is_active` raise `InvalidPartyError(f"party {party.code} is already retired")`.
    # 2. `done = append(uow, cmd, party.id, PARTY, [NewEvent(event_type=PARTY_RETIRED,
    #    payload={"reason": cmd.reason})])`; return `CommandResult(stream_id=party.id,
    #    key=party.code, version=done.new_version, events=list(done.events))`.
    raise NotImplementedError
```

`packages/tl-modules/correspondence/src/tl_mod_correspondence/handlers/clauses.py` (the stub you complete; the whole file):
```python
# ruff: noqa: F401, F841
"""Contract clauses: the time bars and notice rules a clock can cite (brief 9 M10).

A **clause** is one row of the contract register: the contract, the clause number, how many days
the clause allows for a notice (a *time bar*), what the notice must contain, to whom it must be
served and how, and the domains that cite it. A clock may name a clause (``clause_id``), and a
domain file may name one (``clause: <contract>/<number>``). Clauses are registered by a document
controller and retired, never edited: a change is a new clause number or a retire and a new row.

STUB (P1-I5-T07f): the functions with a STEPS comment are for you to write. When they are
written, delete this paragraph, the STEPS comments and the `ruff: noqa` line at the top.
"""

from __future__ import annotations

import re
from typing import Literal

from pydantic import ConfigDict, Field, field_validator, model_validator
from tl_core.ledger import NewEvent
from tl_core.services.commands import Command, CommandResult
from tl_core.services.records import create_module_record
from tl_core.uow import UnitOfWork
from tl_mod_documents import registry as documents

from tl_mod_correspondence import registry
from tl_mod_correspondence.errors import ClauseNotFoundError, InvalidClauseError
from tl_mod_correspondence.handlers.common import append, correlated, require_project
from tl_mod_correspondence.handlers.models import non_blank
from tl_mod_correspondence.limits import (
    MAX_BODY,
    MAX_CONTACTS,
    MAX_DURATION_DAYS,
    MAX_NUMBER,
    MAX_REASON,
)
from tl_mod_correspondence.names import CLAUSE, CLAUSE_DEFINED, CLAUSE_RETIRED
from tl_mod_correspondence.textcheck import clean_body, clean_text

_PART = re.compile(r"[A-Za-z0-9_.()-]{1,64}")
_ROLE = re.compile(r"[a-z][a-z0-9_]{0,63}")
_DOMAIN_CODE = re.compile(r"[a-z][a-z0-9_]{0,31}")
ServiceMethod = Literal["email", "letter", "portal", "hand"]
DayType = Literal["calendar", "working"]


class DefineClause(Command):
    """Register a contract clause. The key is ``<contract>/<clause_number>``.

    ``time_bar_days`` and ``time_bar_day_type`` go together (both or neither).
    ``required_recipients`` are contact roles (lower-case words); ``domains`` are the domain codes
    that cite the clause. ``contract_document_id`` is the contract as a document of the register.
    """

    model_config = ConfigDict(extra="forbid")

    contract: str = Field(min_length=1, max_length=64)
    clause_number: str = Field(min_length=1, max_length=64)
    time_bar_days: int | None = Field(default=None, ge=1, le=MAX_DURATION_DAYS)
    time_bar_day_type: DayType | None = None
    notice_requirements: str | None = Field(default=None, max_length=MAX_BODY)
    required_recipients: list[str] = Field(default_factory=list, max_length=MAX_CONTACTS)
    service_method: ServiceMethod | None = None
    contract_document_id: str | None = Field(default=None, max_length=MAX_NUMBER)
    domains: list[str] = Field(default_factory=list, max_length=20)

    @field_validator("contract", "clause_number")
    @classmethod
    def _part(cls, value: str) -> str:
        if _PART.fullmatch(value) is None:
            raise ValueError("letters, digits and '_', '.', '(', ')', '-' only (at most 64)")
        return value

    @field_validator("notice_requirements")
    @classmethod
    def _notice(cls, value: str | None) -> str | None:
        return None if value is None else clean_body(value)

    @field_validator("required_recipients")
    @classmethod
    def _roles(cls, value: list[str]) -> list[str]:
        if len(set(value)) != len(value) or any(_ROLE.fullmatch(r) is None for r in value):
            raise ValueError("recipient roles are distinct lower-case words")
        return value

    @field_validator("domains")
    @classmethod
    def _domains(cls, value: list[str]) -> list[str]:
        if len(set(value)) != len(value) or any(_DOMAIN_CODE.fullmatch(d) is None for d in value):
            raise ValueError("domains are distinct domain codes")
        return value

    @model_validator(mode="after")
    def _bar(self) -> DefineClause:
        if (self.time_bar_days is None) != (self.time_bar_day_type is None):
            raise ValueError("give time_bar_days and time_bar_day_type together, or neither")
        return self


class RetireClause(Command):
    """Retire a clause. Clocks that cited it keep the reference."""

    model_config = ConfigDict(extra="forbid")

    clause_id: str = Field(max_length=MAX_NUMBER)
    reason: str = Field(max_length=MAX_REASON)

    @field_validator("reason")
    @classmethod
    def _reason(cls, value: str) -> str:
        return non_blank(value)


def handle_define_clause(uow: UnitOfWork, cmd: DefineClause) -> CommandResult:
    """Append ``Record.Created`` (key ``<contract>/<number>``) and ``ContractClause.Defined``.

    Raises ``CorrespondenceScopeError``, ``DuplicateKeyError`` (the clause exists in the scope)
    and ``InvalidClauseError`` (the contract document is not a document of the scope).
    """
    # STEPS
    # 1. `require_project(cmd)`; `cmd = correlated(cmd)`.
    # 2. When `cmd.contract_document_id is not None`: `found =
    #    documents.get_document(uow.conn(), cmd.contract_document_id)`; when `found is None or
    #    found.scope != cmd.scope` raise `InvalidClauseError(f"{cmd.contract_document_id!r} is
    #    not a document of {cmd.scope}")`.
    # 3. `key = f"{cmd.contract}/{cmd.clause_number}"`; `made = create_module_record(uow, cmd,
    #    record_type=CLAUSE, title=clean_text(f"{cmd.contract} clause {cmd.clause_number}"),
    #    key=key)` (a key already used raises `DuplicateKeyError` there).
    # 4. `done = append(uow, cmd, made.stream_id, CLAUSE, [NewEvent(event_type=CLAUSE_DEFINED,
    #    payload={...})], expected=made.version)` where the payload holds contract,
    #    clause_number, time_bar_days, time_bar_day_type, notice_requirements,
    #    required_recipients, service_method, contract_document_id and domains, each from the
    #    command field of the same name.
    # 5. Return `CommandResult(stream_id=made.stream_id, key=made.key, version=done.new_version,
    #    events=[*made.events, *done.events])`.
    raise NotImplementedError


def handle_retire_clause(uow: UnitOfWork, cmd: RetireClause) -> CommandResult:
    """Append ``ContractClause.Retired``.

    Raises ``ClauseNotFoundError`` and ``InvalidClauseError`` (already retired).
    """
    # STEPS
    # 1. `cmd = correlated(cmd)`; `clause = registry.get_clause(uow.conn(), cmd.clause_id)`.
    #    When `clause is None or clause.scope != cmd.scope` raise `ClauseNotFoundError(f"no
    #    clause {cmd.clause_id!r} in scope {cmd.scope!r}")`.
    # 2. When `not clause.is_active` raise `InvalidClauseError(f"clause
    #    {clause.contract}/{clause.clause_number} is retired")`.
    # 3. `done = append(uow, cmd, clause.id, CLAUSE, [NewEvent(event_type=CLAUSE_RETIRED,
    #    payload={"reason": cmd.reason})])`; return `CommandResult(stream_id=clause.id,
    #    key=f"{clause.contract}/{clause.clause_number}", version=done.new_version,
    #    events=list(done.events))`.
    raise NotImplementedError
```

`packages/tl-modules/correspondence/src/tl_mod_correspondence/handlers/common.py` (read-only; names and signatures):
```python
def require_project(cmd: Command) -> None:
    """"""
    ...
def correlated[C: Command](cmd: C) -> C:
    """``cmd`` with a correlation id, so every event of the command carries the same one."""
    ...
def now() -> datetime:
    """The current instant: the one place this module reads the clock (tests freeze it)."""
    ...
def today() -> str:
    """Today's date, ISO, from ``now``."""
    ...
def today_date() -> date:
    """"""
    ...
def check_date(value: str | None, what: str) -> str | None:
    """``value`` when it is an ISO calendar date (or ``None``); otherwise a ``ValueError``."""
    ...
def plausible_date(value: str | None, what: str) -> str | None:
    """``check_date``, and the day is at most a year ahead and 50 years back of today."""
    ...
def resolve_date(value: str | None, reason: str | None, what: str) -> tuple[str, str | None]:
    """``(date, reason)`` for an act's date: today by default, never in the future."""
    ...
def version_of(uow: UnitOfWork, record_id: str) -> int:
    """The stream version of a record now (the envelope row follows every module event)."""
    ...
def append(
    uow: UnitOfWork,
    cmd: Command,
    stream_id: str,
    stream_type: str,
    events: list[NewEvent],
    *,
    expected: int | None = None,
) -> AppendResult:
    """Append ``events`` to a stream at its current version (or ``expected``)."""
    ...
def transition(
    uow: UnitOfWork,
    cmd: Command,
    stream_id: str,
    name: str,
    *,
    reason: str | None = None,
    expected: int | None = None,
) -> CommandResult:
    """Run workflow transition ``name`` on a record of this module (at ``expected`` or now)."""
    ...
def load_item(uow: UnitOfWork, cmd: Command, item_id: str) -> registry.ItemRow:
    """The item, in the command's scope and readable by the viewer."""
    ...
def open_item(uow: UnitOfWork, cmd: Command, item_id: str) -> registry.ItemRow:
    """Like ``load_item``, and the item must still take changes (not void, closed or replaced)."""
    ...
def require_state(item: registry.ItemRow, *states: str) -> None:
    """Raise ``ItemStateError`` unless the item is in one of ``states``."""
    ...
def changes_of(old: dict[str, Any], new: dict[str, Any]) -> dict[str, list[Any]]:
    """``{field: [old, new]}`` for each field of ``new`` that differs."""
    ...
```

`packages/tl-modules/correspondence/src/tl_mod_correspondence/registry.py` (read-only; names and signatures):
```python
def get_party(conn: Connection, party_id: str) -> PartyRow | None:
    """"""
    ...
def list_parties(conn: Connection, scope: str, *, include_inactive: bool = False) -> list[PartyRow]:
    """"""
    ...
def contacts_of(
    conn: Connection, party_id: str, *, include_ended: bool = False
) -> list[ContactRow]:
    """"""
    ...
def get_clause(conn: Connection, clause_id: str) -> ClauseRow | None:
    """"""
    ...
def find_clause(
    conn: Connection, scope: str, contract: str, clause_number: str
) -> ClauseRow | None:
    """"""
    ...
```

## Context (read these, nothing else)
- `packages/tl-modules/correspondence/src/tl_mod_correspondence/handlers/common.py`
- `packages/tl-modules/correspondence/src/tl_mod_correspondence/registry.py`
- `packages/tl-modules/correspondence/src/tl_mod_correspondence/errors.py`
- `packages/tl-modules/correspondence/src/tl_mod_correspondence/names.py`
- `packages/tl-modules/correspondence/src/tl_mod_correspondence/testing.py`
- `docs/tickets/P1-I5/provided/t07f-test_registry_commands.py.txt`
- `docs/templates/haiku-report.md`
may explore: (none)

## Allowed paths
- `packages/tl-modules/correspondence/src/tl_mod_correspondence/handlers/parties.py`
- `packages/tl-modules/correspondence/src/tl_mod_correspondence/handlers/clauses.py`
- `packages/tl-modules/correspondence/tests/test_registry_commands.py (create: the provided test, byte for byte)`
- `docs/reports/P1-I5/P1-I5-T07f.md` (create: your report; commit it)

## Steps
1. Copy the provided test: `cp docs/tickets/P1-I5/provided/t07f-test_registry_commands.py.txt packages/tl-modules/correspondence/tests/test_registry_commands.py`. Do not edit the copy.
2. Implement the six handlers by their STEPS comments.
3. Delete the `STUB` paragraph of the module docstring, every `# STEPS` comment and the `# ruff: noqa` line at the top of each stub file you completed.
4. Run the acceptance commands, write the report, commit with `P1-I5-T07f: <imperative summary>`.

## Acceptance
```
just check
uv run pytest packages/tl-modules/correspondence/tests/test_registry_commands.py -q
TL_PG_URL=postgresql://postgres:postgres@localhost:5432/tl_test TL_REQUIRE_POSTGRES=1 uv run pytest packages/tl-modules/correspondence/tests/test_registry_commands.py -q --adapters sqlite,postgres
```
Expected: `just check` clean; 11 passed on SQLite; 22 passed with both adapters (every case runs once per adapter).

## Tests to add
- `packages/tl-modules/correspondence/tests/test_registry_commands.py` is provided; it is the whole test of this ticket. Add no other test file.

## Report requirements
Standard report (`docs/templates/haiku-report.md`), saved to `docs/reports/P1-I5/P1-I5-T07f.md` and committed. State the SQLite count and the both-adapters count you got, and say whether the `STUB` paragraphs, the STEPS comments and the `ruff: noqa` lines are gone.

## Escalation triggers
- A STEPS line contradicts the docstring of its function or the provided test.
- The provided test cannot pass without editing it, a file outside *Allowed paths*, or a pasted interface.
- Two attempts at the same failing test have not passed it.

## Blocked
(implementer writes here)

## Decision
(supervisor or orchestrator writes here)
