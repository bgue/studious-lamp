"""Item library commands: ``DefineItem``, ``ReviseItem``, ``RetireItem`` and ``AdoptItem``.

The library is the company's (``scope`` is ``company``; the word is ``materials.library.edit``, held
by a company materials superuser, else an admin). Its record is ``materials.ItemMaster``, keyed by
the item ``code``. A project adopts an item with ``AdoptItem`` (a ``materials.ProjectItem`` keyed by
the same code, with copies of category, unit and consumable flag); ``ReviseItem`` makes the copies
follow in every project (the projector does it) and the unit cannot change once any copy exists.

Each ``check_*`` function is the rule of its command, run by the handler and by the load target's
plan, so the loader and the command share one check.
"""

from __future__ import annotations

from typing import Any

from pydantic import ConfigDict, Field, field_validator
from sqlalchemy import Connection
from tl_core.confidentiality import require_visible
from tl_core.ledger import NewEvent
from tl_core.services.commands import Command, CommandResult
from tl_core.services.errors import DuplicateKeyError
from tl_core.services.records import create_module_record
from tl_core.text import clean_optional_text, clean_text
from tl_core.uow import UnitOfWork

from tl_mod_materials.common import (
    append,
    check_one_of,
    correlated,
    require_company,
    require_project,
)
from tl_mod_materials.errors import (
    InvalidValueError,
    ItemAlreadyAdoptedError,
    ItemInUseError,
    ItemNotFoundError,
    ItemRetiredError,
    NoChangesError,
)
from tl_mod_materials.limits import (
    CODE_WORD,
    ITEM_CODE,
    MAX_ITEM_CODE,
    MAX_REASON,
    MAX_SPEC_TEXT,
    MAX_TITLE,
    STOCK_UOMS,
)
from tl_mod_materials.names import (
    ITEM_DEFINED,
    ITEM_MASTER,
    ITEM_RETIRED,
    ITEM_REVISED,
    PROJECT_ITEM,
    PROJECT_ITEM_DEFINED,
)
from tl_mod_materials.registry import (
    ItemRow,
    get_item,
    get_project_item,
    item_is_adopted,
    record_type_of_key,
)

#: The fields of the library item a revision may carry (the title is the envelope's).
REVISABLE = ("category", "base_uom", "size_text", "rating_text", "material_code", "consumable")


def valid_item_code(value: str) -> str:
    """``value`` when it is an item code (pydantic validators and the targets use it)."""
    if ITEM_CODE.fullmatch(value) is None:
        raise ValueError("code must be upper-case letters, digits, '.', '_' or '-', at most 40")
    return value


def _word(value: str) -> str:
    if CODE_WORD.fullmatch(value) is None:
        raise ValueError("a list value is letters, digits, '.', '_' or '-', at most 32")
    return value


class DefineItem(Command):
    """Define an item of the company library."""

    model_config = ConfigDict(extra="forbid")

    code: str = Field(min_length=1, max_length=MAX_ITEM_CODE)
    title: str = Field(min_length=1, max_length=MAX_TITLE)
    category: str = Field(min_length=1, max_length=32)
    base_uom: str = Field(min_length=1, max_length=8)
    size_text: str | None = Field(default=None, max_length=MAX_SPEC_TEXT)
    rating_text: str | None = Field(default=None, max_length=MAX_SPEC_TEXT)
    material_code: str | None = Field(default=None, max_length=32)
    consumable: bool = False

    @field_validator("code")
    @classmethod
    def _check_code(cls, value: str) -> str:
        return valid_item_code(value)

    @field_validator("title")
    @classmethod
    def _check_title(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("title must not be blank")
        return clean_text(value)

    @field_validator("category")
    @classmethod
    def _check_category(cls, value: str) -> str:
        return _word(value)

    @field_validator("material_code")
    @classmethod
    def _check_material(cls, value: str | None) -> str | None:
        return None if value is None else _word(value)

    @field_validator("size_text", "rating_text")
    @classmethod
    def _check_text(cls, value: str | None) -> str | None:
        return clean_optional_text(value)


class ReviseItem(Command):
    """Revise a library item; only the fields sent change (a field sent as null is cleared)."""

    model_config = ConfigDict(extra="forbid")

    code: str = Field(min_length=1, max_length=MAX_ITEM_CODE)
    title: str | None = Field(default=None, min_length=1, max_length=MAX_TITLE)
    category: str | None = Field(default=None, min_length=1, max_length=32)
    base_uom: str | None = Field(default=None, min_length=1, max_length=8)
    size_text: str | None = Field(default=None, max_length=MAX_SPEC_TEXT)
    rating_text: str | None = Field(default=None, max_length=MAX_SPEC_TEXT)
    material_code: str | None = Field(default=None, max_length=32)
    consumable: bool | None = None

    @field_validator("code")
    @classmethod
    def _check_code(cls, value: str) -> str:
        return valid_item_code(value)

    @field_validator("title", "size_text", "rating_text")
    @classmethod
    def _check_text(cls, value: str | None) -> str | None:
        return clean_optional_text(value)

    @field_validator("category", "material_code")
    @classmethod
    def _check_word(cls, value: str | None) -> str | None:
        return None if value is None else _word(value)


class RetireItem(Command):
    """Retire a library item; projects keep their copies."""

    model_config = ConfigDict(extra="forbid")

    code: str = Field(min_length=1, max_length=MAX_ITEM_CODE)
    reason: str = Field(min_length=1, max_length=MAX_REASON)

    @field_validator("code")
    @classmethod
    def _check_code(cls, value: str) -> str:
        return valid_item_code(value)

    @field_validator("reason")
    @classmethod
    def _check_reason(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("reason must not be blank")
        return clean_text(value)


class AdoptItem(Command):
    """Adopt a library item into the project."""

    model_config = ConfigDict(extra="forbid")

    item_code: str = Field(min_length=1, max_length=MAX_ITEM_CODE)

    @field_validator("item_code")
    @classmethod
    def _check_code(cls, value: str) -> str:
        return valid_item_code(value)


# --- the rules -----------------------------------------------------------------------------------


def check_define_item(conn: Connection, cmd: DefineItem) -> None:
    """Refuse an item the library cannot hold; the key must be free (``DuplicateKeyError``)."""
    check_one_of(cmd.base_uom, STOCK_UOMS, "base_uom")
    holder = record_type_of_key(conn, cmd.scope, cmd.code)
    if holder is not None:
        raise DuplicateKeyError("the item code is already used in the library")


def handle_define_item(uow: UnitOfWork, cmd: DefineItem) -> CommandResult:
    require_company(cmd)
    cmd = correlated(cmd)
    check_define_item(uow.conn(), cmd)
    return create_module_record(
        uow,
        cmd,
        record_type=ITEM_MASTER,
        title=cmd.title,
        key=cmd.code,
        extra_events=[
            NewEvent(
                event_type=ITEM_DEFINED,
                payload={
                    "code": cmd.code,
                    "category": cmd.category,
                    "base_uom": cmd.base_uom,
                    "size_text": cmd.size_text,
                    "rating_text": cmd.rating_text,
                    "material_code": cmd.material_code,
                    "consumable": cmd.consumable,
                },
            )
        ],
    )


def _live_item(conn: Connection, code: str) -> ItemRow:
    row = get_item(conn, code)
    if row is None:
        raise ItemNotFoundError(f"no item {code!r} in the library")
    require_visible(conn, row.id)
    return row


def handle_revise_item(uow: UnitOfWork, cmd: ReviseItem) -> CommandResult:
    """Change the fields sent. The project copies follow (projector). ``base_uom`` cannot change
    once any project item uses the item."""
    require_company(cmd)
    cmd = correlated(cmd)
    conn = uow.conn()
    row = _live_item(conn, cmd.code)
    if row.retired:
        raise ItemRetiredError(f"item {cmd.code!r} is retired")
    sent = cmd.model_fields_set
    for required in ("category", "base_uom", "consumable", "title"):
        if required in sent and getattr(cmd, required) is None:
            raise InvalidValueError(f"{required} cannot be cleared")
    changes: dict[str, Any] = {}
    for name in REVISABLE:
        if name in sent and getattr(cmd, name) != getattr(row, name):
            changes[name] = getattr(cmd, name)
    new_title = cmd.title if "title" in sent and cmd.title != row.title else None
    if "base_uom" in changes:
        check_one_of(changes["base_uom"], STOCK_UOMS, "base_uom")
        if item_is_adopted(conn, row.id):
            raise ItemInUseError(f"item {cmd.code!r} is used by a project; its unit cannot change")
    if not changes and new_title is None:
        raise NoChangesError(f"the revision changes nothing in item {cmd.code!r}")
    events: list[NewEvent] = []
    if new_title is not None:
        events.append(
            NewEvent(
                event_type="Record.Updated",
                payload={"changes": {"title": [row.title, new_title]}},
            )
        )
    if changes:
        events.append(NewEvent(event_type=ITEM_REVISED, payload=changes))
    result = append(uow, cmd, row.id, ITEM_MASTER, events)
    return CommandResult(
        stream_id=row.id, key=row.code, version=result.new_version, events=result.events
    )


def handle_retire_item(uow: UnitOfWork, cmd: RetireItem) -> CommandResult:
    require_company(cmd)
    cmd = correlated(cmd)
    row = _live_item(uow.conn(), cmd.code)
    if row.retired:
        raise ItemRetiredError(f"item {cmd.code!r} is already retired")
    result = append(
        uow,
        cmd,
        row.id,
        ITEM_MASTER,
        [NewEvent(event_type=ITEM_RETIRED, payload={"reason": cmd.reason})],
    )
    return CommandResult(
        stream_id=row.id, key=row.code, version=result.new_version, events=result.events
    )


def adopt_item(uow: UnitOfWork, cmd: Command, master: ItemRow) -> CommandResult:
    """Make the project's copy of ``master`` (the caller has checked the item is usable)."""
    return create_module_record(
        uow,
        cmd,
        record_type=PROJECT_ITEM,
        title=master.title,
        key=master.code,
        extra_events=[
            NewEvent(
                event_type=PROJECT_ITEM_DEFINED,
                payload={
                    "item_master_id": master.id,
                    "code": master.code,
                    "category": master.category,
                    "uom": master.base_uom,
                    "consumable": master.consumable,
                },
            )
        ],
    )


def check_adopt_item(conn: Connection, scope: str, item_code: str) -> ItemRow:
    """The library item a project may adopt: it exists, is not retired and is not yet adopted."""
    master = _live_item(conn, item_code)
    if master.retired:
        raise ItemRetiredError(f"item {item_code!r} is retired and cannot be adopted")
    if get_project_item(conn, scope, item_code) is not None:
        raise ItemAlreadyAdoptedError(f"item {item_code!r} is already adopted in {scope}")
    return master


def handle_adopt_item(uow: UnitOfWork, cmd: AdoptItem) -> CommandResult:
    require_project(cmd)
    cmd = correlated(cmd)
    master = check_adopt_item(uow.conn(), cmd.scope, cmd.item_code)
    return adopt_item(uow, cmd, master)
