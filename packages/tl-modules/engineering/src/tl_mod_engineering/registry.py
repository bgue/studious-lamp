"""Reading the engineering tables: registry entries, code values, tag classes and tags.

Every function takes a connection (``uow.conn()`` inside a unit of work, a read transaction
elsewhere) and returns frozen rows that join the module's table with the envelope in
``cur_core_record`` (``key``, ``version``, ``voided``, ``status``). Nothing here writes. JSON
columns come back as Python values on both adapters.

A voided record is never returned unless a function says so: the registry keeps a retired entry
(``lifecycle`` retired) for history, but a voided one was entered in error.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from sqlalchemy import Connection, text

from tl_mod_engineering.names import (
    CODE_VALUE_TABLE,
    STANDARD_TABLE,
    TAG_CLASS_TABLE,
    TAG_TABLE,
)


def _json(value: Any, default: Any) -> Any:
    """A JSON column as Python: text on SQLite and through the Postgres adapter."""
    if value is None:
        return default
    return json.loads(value) if isinstance(value, str) else value


@dataclass(frozen=True)
class StandardRow:
    id: str
    scope: str
    kind: str  # code_list | mnemonic | numbering_pattern
    code: str
    label: str
    definition: str | None
    edition: str
    owner: str | None
    adoption: str
    value_list_policy: str | None
    effective_from: str | None
    effective_to: str | None
    lifecycle: str
    superseded_by: str | None
    data: dict[str, Any]
    key: str | None
    version: int
    record_type: str

    @property
    def active(self) -> bool:
        return self.lifecycle == "active"


@dataclass(frozen=True)
class CodeValueRow:
    id: str
    scope: str
    code_list: str
    code: str
    label: str
    meaning: str | None
    crosswalk: str | None
    origin: str  # company | project
    sort_order: int
    effective_from: str | None
    effective_to: str | None
    lifecycle: str
    superseded_by: str | None
    attributes: dict[str, Any]
    edition: str
    key: str | None
    version: int

    @property
    def active(self) -> bool:
        return self.lifecycle == "active"


@dataclass(frozen=True)
class TagClassRow:
    id: str
    scope: str
    code: str
    label: str
    description: str | None
    family: str
    required_psets: list[str]
    itr_templates: list[str]
    mnemonics: list[str]
    lifecycle: str
    superseded_by: str | None
    edition: str
    key: str | None
    version: int

    @property
    def active(self) -> bool:
        return self.lifecycle == "active"


@dataclass(frozen=True)
class TagRow:
    id: str
    scope: str
    number: str
    class_code: str | None
    title: str
    status: str | None
    area: str | None
    mnemonic: str | None
    sequence: int | None
    segments: dict[str, str]
    pattern_code: str | None
    number_status: str  # ok | violation
    violations: list[dict[str, Any]]
    origin: str
    conformance: str
    version: int
    psets: dict[str, Any]


_STANDARD_SELECT = (
    "SELECT s.id, s.scope, s.kind, s.code, s.label, s.definition, s.edition, s.owner, s.adoption, "
    "s.value_list_policy, s.effective_from, s.effective_to, s.lifecycle, s.superseded_by, "
    "s.data_json, r.key, r.version, r.type "
    f"FROM {STANDARD_TABLE} s JOIN cur_core_record r ON r.id = s.id WHERE r.voided = :no"
)
_CODE_VALUE_SELECT = (
    "SELECT v.id, v.scope, v.code_list, v.code, v.label, v.meaning, v.crosswalk, v.origin, "
    "v.sort_order, v.effective_from, v.effective_to, v.lifecycle, v.superseded_by, "
    "v.attributes_json, v.edition, r.key, r.version "
    f"FROM {CODE_VALUE_TABLE} v JOIN cur_core_record r ON r.id = v.id WHERE r.voided = :no"
)
_TAG_CLASS_SELECT = (
    "SELECT c.id, c.scope, c.code, c.label, r.description, c.family, c.required_psets_json, "
    "c.itr_templates_json, c.mnemonics_json, c.lifecycle, c.superseded_by, c.edition, r.key, "
    "r.version "
    f"FROM {TAG_CLASS_TABLE} c JOIN cur_core_record r ON r.id = c.id WHERE r.voided = :no"
)
_TAG_SELECT = (
    "SELECT t.id, t.scope, t.number, t.class_code, r.title, r.status, t.area, t.mnemonic, "
    "t.sequence, t.segments_json, t.pattern_code, t.number_status, t.violations_json, t.origin, "
    "r.conformance, r.version, r.psets_json "
    f"FROM {TAG_TABLE} t JOIN cur_core_record r ON r.id = t.id WHERE r.voided = :no"
)


def _standard(row: Any) -> StandardRow:
    return StandardRow(
        id=row.id,
        scope=row.scope,
        kind=row.kind,
        code=row.code,
        label=row.label,
        definition=row.definition,
        edition=row.edition,
        owner=row.owner,
        adoption=row.adoption,
        value_list_policy=row.value_list_policy,
        effective_from=row.effective_from,
        effective_to=row.effective_to,
        lifecycle=row.lifecycle,
        superseded_by=row.superseded_by,
        data=_json(row.data_json, {}),
        key=row.key,
        version=int(row.version),
        record_type=row.type,
    )


def _code_value(row: Any) -> CodeValueRow:
    return CodeValueRow(
        id=row.id,
        scope=row.scope,
        code_list=row.code_list,
        code=row.code,
        label=row.label,
        meaning=row.meaning,
        crosswalk=row.crosswalk,
        origin=row.origin,
        sort_order=int(row.sort_order),
        effective_from=row.effective_from,
        effective_to=row.effective_to,
        lifecycle=row.lifecycle,
        superseded_by=row.superseded_by,
        attributes=_json(row.attributes_json, {}),
        edition=row.edition,
        key=row.key,
        version=int(row.version),
    )


def _tag_class(row: Any) -> TagClassRow:
    return TagClassRow(
        id=row.id,
        scope=row.scope,
        code=row.code,
        label=row.label,
        description=row.description,
        family=row.family,
        required_psets=_json(row.required_psets_json, []),
        itr_templates=_json(row.itr_templates_json, []),
        mnemonics=_json(row.mnemonics_json, []),
        lifecycle=row.lifecycle,
        superseded_by=row.superseded_by,
        edition=row.edition,
        key=row.key,
        version=int(row.version),
    )


def _tag(row: Any) -> TagRow:
    return TagRow(
        id=row.id,
        scope=row.scope,
        number=row.number,
        class_code=row.class_code,
        title=row.title,
        status=row.status,
        area=row.area,
        mnemonic=row.mnemonic,
        sequence=None if row.sequence is None else int(row.sequence),
        segments=_json(row.segments_json, {}),
        pattern_code=row.pattern_code,
        number_status=row.number_status,
        violations=_json(row.violations_json, []),
        origin=row.origin,
        conformance=row.conformance,
        version=int(row.version),
        psets=_json(row.psets_json, {}),
    )


# --- standards -----------------------------------------------------------------------------------


def get_standard(conn: Connection, stream_id: str) -> StandardRow | None:
    row = conn.execute(text(_STANDARD_SELECT + " AND s.id = :id"), {"no": False, "id": stream_id})
    found = row.first()
    return None if found is None else _standard(found)


def find_standards(
    conn: Connection,
    *,
    scope: str,
    kind: str,
    code: str | None = None,
    active_only: bool = False,
) -> list[StandardRow]:
    """Entries of ``kind`` in ``scope`` (and ``code``), by code then edition (newest last)."""
    sql = _STANDARD_SELECT + " AND s.scope = :scope AND s.kind = :kind"
    params: dict[str, Any] = {"no": False, "scope": scope, "kind": kind}
    if code is not None:
        sql += " AND s.code = :code"
        params["code"] = code
    if active_only:
        sql += " AND s.lifecycle = 'active'"
    sql += " ORDER BY s.code, s.edition"
    return [_standard(r) for r in conn.execute(text(sql), params)]


def active_standard(conn: Connection, scope: str, kind: str, code: str) -> StandardRow | None:
    """The entry that is in force: the active one of the newest edition, or ``None``."""
    found = find_standards(conn, scope=scope, kind=kind, code=code, active_only=True)
    return found[-1] if found else None


# --- code values ---------------------------------------------------------------------------------


def get_code_value(conn: Connection, stream_id: str) -> CodeValueRow | None:
    row = conn.execute(text(_CODE_VALUE_SELECT + " AND v.id = :id"), {"no": False, "id": stream_id})
    found = row.first()
    return None if found is None else _code_value(found)


def find_code_value(conn: Connection, scope: str, code_list: str, code: str) -> CodeValueRow | None:
    """The value ``code`` of ``code_list`` that ``scope`` itself defined (any lifecycle)."""
    sql = _CODE_VALUE_SELECT + " AND v.scope = :scope AND v.code_list = :list AND v.code = :code"
    row = conn.execute(
        text(sql), {"no": False, "scope": scope, "list": code_list, "code": code}
    ).first()
    return None if row is None else _code_value(row)


def code_values(
    conn: Connection, scope: str, code_list: str, *, active_only: bool = False
) -> list[CodeValueRow]:
    """The values ``scope`` itself defined for ``code_list``, in list order."""
    sql = _CODE_VALUE_SELECT + " AND v.scope = :scope AND v.code_list = :list"
    if active_only:
        sql += " AND v.lifecycle = 'active'"
    sql += " ORDER BY v.sort_order, v.code"
    params = {"no": False, "scope": scope, "list": code_list}
    return [_code_value(r) for r in conn.execute(text(sql), params)]


# --- tag classes ---------------------------------------------------------------------------------


def get_tag_class(conn: Connection, stream_id: str) -> TagClassRow | None:
    row = conn.execute(text(_TAG_CLASS_SELECT + " AND c.id = :id"), {"no": False, "id": stream_id})
    found = row.first()
    return None if found is None else _tag_class(found)


def find_tag_classes(
    conn: Connection, scope: str, *, code: str | None = None, active_only: bool = False
) -> list[TagClassRow]:
    sql = _TAG_CLASS_SELECT + " AND c.scope = :scope"
    params: dict[str, Any] = {"no": False, "scope": scope}
    if code is not None:
        sql += " AND c.code = :code"
        params["code"] = code
    if active_only:
        sql += " AND c.lifecycle = 'active'"
    sql += " ORDER BY c.code, c.edition"
    return [_tag_class(r) for r in conn.execute(text(sql), params)]


def active_tag_class(conn: Connection, scope: str, code: str) -> TagClassRow | None:
    """The class in force: the active one of the newest edition, or ``None``."""
    found = find_tag_classes(conn, scope, code=code, active_only=True)
    return found[-1] if found else None


# --- tags ----------------------------------------------------------------------------------------


def get_tag(conn: Connection, stream_id: str) -> TagRow | None:
    row = conn.execute(text(_TAG_SELECT + " AND t.id = :id"), {"no": False, "id": stream_id})
    found = row.first()
    return None if found is None else _tag(found)


def find_tag(conn: Connection, scope: str, number: str) -> TagRow | None:
    sql = _TAG_SELECT + " AND t.scope = :scope AND t.number = :number"
    found = conn.execute(text(sql), {"no": False, "scope": scope, "number": number}).first()
    return None if found is None else _tag(found)
