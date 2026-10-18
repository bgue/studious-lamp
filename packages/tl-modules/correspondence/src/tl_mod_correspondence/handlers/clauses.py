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
