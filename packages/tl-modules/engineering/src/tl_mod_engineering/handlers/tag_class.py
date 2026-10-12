"""Tag class commands: define, revise and close (brief 9 M2; P1-I1-T07).

A tag class is a company record (``engineering.TagClass``) whose ``required_psets`` name the
property sets a tag of that class must carry. Each handler runs inside an entered unit of work,
appends through it and never commits. A failed check raises a ``ServiceError`` before anything is
appended, so nothing is written.
"""

from __future__ import annotations

from typing import Any, Literal, get_args

from pydantic import Field, field_validator
from tl_core.ledger import NewEvent
from tl_core.schema_provider import get_provider
from tl_core.services.commands import Command, CommandResult
from tl_core.services.errors import NoChangesError, UnknownPsetError, UnsupportedFieldError
from tl_core.services.records import create_module_record
from tl_core.uow import UnitOfWork
from tl_core.util import new_ulid

from tl_mod_engineering import registry
from tl_mod_engineering.document import ENTRY_CODE, PSET_NAME, TagFamily
from tl_mod_engineering.errors import (
    AlreadyClosedError,
    DuplicateTagClassError,
    InvalidTagClassError,
    RegistryScopeError,
    TagClassNotFoundError,
)
from tl_mod_engineering.limits import (
    MAX_DESCRIPTION,
    MAX_ITEMS,
    MAX_NUMBER,
    MAX_REASON,
    MAX_TEXT,
)
from tl_mod_engineering.names import (
    COMPANY,
    TAG_CLASS,
    TAG_CLASS_CLOSED,
    TAG_CLASS_DEFINED,
    TAG_CLASS_REVISED,
)

#: The fields ``ReviseTagClass.changes`` may carry.
REVISABLE = ("label", "family", "required_psets", "itr_templates", "mnemonics")
_LIST_FIELDS = ("required_psets", "itr_templates", "mnemonics")


class DefineTagClass(Command):
    """Create a tag class. ``scope`` must be ``company``."""

    code: str = Field(max_length=MAX_NUMBER)
    label: str = Field(min_length=1, max_length=MAX_TEXT)
    definition: str | None = Field(default=None, max_length=MAX_DESCRIPTION)
    family: TagFamily
    required_psets: list[str] = Field(default=[], max_length=MAX_ITEMS)
    itr_templates: list[str] = Field(default=[], max_length=MAX_ITEMS)
    mnemonics: list[str] = Field(default=[], max_length=MAX_ITEMS)
    edition: str = Field(min_length=1, max_length=MAX_NUMBER)

    @field_validator("code")
    @classmethod
    def _code(cls, value: str) -> str:
        if ENTRY_CODE.fullmatch(value) is None:
            raise ValueError(f"class code {value!r} may hold letters, digits and _ only")
        return value


class ReviseTagClass(Command):
    """Change fields of a tag class. ``changes`` maps a field in ``REVISABLE`` to its new value."""

    stream_id: str
    expected_version: int | None = None  # None: whatever version the class has now
    changes: dict[str, Any] = Field(max_length=len(REVISABLE))
    reason: str = Field(max_length=MAX_REASON)

    @field_validator("reason")
    @classmethod
    def _reason(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("reason must not be blank")
        return value


class CloseTagClass(Command):
    """End a tag class's life. Tags already of that class keep it."""

    stream_id: str
    expected_version: int | None = None
    lifecycle: Literal["superseded", "retired"] = "retired"
    superseded_by: str | None = None  # the replacing class; required for ``superseded``
    reason: str = Field(max_length=MAX_REASON)

    @field_validator("reason")
    @classmethod
    def _reason(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("reason must not be blank")
        return value


def _require_company(cmd: Command) -> None:
    if cmd.scope != COMPANY:
        raise RegistryScopeError(f"tag classes are company records; the scope is {cmd.scope!r}")


def _require_psets(names: list[str]) -> None:
    """Every name must be a pset of the company effective schema."""
    schema = get_provider().effective(COMPANY)
    for name in names:
        if PSET_NAME.fullmatch(name) is None or schema.find_pset(name) is None:
            raise UnknownPsetError(f"pset {name!r} is not in the company effective schema")


def _load_active(uow: UnitOfWork, cmd: Command, stream_id: str) -> registry.TagClassRow:
    row = registry.get_tag_class(uow.conn(), stream_id)
    if row is None or row.scope != cmd.scope:
        raise TagClassNotFoundError(f"no tag class {stream_id!r} in scope {cmd.scope!r}")
    if not row.active:
        raise AlreadyClosedError(f"tag class {row.code} is {row.lifecycle}")
    return row


def handle_define_tag_class(uow: UnitOfWork, cmd: DefineTagClass) -> CommandResult:
    """Append ``Record.Created`` and ``TagClass.Defined`` for a new class (key ``TC:<code>``).

    Raises ``RegistryScopeError`` (not company scope), ``UnknownPsetError`` (a required pset the
    company schema does not define) and ``DuplicateTagClassError`` (the code is taken, closed or
    not).
    """
    _require_company(cmd)
    _require_psets(cmd.required_psets)
    taken = registry.find_tag_classes(uow.conn(), COMPANY, code=cmd.code)
    if taken:
        raise DuplicateTagClassError(
            f"tag class {cmd.code!r} is already defined (lifecycle {taken[0].lifecycle})"
        )
    payload = {
        "code": cmd.code,
        "label": cmd.label,
        "family": cmd.family,
        "required_psets": cmd.required_psets,
        "itr_templates": cmd.itr_templates,
        "mnemonics": cmd.mnemonics,
        "edition": cmd.edition,
    }
    return create_module_record(
        uow,
        cmd,
        record_type=TAG_CLASS,
        title=cmd.label,
        description=cmd.definition,
        key=f"TC:{cmd.code}",
        extra_events=[NewEvent(event_type=TAG_CLASS_DEFINED, payload=payload)],
    )


def handle_revise_tag_class(uow: UnitOfWork, cmd: ReviseTagClass) -> CommandResult:
    """Append ``TagClass.Revised`` with the fields that differ, as ``{field: [old, new]}``.

    Raises ``TagClassNotFoundError``, ``AlreadyClosedError``, ``UnsupportedFieldError`` (a field
    outside ``REVISABLE``), ``InvalidTagClassError`` (a blank label, an unknown family, a list field
    that is not a list of strings), ``UnknownPsetError`` and ``NoChangesError`` (nothing differs).
    """
    row = _load_active(uow, cmd, cmd.stream_id)
    unsupported = sorted(set(cmd.changes) - set(REVISABLE))
    if unsupported:
        raise UnsupportedFieldError(
            f"fields {', '.join(unsupported)} cannot be revised; only {', '.join(REVISABLE)} can"
        )
    current: dict[str, Any] = {
        "label": row.label,
        "family": row.family,
        "required_psets": row.required_psets,
        "itr_templates": row.itr_templates,
        "mnemonics": row.mnemonics,
    }
    changes: dict[str, list[Any]] = {}
    for field, new in cmd.changes.items():
        _check_value(field, new)
        if new != current[field]:
            changes[field] = [current[field], new]
    if "required_psets" in changes:
        _require_psets(changes["required_psets"][1])
    if not changes:
        raise NoChangesError(f"no field of tag class {row.code} differs from the request")
    result = uow.append(
        stream_id=row.id,
        stream_type=TAG_CLASS,
        scope=cmd.scope,
        expected_version=(
            cmd.expected_version if cmd.expected_version is not None else row.version
        ),
        events=[
            NewEvent(
                event_type=TAG_CLASS_REVISED,
                payload={"changes": changes, "reason": cmd.reason},
            )
        ],
        actor=cmd.actor,
        source=cmd.source,
        correlation_id=cmd.correlation_id or new_ulid(),
        causation_id=cmd.causation_id,
    )
    return CommandResult(
        stream_id=row.id,
        key=row.key,
        version=result.new_version,
        events=result.events,
    )


def _check_value(field: str, value: Any) -> None:
    if field == "label":
        if not isinstance(value, str) or not value.strip():
            raise InvalidTagClassError("label must not be blank")
    elif field == "family":
        if value not in get_args(TagFamily):
            raise InvalidTagClassError(f"family must be one of {', '.join(get_args(TagFamily))}")
    elif field in _LIST_FIELDS:
        if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
            raise InvalidTagClassError(f"{field} must be a list of strings")


def handle_close_tag_class(uow: UnitOfWork, cmd: CloseTagClass) -> CommandResult:
    """Append ``TagClass.Closed``.

    Raises ``TagClassNotFoundError``, ``AlreadyClosedError`` and ``InvalidTagClassError`` (a
    ``superseded`` close without a replacing class that exists, or a ``retired`` close with one).
    """
    row = _load_active(uow, cmd, cmd.stream_id)
    if cmd.lifecycle == "superseded":
        successor = (
            None
            if cmd.superseded_by is None
            else registry.get_tag_class(uow.conn(), cmd.superseded_by)
        )
        if successor is None or successor.scope != cmd.scope or successor.id == row.id:
            raise InvalidTagClassError("a superseded class needs superseded_by: another tag class")
    elif cmd.superseded_by is not None:
        raise InvalidTagClassError("a retired class has no superseded_by")
    result = uow.append(
        stream_id=row.id,
        stream_type=TAG_CLASS,
        scope=cmd.scope,
        expected_version=(
            cmd.expected_version if cmd.expected_version is not None else row.version
        ),
        events=[
            NewEvent(
                event_type=TAG_CLASS_CLOSED,
                payload={
                    "lifecycle": cmd.lifecycle,
                    "superseded_by": cmd.superseded_by,
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
        stream_id=row.id,
        key=row.key,
        version=result.new_version,
        events=result.events,
    )
