"""Resolve extension types for the record services (brief 31; FANOUT D7).

``handle_create_record`` accepts ``record_type = "<ns>.<Name>"`` when the registry holds an active
version whose package still loads. These helpers answer "what is this type, and may it take
instances", so the record handlers, the pset guard and the body store ask one place.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from pydantic import BaseModel
from tl_schema.effective import EffectiveSchema
from tl_schema.validation import validate_psets

from tl_core.extypes import registry
from tl_core.extypes.errors import (
    BodyNotAllowedError,
    BodyRequiredError,
    TypeNotActiveError,
    UnknownTypeError,
)
from tl_core.extypes.forms import TypeForm, type_form
from tl_core.extypes.loader import LoadedType, Unavailable, default_loader
from tl_core.extypes.model import CompiledType
from tl_core.extypes.names import LayoutError, pset_name, split_type_name
from tl_core.extypes.types import (
    BodyPointer,
    StorageMode,
    TypeIssue,
    TypeRegistration,
    TypeStatus,
    TypeView,
)
from tl_core.schema_provider import get_provider
from tl_core.services.errors import (
    PsetValidationError,
    UnknownPsetError,
    UnsupportedRecordTypeError,
)
from tl_core.uow import UnitOfWork


@dataclass(frozen=True)
class ResolvedType:
    view: TypeView
    compiled: CompiledType

    @property
    def storage_mode(self) -> StorageMode:
        return self.view.registration.storage_mode

    @property
    def pset(self) -> str:
        return self.compiled.pset


def storage_mode_of(uow: UnitOfWork, type_name: str) -> StorageMode | None:
    """Storage mode of the registered type, from the registry rows only (no file is read).

    ``None`` for a name the registry does not know (``core.Record``, a typo). Versions of one type
    may differ in mode only by registering a different package; the newest wins.
    """
    view = registry.current_type(uow.conn(), type_name)
    return None if view is None else view.registration.storage_mode


def lookup_type(uow: UnitOfWork, type_name: str) -> ResolvedType | None:
    """The current version of ``type_name`` (active or deprecated) with its compiled class.

    ``None`` when the registry has no usable version. Raises ``TypeNotActiveError`` when it has
    one but the package files no longer match (the reason is in the message).
    """
    view = registry.current_type(uow.conn(), type_name)
    if view is None:
        return None
    loaded = default_loader().load(view.registration)
    if isinstance(loaded, Unavailable):
        raise TypeNotActiveError(
            f"{view.registration.type_ref} is registered but unavailable: {loaded.reason}"
        )
    assert isinstance(loaded, LoadedType)
    return ResolvedType(view, loaded.compiled)


def require_type(uow: UnitOfWork, type_name: str) -> ResolvedType:
    """Like ``lookup_type`` but an unknown name raises ``UnknownTypeError``."""
    found = lookup_type(uow, type_name)
    if found is None:
        raise UnknownTypeError(f"no extension type {type_name!r} is registered")
    return found


def require_active(uow: UnitOfWork, type_name: str) -> ResolvedType:
    """The type, which must take new instances: ``active``, with files that still match."""
    found = require_type(uow, type_name)
    if found.view.registration.status != "active":
        raise TypeNotActiveError(
            f"{found.view.registration.type_ref} is {found.view.registration.status}; "
            "no new instances can be created"
        )
    return found


class TypeDetail(BaseModel):
    """One registered type version for a reader: its row, why it was refused, its form."""

    registration: TypeRegistration
    seq: int
    form: TypeForm | None  # None for a quarantined version or one whose files are unavailable
    report: list[TypeIssue]  # the issues of a quarantine, or of a change refused under it
    unavailable: str | None  # why a usable version is left out of the schema


def type_detail(uow: UnitOfWork, type_ref: str) -> TypeDetail:
    """The registration ``type_ref`` with its form. Raises ``UnknownTypeError``."""
    from tl_core.extypes.registry import list_quarantined

    view = registry.get_type(uow.conn(), type_ref)
    if view is None:
        raise UnknownTypeError(f"no registration {type_ref!r}")
    registration = view.registration
    report: list[TypeIssue] = []
    for entry in list_quarantined(uow.conn()):
        if entry.type_ref == type_ref:
            report = entry.report
    form: TypeForm | None = None
    unavailable: str | None = None
    if registration.status in ("active", "deprecated"):
        loaded = default_loader().load(registration)
        if isinstance(loaded, Unavailable):
            unavailable = loaded.reason
        else:
            form = type_form(loaded.compiled)
    return TypeDetail(
        registration=registration, seq=view.seq, form=form, report=report, unavailable=unavailable
    )


class TypeSummary(BaseModel):
    """One registered version without its files or form (the list rows of the API and MCP)."""

    type_ref: str
    type_name: str
    namespace: str
    name: str
    version: str
    status: TypeStatus
    storage_mode: StorageMode
    index_fields: list[str]
    owner: str
    schema_hash: str
    content_hash: str
    seq: int


def summarise(view: TypeView) -> TypeSummary:
    """The list row of ``view``: its registration fields, ``type_name`` joined, and ``seq``."""
    r = view.registration
    return TypeSummary(
        type_ref=r.type_ref,
        type_name=f"{r.namespace}.{r.name}",
        namespace=r.namespace,
        name=r.name,
        version=r.version,
        status=r.status,
        storage_mode=r.storage_mode,
        index_fields=list(r.index_fields),
        owner=r.owner,
        schema_hash=r.schema_hash,
        content_hash=r.content_hash,
        seq=view.seq,
    )


class BodyView(BaseModel):
    """A verified body with the pointer it was verified against."""

    record_id: str
    pointer: BodyPointer
    body: dict[str, Any]


def psets_of(schema: EffectiveSchema, record_type: str) -> set[str]:
    """Names of the psets that apply to ``record_type`` in ``schema``."""
    return {pset.name for pset in schema.for_record_type(record_type)}


def prepare_create(
    uow: UnitOfWork,
    *,
    record_type: str,
    scope: str,
    psets: dict[str, Any],
    allow_object_backed: bool,
) -> ResolvedType:
    """Check a ``CreateRecord`` of an extension type and return the type it creates.

    The name must be a registered type (else ``UnsupportedRecordTypeError``, the error a type the
    platform does not know has always had), active (``TypeNotActiveError``) and, unless the caller
    is ``create_extension_record``, not object-backed (``BodyRequiredError``: its body is stored
    with it). Initial ``psets`` must be psets of the type and pass the structural checks of
    ``SetPsetValues``; range and value-list problems become conformance, as there.
    """
    from tl_core.services.psets import BLOCKING_KEYWORDS  # psets imports this module

    found = lookup_type(uow, record_type)
    if found is None:
        raise UnsupportedRecordTypeError(
            f"record type {record_type!r} is not supported: it is not core.Record "
            "and no extension type of that name is registered"
        )
    if found.view.registration.status != "active":
        raise TypeNotActiveError(
            f"{found.view.registration.type_ref} is {found.view.registration.status}; "
            "no new instances can be created"
        )
    if found.storage_mode == "object-backed" and not allow_object_backed:
        raise BodyRequiredError(
            f"{record_type} is object-backed: its body is stored with the record "
            "(create_extension_record, or the API's body route)"
        )
    if found.storage_mode == "object-backed" and psets:
        raise BodyNotAllowedError(
            f"{record_type} is object-backed: index fields come from the body, not from psets"
        )
    schema = get_provider().effective(scope)
    unknown = sorted(set(psets) - psets_of(schema, record_type))
    if unknown:
        raise UnknownPsetError(
            f"psets {', '.join(unknown)} do not apply to {record_type} in the effective schema"
        )
    blocking = [
        f"{issue.path}: {issue.message}"
        for issue in validate_psets(schema, record_type, psets)
        if issue.keyword in BLOCKING_KEYWORDS
    ]
    if blocking:
        raise PsetValidationError(f"initial values of {record_type} are invalid", blocking)
    return found


def refuse_index_write(uow: UnitOfWork, record_type: str, pset: str | None = None) -> None:
    """Refuse a direct write to the index fields of an object-backed record.

    Its index values are copies of its body; writing them directly would make the two disagree.
    ``pset`` ``None`` means "any pset write" (a whole-``psets`` update).
    """
    if record_type == "core.Record" or storage_mode_of(uow, record_type) != "object-backed":
        return
    try:
        namespace, name = split_type_name(record_type)
    except LayoutError:
        return
    if pset is None or pset == pset_name(namespace, name):
        raise BodyNotAllowedError(
            f"{record_type} is object-backed: its index fields are copied from the body; "
            "store a new body instead"
        )
