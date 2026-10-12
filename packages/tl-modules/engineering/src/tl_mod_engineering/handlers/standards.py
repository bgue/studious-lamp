"""Registry commands: code lists, code values, mnemonics, numbering patterns (brief 6.4; P1-I1-T03).

Each handler runs inside an entered unit of work, appends through it and never commits. A failed
check raises a ``ServiceError`` before anything is appended, so nothing is written. Registry
entries live in ``company`` scope; only a code value may also be added in a project scope, by the
policy of its list (``tl_mod_engineering.codelists``). Entries are never rewritten: a new edition is
a new record and the old one is closed (``Standard.Closed``, ``CodeValue.Closed``).

STUB (P1-I1-T03): the six public ``handle_*`` bodies raise NotImplementedError; the command
models, the signatures, the docstrings and the helpers ``_register`` and ``_close`` are final. Each
body has a STEPS comment. Implement them, then delete this paragraph, the STEPS comments and the
``ruff: noqa`` line.
"""

# ruff: noqa: F401 -- STUB: these imports are used once the bodies are written

from __future__ import annotations

import re
from typing import Any, Literal

from pydantic import Field, field_validator
from tl_core.ledger import NewEvent
from tl_core.numbering.pattern import PatternError, parse_pattern
from tl_core.services.commands import Command, CommandResult
from tl_core.services.records import create_module_record
from tl_core.uow import UnitOfWork
from tl_core.util import new_ulid

from tl_mod_engineering import codelists, registry
from tl_mod_engineering.document import (
    DATE_PATTERN,
    ENTRY_CODE,
    LIST_CODE,
    MNEMONIC_CODE,
    RECORD_TYPE,
    VALUE_CODE,
    Adoption,
    PatternDef,
    SegmentDef,
    ValueListPolicy,
    pattern_problems,
)
from tl_mod_engineering.errors import (
    AlreadyClosedError,
    DuplicateStandardError,
    InvalidPatternError,
    InvalidSupersessionError,
    RegistryScopeError,
    StandardNotFoundError,
)
from tl_mod_engineering.names import (
    CODE_LIST,
    CODE_VALUE,
    CODE_VALUE_CLOSED,
    CODE_VALUE_DEFINED,
    COMPANY,
    MNEMONIC,
    NUMBERING_PATTERN,
    STANDARD_CLOSED,
    STANDARD_DEFINED,
)

#: ``co.acme.standards@1.0.0``: the name, an ``@`` and the version.
EDITION = re.compile(r"[a-z][a-z0-9.-]*@(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)")


def _iso_date(value: str | None) -> str | None:
    if value is not None and DATE_PATTERN.fullmatch(value) is None:
        raise ValueError(f"must be an ISO date (YYYY-MM-DD), got {value!r}")
    return value


class _Entry(Command):
    """The fields every registry entry has."""

    code: str
    label: str = Field(min_length=1)
    definition: str | None = None
    edition: str
    owner: str | None = None
    adoption: Adoption = "default"
    effective_from: str | None = None
    effective_to: str | None = None

    @field_validator("edition")
    @classmethod
    def _edition(cls, value: str) -> str:
        if EDITION.fullmatch(value) is None:
            raise ValueError(f"edition must look like 'co.acme.standards@1.0.0', got {value!r}")
        return value

    @field_validator("effective_from", "effective_to")
    @classmethod
    def _dates(cls, value: str | None) -> str | None:
        return _iso_date(value)


class RegisterCodeList(_Entry):
    """Create a code list. ``scope`` must be ``company``."""

    value_list_policy: ValueListPolicy = "closed"

    @field_validator("code")
    @classmethod
    def _code(cls, value: str) -> str:
        if LIST_CODE.fullmatch(value) is None:
            raise ValueError(f"code list name {value!r} must be UpperCamelCase")
        return value


class RegisterMnemonic(_Entry):
    """Create a mnemonic (a tag prefix). ``scope`` must be ``company``."""

    class_hint: str | None = None
    discipline: str | None = None

    @field_validator("code")
    @classmethod
    def _code(cls, value: str) -> str:
        if MNEMONIC_CODE.fullmatch(value) is None:
            raise ValueError(f"mnemonic {value!r} must be upper-case letters and digits")
        return value


class RegisterNumberingPattern(_Entry):
    """Create a numbering pattern. ``scope`` must be ``company``."""

    record_type: str
    template: str
    segments: dict[str, SegmentDef]
    allocate: bool = False
    gap_free: bool = True
    scope_selector: str = "project:*"
    reserved: list[tuple[int, int]] = []

    @field_validator("code")
    @classmethod
    def _code(cls, value: str) -> str:
        if ENTRY_CODE.fullmatch(value) is None:
            raise ValueError(f"pattern code {value!r} may hold letters, digits and _ only")
        return value

    @field_validator("record_type")
    @classmethod
    def _record_type(cls, value: str) -> str:
        if RECORD_TYPE.fullmatch(value) is None:
            raise ValueError(f"record type {value!r} must look like 'engineering.Tag'")
        return value


class AddCodeValue(Command):
    """Add a value to a code list in ``scope`` (``company`` or a project)."""

    code_list: str
    code: str
    label: str = Field(min_length=1)
    meaning: str | None = None
    crosswalk: str | None = None
    sort_order: int | None = None  # None: ten after the scope's last value of the list
    effective_from: str | None = None
    effective_to: str | None = None
    attributes: dict[str, Any] = {}
    edition: str | None = None  # None: the list's edition (company) or "project" (a project)

    @field_validator("code")
    @classmethod
    def _code(cls, value: str) -> str:
        if VALUE_CODE.fullmatch(value) is None:
            raise ValueError(f"value code {value!r} may hold letters, digits and ._- only")
        return value

    @field_validator("effective_from", "effective_to")
    @classmethod
    def _dates(cls, value: str | None) -> str | None:
        return _iso_date(value)


class _Close(Command):
    stream_id: str
    expected_version: int | None = None  # None: whatever version the entry has now
    lifecycle: Literal["superseded", "retired"] = "retired"
    superseded_by: str | None = None  # the replacing entry; required for ``superseded``
    effective_to: str | None = None
    reason: str

    @field_validator("reason")
    @classmethod
    def _reason(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("reason must not be blank")
        return value

    @field_validator("effective_to")
    @classmethod
    def _end(cls, value: str | None) -> str | None:
        return _iso_date(value)


class CloseStandard(_Close):
    """End the life of a code list, mnemonic or numbering pattern."""


class CloseCodeValue(_Close):
    """End the life of a code value (in ``company`` or a project scope)."""


def _version(edition: str) -> str:
    return edition.split("@", 1)[1]


def _require_company(cmd: Command, what: str) -> None:
    if cmd.scope != COMPANY:
        raise RegistryScopeError(f"{what} are company records; the scope is {cmd.scope!r}")


def _register(
    uow: UnitOfWork,
    cmd: _Entry,
    *,
    record_type: str,
    kind: str,
    prefix: str,
    what: str,
    value_list_policy: str | None = None,
    data: dict[str, Any] | None = None,
) -> CommandResult:
    """Shared body of the three ``handle_register_*``: checks, then one append."""
    _require_company(cmd, what)
    for other in registry.find_standards(uow.conn(), scope=COMPANY, kind=kind, code=cmd.code):
        if other.edition == cmd.edition:
            raise DuplicateStandardError(
                f"{kind} {cmd.code!r} is already registered in {cmd.edition}"
            )
    payload: dict[str, Any] = {
        "kind": kind,
        "code": cmd.code,
        "label": cmd.label,
        "definition": cmd.definition,
        "edition": cmd.edition,
        "owner": cmd.owner,
        "adoption": cmd.adoption,
        "value_list_policy": value_list_policy,
        "effective_from": cmd.effective_from,
        "effective_to": cmd.effective_to,
        "data": data or {},
    }
    return create_module_record(
        uow,
        cmd,
        record_type=record_type,
        title=cmd.label,
        description=cmd.definition,
        key=f"{prefix}:{cmd.code}@{_version(cmd.edition)}",
        extra_events=[NewEvent(event_type=STANDARD_DEFINED, payload=payload)],
    )


def handle_register_code_list(uow: UnitOfWork, cmd: RegisterCodeList) -> CommandResult:
    """Append the envelope and ``Standard.Defined``; kind ``code_list``, key ``CL:<code>@<v>``.

    Raises ``RegistryScopeError`` (not company scope) and ``DuplicateStandardError`` (the code is
    already registered in that edition).
    """
    # STEPS
    # return _register(uow, cmd, record_type=CODE_LIST, kind="code_list", prefix="CL",
    #     what="code lists", value_list_policy=cmd.value_list_policy).
    raise NotImplementedError


def handle_register_mnemonic(uow: UnitOfWork, cmd: RegisterMnemonic) -> CommandResult:
    """Append the envelope and ``Standard.Defined``; kind ``mnemonic``, key ``MN:<code>@<v>``.

    ``data`` is ``{"class_hint": ..., "discipline": ...}``. Raises ``RegistryScopeError`` and
    ``DuplicateStandardError``.
    """
    # STEPS
    # return _register(uow, cmd, record_type=MNEMONIC, kind="mnemonic", prefix="MN",
    #     what="mnemonics", data={"class_hint": cmd.class_hint, "discipline": cmd.discipline}).
    raise NotImplementedError


def handle_register_numbering_pattern(
    uow: UnitOfWork, cmd: RegisterNumberingPattern
) -> CommandResult:
    """Append the envelope and ``Standard.Defined`` (``numbering_pattern``), key ``NP:<code>@<v>``.

    ``data`` is ``{"record_type", "template", "segments", "allocate", "gap_free", "scope",
    "reserved"}`` with ``segments`` as ``{name: {"role", "list", "registry"}}``. Raises
    ``RegistryScopeError``, ``InvalidPatternError`` (the template does not parse, the segments do
    not match its fields, a segment names a code list that is not registered and active, or another
    active pattern already numbers this record type) and ``DuplicateStandardError``.
    """
    # STEPS
    # 1. _require_company(cmd, "numbering patterns").
    # 2. parse_pattern(cmd.template); a PatternError becomes
    #    InvalidPatternError(f"template {cmd.template!r}: {exc}") (raise ... from exc).
    # 3. lists = {row.code for row in registry.find_standards(uow.conn(), scope=COMPANY,
    #    kind="code_list", active_only=True)}.
    # 4. definition = PatternDef(code=cmd.code, label=cmd.label,
    #    definition=cmd.definition or cmd.label, record_type=cmd.record_type,
    #    template=cmd.template, segments=cmd.segments); problems = pattern_problems(definition,
    #    lists); if any: InvalidPatternError("; ".join(problems)).
    # 5. For every active numbering_pattern in COMPANY (find_standards with active_only=True): if
    #    its data["record_type"] equals cmd.record_type and its code differs from cmd.code, raise
    #    InvalidPatternError(f"{cmd.record_type} is already numbered by the active pattern "
    #    f"{other.code!r}").
    # 6. data = {"record_type": cmd.record_type, "template": cmd.template, "segments":
    #    {name: seg.model_dump() for name, seg in sorted(cmd.segments.items())}, "allocate":
    #    cmd.allocate, "gap_free": cmd.gap_free, "scope": cmd.scope_selector, "reserved":
    #    [list(pair) for pair in cmd.reserved]}.
    # 7. return _register(uow, cmd, record_type=NUMBERING_PATTERN, kind="numbering_pattern",
    #    prefix="NP", what="numbering patterns", data=data).
    raise NotImplementedError


def handle_add_code_value(uow: UnitOfWork, cmd: AddCodeValue) -> CommandResult:
    """Append ``Record.Created`` and ``CodeValue.Defined`` for a value of ``cmd.code_list``.

    The list's policy decides (``codelists.plan_new_value``): it raises ``UnknownCodeListError``,
    ``DuplicateCodeValueError``, ``ListClosedError``, ``CrosswalkRequiredError`` and
    ``InvalidCrosswalkError``. The key is ``CV:<list>.<code>@<version>`` in company scope (the
    version of the edition) and ``CV:<list>.<code>`` in a project scope.
    """
    # STEPS
    # 1. conn = uow.conn(); plan = codelists.plan_new_value(conn, scope=cmd.scope,
    #    name=cmd.code_list, code=cmd.code, crosswalk=cmd.crosswalk).
    # 2. In company scope: edition = cmd.edition or codelists.code_list(conn, cmd.code_list).edition
    #    and key = f"CV:{cmd.code_list}.{cmd.code}@{_version(edition)}". In a project scope:
    #    edition = cmd.edition or "project" and key = f"CV:{cmd.code_list}.{cmd.code}".
    # 3. order = cmd.sort_order if it is not None, else ten more than the largest sort_order of
    #    registry.code_values(conn, cmd.scope, cmd.code_list), or 10 when the scope has none.
    # 4. payload = {"code_list", "code", "label", "meaning", "crosswalk": plan.crosswalk,
    #    "origin": plan.origin, "sort_order": order, "effective_from", "effective_to",
    #    "attributes", "edition": edition} (the rest from cmd).
    # 5. return create_module_record(uow, cmd, record_type=CODE_VALUE, title=cmd.label, key=key,
    #    extra_events=[NewEvent(event_type=CODE_VALUE_DEFINED, payload=payload)]).
    raise NotImplementedError


def _close(
    uow: UnitOfWork,
    cmd: _Close,
    *,
    row_id: str,
    row_label: str,
    lifecycle_now: str,
    version: int,
    record_type: str,
    event_type: str,
    key: str | None,
    successor_ok: bool,
) -> CommandResult:
    if lifecycle_now != "active":
        raise AlreadyClosedError(f"{row_label} is {lifecycle_now}")
    if cmd.lifecycle == "superseded":
        if cmd.superseded_by is None or not successor_ok:
            raise InvalidSupersessionError(
                f"a superseded {row_label} needs superseded_by: another entry of the same kind"
            )
    elif cmd.superseded_by is not None:
        raise InvalidSupersessionError("a retired entry has no superseded_by")
    result = uow.append(
        stream_id=row_id,
        stream_type=record_type,
        scope=cmd.scope,
        expected_version=cmd.expected_version if cmd.expected_version is not None else version,
        events=[
            NewEvent(
                event_type=event_type,
                payload={
                    "lifecycle": cmd.lifecycle,
                    "superseded_by": cmd.superseded_by,
                    "effective_to": cmd.effective_to,
                    "reason": cmd.reason,
                },
            )
        ],
        actor=cmd.actor,
        source=cmd.source,
        correlation_id=cmd.correlation_id or new_ulid(),
        causation_id=cmd.causation_id,
    )
    return CommandResult(
        stream_id=row_id, key=key, version=result.new_version, events=result.events
    )


def handle_close_standard(uow: UnitOfWork, cmd: CloseStandard) -> CommandResult:
    """Append ``Standard.Closed``: superseded by another entry of the same kind, or retired.

    Raises ``StandardNotFoundError`` (no such entry in the scope), ``InvalidSupersessionError`` (a
    ``superseded`` close whose ``superseded_by`` is missing, unknown or of another kind; a
    ``retired`` close that names a replacement) and ``AlreadyClosedError``.
    """
    # STEPS
    # 1. row = registry.get_standard(uow.conn(), cmd.stream_id); if it is None or its scope is not
    #    cmd.scope: StandardNotFoundError(f"no registry entry {cmd.stream_id!r} in scope "
    #    f"{cmd.scope!r}").
    # 2. other = None if cmd.superseded_by is None else
    #    registry.get_standard(uow.conn(), cmd.superseded_by).
    # 3. return _close(uow, cmd, row_id=row.id, row_label=f"{row.kind} {row.code}",
    #    lifecycle_now=row.lifecycle, version=row.version, record_type=row.record_type,
    #    event_type=STANDARD_CLOSED, key=row.key, successor_ok=other is not None and
    #    other.kind == row.kind and other.id != row.id).
    raise NotImplementedError


def handle_close_code_value(uow: UnitOfWork, cmd: CloseCodeValue) -> CommandResult:
    """Append ``CodeValue.Closed``: superseded by another value of the same list, or retired.

    Raises as ``handle_close_standard`` does, with "same list" for "same kind".
    """
    # STEPS
    # 1. row = registry.get_code_value(uow.conn(), cmd.stream_id); if it is None or its scope is
    #    not cmd.scope: StandardNotFoundError(f"no code value {cmd.stream_id!r} in scope "
    #    f"{cmd.scope!r}").
    # 2. other = None if cmd.superseded_by is None else
    #    registry.get_code_value(uow.conn(), cmd.superseded_by).
    # 3. return _close(uow, cmd, row_id=row.id, row_label=f"value {row.code_list}.{row.code}",
    #    lifecycle_now=row.lifecycle, version=row.version, record_type=CODE_VALUE,
    #    event_type=CODE_VALUE_CLOSED, key=row.key, successor_ok=other is not None and
    #    other.code_list == row.code_list and other.id != row.id).
    raise NotImplementedError
