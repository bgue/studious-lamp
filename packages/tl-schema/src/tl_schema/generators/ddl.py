# pyright: basic
"""Current-state DDL generator: a LinkML class becomes ``cur_<module>_<class>`` per SQL dialect.

Rules (brief 5.4, build spec 03 section 9):

* A class gets a table only when it carries the annotation ``tl:current_state: true``.
* The table is named ``cur_<module>_<class in snake_case>``; ``<module>`` is the ``tl:module``
  annotation of the schema file that defines the class. The annotation ``tl:table`` on the class
  overrides the whole name (for example ``cur_pset_values``).
* Columns are the class's induced slots in LinkML order. A slot's column is its name, or
  ``<name>_json`` when it is annotated ``tl:json: true``, or the value of ``tl:column`` if present.
* The type comes from ``ddl_types.column_type`` after resolving the slot range: a custom type to
  its root LinkML type, an enum to ``enum``, a ``tl:json`` slot to the dialect's JSON type. Any
  other range raises ``DdlError``.
* Postgres ``TEXT`` columns are ``COLLATE "C"`` so text orders bytewise like SQLite
  (``ddl_types.collated``).
* The identifier slot is ``PRIMARY KEY``; other required slots are ``NOT NULL``.
* ``DEFAULT`` comes from ``ifabsent`` (``string(x)``, ``int(n)``, ``float(x)``, ``true``/``false``).
  A required JSON slot without ``ifabsent`` defaults to ``'{}'``.
* Each entry of the class's ``unique_keys`` becomes ``CREATE UNIQUE INDEX ux_<table>_<key name>``;
  each slot annotated ``tl:indexed: true`` becomes ``CREATE INDEX ix_<table>_<column>``.
* Each class annotation ``tl:ix_<name>: "<terms>"`` becomes ``CREATE INDEX ix_<table>_<name>`` over
  the comma-separated terms: a slot name (its column), a slot name followed by ``desc``, or
  ``empty_last(<slot>)``, the expression ``(col IS NULL OR col = '')`` that the record queries
  order by first so empty values sort last (``tl_core.query.compiler``); an index on that exact
  expression lets the planner read a sorted page instead of sorting the table. Both dialects
  accept the same text.
* Every statement is ``IF NOT EXISTS`` so applying the DDL twice is harmless. Statements end with
  ``;`` and are separated by one blank line. Output is deterministic.
"""

from __future__ import annotations

import re
from contextlib import chdir
from pathlib import Path
from typing import Any, cast

from linkml_runtime.utils.schemaview import SchemaView

from tl_schema.generators.ddl_types import Dialect, collated, column_type, sql_literal

ROOT_SCHEMA = "core.yaml"
DIALECTS: tuple[Dialect, ...] = ("sqlite", "postgres")


class DdlError(ValueError):
    """The LinkML class cannot be expressed as a current-state table."""


def _annotation(element: Any, tag: str) -> Any:
    annotations = element.annotations
    if not annotations:
        return None
    try:
        return annotations[tag].value
    except KeyError:
        return None


def snake_case(name: str) -> str:
    """``TestPackage`` becomes ``test_package``; ``Weld`` becomes ``weld``."""
    return re.sub(r"(?<=[a-z0-9])(?=[A-Z])", "_", name).lower()


def _module_of(view: SchemaView, class_name: str) -> str:
    definition = view.get_class(class_name)
    if definition is None:
        raise DdlError(f"unknown class {class_name}")
    source = definition.from_schema
    for schema in (view.schema_map or {}).values():
        if schema.id == source:
            module = _annotation(schema, "tl:module")
            if module:
                return str(module)
    raise DdlError(f"class {class_name}: its schema has no tl:module annotation")


def table_name(view: SchemaView, class_name: str) -> str:
    override = _annotation(view.get_class(class_name), "tl:table")
    if override:
        return str(override)
    return f"cur_{_module_of(view, class_name)}_{snake_case(class_name)}"


def _root_type(view: SchemaView, slot: Any) -> str:
    """The LinkML built-in type name (or ``enum``) for a slot's range."""
    rng = slot.range
    if rng in view.all_enums():
        return "enum"
    if rng in view.all_types():
        return str(view.type_ancestors(rng)[-1]).lower()
    raise DdlError(
        f"slot {slot.name}: range {rng} is not a type or enum "
        "(annotate it tl:json or extend the generator)"
    )


def _default(linkml_type: str, slot: Any, is_json: bool, dialect: Dialect) -> str | None:
    raw = slot.ifabsent
    if raw is None:
        return sql_literal("string", {}, dialect, json=True) if is_json and slot.required else None
    text = str(raw).strip()
    match = re.fullmatch(r"(string|int|float)\((.*)\)", text)
    value: object
    if match:
        kind, body = match.groups()
        value = {"string": str, "int": int, "float": float}[kind](body)
    elif text.lower() in ("true", "false"):
        value = text.lower() == "true"
    else:
        raise DdlError(f"slot {slot.name}: unsupported ifabsent {raw!r}")
    return sql_literal(linkml_type, value, dialect)


def _column(view: SchemaView, slot: Any, dialect: Dialect) -> tuple[str, str]:
    """Return (column name, column definition)."""
    if slot.multivalued:
        raise DdlError(f"slot {slot.name}: multivalued slots are not supported yet")
    is_json = bool(_annotation(slot, "tl:json"))
    name = _annotation(slot, "tl:column") or (f"{slot.name}_json" if is_json else slot.name)
    linkml_type = "string" if is_json else _root_type(view, slot)
    parts = [str(name), collated(column_type(linkml_type, dialect, json=is_json), dialect)]
    if slot.identifier:
        parts.append("PRIMARY KEY")
    elif slot.required:
        parts.append("NOT NULL")
    default = _default(linkml_type, slot, is_json, dialect)
    if default is not None:
        parts.append(f"DEFAULT {default}")
    return str(name), " ".join(parts)


INDEX_TAG = "tl:ix_"
_INDEX_NAME = re.compile(r"[a-z][a-z0-9_]*")
_INDEX_TERM = re.compile(r"(?:empty_last\((?P<fn>\w+)\))|(?:(?P<col>\w+)(?: (?P<dir>asc|desc))?)")


def _class_indexes(view: SchemaView, class_name: str) -> dict[str, str]:
    """``{index name: terms}`` from the ``tl:ix_<name>`` annotations of the class and parents."""
    found: dict[str, str] = {}
    for ancestor in reversed(view.class_ancestors(class_name)):
        definition = cast(Any, view.get_class(ancestor))
        annotations = cast(dict[str, Any], definition.annotations or {})
        for tag, annotation in annotations.items():
            if str(tag).startswith(INDEX_TAG):
                found[str(tag)[len(INDEX_TAG) :]] = str(annotation.value)
    return found


def _index_terms(
    spec: str, slots: dict[str, Any], columns: dict[str, tuple[str, str]], view: SchemaView
) -> str:
    terms: list[str] = []
    for raw in spec.split(","):
        match = _INDEX_TERM.fullmatch(raw.strip())
        if match is None:
            raise DdlError(f"index term {raw.strip()!r} is not a slot, 'slot desc' or empty_last()")
        slot_name = match.group("fn") or match.group("col")
        if slot_name not in columns:
            raise DdlError(f"index term {raw.strip()!r}: no slot {slot_name!r} in the class")
        column = columns[slot_name][0]
        if match.group("fn"):
            slot = slots[slot_name]
            if _annotation(slot, "tl:json") or _root_type(view, slot) != "string":
                raise DdlError(f"empty_last({slot_name}): only a plain text column has '' values")
            terms.append(f"({column} IS NULL OR {column} = '')")
        else:
            terms.append(column + (f" {match.group('dir').upper()}" if match.group("dir") else ""))
    return ", ".join(terms)


def table_ddl(view: SchemaView, class_name: str, dialect: Dialect) -> str:
    """The full DDL (table, unique indexes, plain indexes) for one class and dialect."""
    table = table_name(view, class_name)
    slots = view.class_induced_slots(class_name)
    columns = {slot.name: _column(view, slot, dialect) for slot in slots}
    lines = [f"  {definition}" for _, definition in columns.values()]
    statements = [f"CREATE TABLE IF NOT EXISTS {table} (\n" + ",\n".join(lines) + "\n);"]
    unique: dict[str, Any] = {}
    for ancestor in reversed(view.class_ancestors(class_name)):
        found = cast(dict[str, Any], getattr(view.get_class(ancestor), "unique_keys", None) or {})
        unique.update(found)
    for key_name in sorted(unique):
        cols = ", ".join(columns[s][0] for s in unique[key_name].unique_key_slots)
        statements.append(
            f"CREATE UNIQUE INDEX IF NOT EXISTS ux_{table}_{key_name} ON {table} ({cols});"
        )
    for slot in slots:
        if _annotation(slot, "tl:indexed"):
            col = columns[slot.name][0]
            statements.append(f"CREATE INDEX IF NOT EXISTS ix_{table}_{col} ON {table} ({col});")
    by_name = {slot.name: slot for slot in slots}
    for index_name, spec in sorted(_class_indexes(view, class_name).items()):
        if _INDEX_NAME.fullmatch(index_name) is None:
            raise DdlError(f"index name {index_name!r}: use lower-case letters, digits, _")
        terms = _index_terms(spec, by_name, columns, view)
        statements.append(
            f"CREATE INDEX IF NOT EXISTS ix_{table}_{index_name} ON {table} ({terms});"
        )
    return "\n\n".join(statements) + "\n"


def current_state_classes(view: SchemaView) -> list[str]:
    return sorted(
        c for c in view.all_classes() if _annotation(view.get_class(c), "tl:current_state")
    )


def generate_from(schema_path: Path) -> dict[str, str]:
    """``{"ddl/<dialect>/<table>.sql": text}`` for each current-state class in the schema."""
    view = SchemaView(str(schema_path))
    files: dict[str, str] = {}
    for class_name in current_state_classes(view):
        table = table_name(view, class_name)
        for dialect in DIALECTS:
            files[f"ddl/{dialect}/{table}.sql"] = table_ddl(view, class_name, dialect)
    return files


def generate(schema_dir: Path) -> dict[str, str]:
    """Entry point used by ``tl_schema.generate``; runs inside ``schema_dir``."""
    with chdir(schema_dir):
        return generate_from(Path(ROOT_SCHEMA))
