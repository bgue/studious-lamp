# pyright: basic
"""Compile a type package: ``type.yaml`` (LinkML) to a ``CompiledType``, a pset and a body schema.

The class of ``type.yaml`` is_a ``ExtensionRecord`` (``schema/core/extension.yaml``). Its own slots
are the body of an instance. A slot annotated ``tl:index: true`` is an index field. The compiler:

1. lints the file with the LinkML linter (errors only; the import ``throughline/core/extension``
   resolves to a private copy of ``schema/core`` in a temporary directory, so a package needs no
   path of the repository);
2. reads the class with ``SchemaView`` and maps each slot to a ``CompiledSlot``;
3. reads ``form.yaml`` hints;
4. turns the type into a ``PackageDoc`` of kind ``company`` with one pset named for the type, which
   is how an active registration enters the effective schema (``tl_core.extypes.provider``);
5. builds the JSON Schema a body validates against.

Every problem is a ``TypeIssue``; nothing here raises for a bad package.
"""

from __future__ import annotations

import re
import shutil
import tempfile
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any, cast

import yaml
from jsonschema import Draft202012Validator
from linkml.linter.linter import Linter
from linkml_runtime.utils.schemaview import SchemaView
from pydantic import ValidationError
from tl_schema.forms import EnumValue
from tl_schema.linkml_render import CORE_SCHEMA_DIR
from tl_schema.packages import (
    NAME_PATTERN,
    CodeList,
    CodeValue,
    CustomSectionDef,
    PackageDoc,
    PropertyDef,
    PsetDef,
    UnitDef,
)
from tl_schema.validation import DATE_PATTERN, DATETIME_PATTERN

from tl_core.extypes.model import CompiledSlot, CompiledType, FormHints, SlotKind
from tl_core.extypes.names import Coordinates
from tl_core.extypes.types import TypeIssue

TYPE_FILE = "type.yaml"
FORM_FILE = "form.yaml"
BASE_CLASS = "ExtensionRecord"
IMPORT_NAME = "throughline/core/extension"
MAX_SLOTS = 100
#: Longest slot pattern accepted. A cap, not a defence: a short pattern can still backtrack badly
#: (full ReDoS hardening is a follow-up).
MAX_PATTERN = 200
#: Slot names that would shadow an envelope field of the record.
RESERVED_SLOTS = frozenset(
    {
        "id",
        "key",
        "type",
        "scope",
        "title",
        "description",
        "status",
        "psets",
        "voided",
        "version",
        "last_seq",
        "effective_schema_hash",
        "conformance",
        "created_at",
        "updated_at",
        "body",
    }
)

_LINT_CONFIG: dict[str, Any] = {
    "rules": {
        "standard_naming": {"level": "error"},
        "no_invalid_slot_usage": {"level": "error"},
        "no_undeclared_ranges": {"level": "error"},
        "one_identifier_per_class": {"level": "error"},
        "no_xsd_int_type": {"level": "error"},
    }
}
_RANGES: dict[str, SlotKind] = {
    "string": "string",
    "str": "string",
    "uri": "string",
    "uriorcurie": "string",
    "ncname": "string",
    "integer": "int",
    "int": "int",
    "float": "decimal",
    "double": "decimal",
    "decimal": "decimal",
    "boolean": "bool",
    "bool": "bool",
    "date": "date",
    "datetime": "datetime",
}
_KIND_OVERRIDES = {"text": "text", "ref": "ref"}


ALLOWED_IMPORTS = frozenset({"linkml:types", IMPORT_NAME})
MAX_IMPORT_FILES = 10
_RELATIVE_IMPORT = re.compile(r"[A-Za-z0-9_][A-Za-z0-9_.-]*(?:/[A-Za-z0-9_][A-Za-z0-9_.-]*)*")


def _import_names(document: Any) -> list[Any]:
    imports: Any = (
        cast("dict[str, Any]", document).get("imports") if isinstance(document, dict) else None
    )
    return cast("list[Any]", imports) if isinstance(imports, list) else []


def check_imports(package: Path) -> tuple[list[str], list[TypeIssue]]:
    """The relative files ``type.yaml`` may import, and an issue for every other import.

    A package may import ``linkml:types``, ``throughline/core/extension`` and files of its own
    directory (``name`` stands for ``<package>/name.yaml``; no scheme, no absolute path, no ``..``,
    no link). Those files may import the same things and nothing else. Anything else would make the
    compiler fetch a URL or read a file the lock does not cover, so it is a ``layout`` issue.
    """
    issues: list[TypeIssue] = []
    files: list[str] = []
    pending: list[str] = [TYPE_FILE]
    seen: set[str] = set()
    base = package.resolve()
    while pending:
        current = pending.pop()
        if current in seen:
            continue
        seen.add(current)
        try:
            document: Any = yaml.safe_load((package / current).read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, yaml.YAMLError) as exc:
            issues.append(
                TypeIssue(kind="compile", path=current, detail=f"not readable YAML: {exc}")
            )
            continue
        for name in _import_names(document):
            if not isinstance(name, str):
                issues.append(
                    TypeIssue(kind="layout", path=current, detail=f"import {name!r} is not text")
                )
            elif name in ALLOWED_IMPORTS:
                continue
            elif (
                _RELATIVE_IMPORT.fullmatch(name) is None
                or ".." in name.split("/")
                or name.startswith("throughline/")
            ):
                detail = (
                    f"import {name!r} is not allowed: use linkml:types, {IMPORT_NAME}, "
                    "or a file of the package (a plain relative name)"
                )
                issues.append(TypeIssue(kind="layout", path=current, detail=detail))
            else:
                relative = f"{name}.yaml"
                target = package / relative
                try:
                    inside = target.resolve().is_relative_to(base)
                except OSError:
                    inside = False
                if target.is_symlink() or not target.is_file() or not inside:
                    detail = f"import {name!r}: {relative} is not a file of the package"
                    issues.append(TypeIssue(kind="layout", path=current, detail=detail))
                elif len(files) >= MAX_IMPORT_FILES:
                    detail = f"more than {MAX_IMPORT_FILES} imported files"
                    issues.append(TypeIssue(kind="layout", path=current, detail=detail))
                else:
                    files.append(relative)
                    pending.append(relative)
    return files, issues


@contextmanager
def _workspace(type_yaml: Path, extra: list[str] | None = None) -> Iterator[Path]:
    """A temporary directory holding a copy of ``type_yaml`` beside a copy of ``schema/core``.

    The package imports ``throughline/core/extension``; the copy puts that file where the import
    resolves, with its own imports next to it. ``extra`` are the package files ``check_imports``
    allowed, copied to the same relative paths.
    """
    with tempfile.TemporaryDirectory(prefix="tl-type-") as directory:
        root = Path(directory)
        core = root / "throughline" / "core"
        core.mkdir(parents=True)
        for source in sorted(CORE_SCHEMA_DIR.glob("*.yaml")):
            shutil.copy(source, core / source.name)
        copy = root / TYPE_FILE
        shutil.copy(type_yaml, copy)
        for relative in extra or []:
            target = root / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy(type_yaml.parent / relative, target)
        yield copy


def _truthy(value: Any) -> bool:
    return value is True or str(value).strip().lower() == "true"


def _annotation(element: Any, tag: str) -> Any:
    annotations = element.annotations
    if not annotations or tag not in annotations:
        return None
    return annotations[tag].value


def lint_issues(copy: Path) -> list[TypeIssue]:
    """Error-level LinkML lint problems of the (copied) ``type.yaml``."""
    issues: list[TypeIssue] = []
    for problem in Linter(_LINT_CONFIG).lint(str(copy)):
        if str(problem.level) == "error":
            issues.append(TypeIssue(kind="lint", path=TYPE_FILE, detail=problem.message))
    return issues


def _enum_values(view: Any, name: str) -> list[EnumValue]:
    enum: Any = view.get_enum(name)
    values: list[EnumValue] = []
    for code, value in enum.permissible_values.items():
        label = (value.title or value.description or str(code)).strip()
        values.append(EnumValue(code=str(code), label=label.split("\n")[0][:120]))
    return values


def _number(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _compile_slot(view: Any, class_name: str, slot_name: str) -> CompiledSlot | TypeIssue:
    slot: Any = view.induced_slot(slot_name, class_name)
    where = f"{TYPE_FILE}: slot {slot_name}"
    if NAME_PATTERN.fullmatch(slot_name) is None or "__" in slot_name:
        detail = f"{where}: the name must be lower snake case without a double underscore"
        return TypeIssue(kind="compile", path=TYPE_FILE, detail=detail)
    if slot_name in RESERVED_SLOTS:
        detail = f"{where}: the name is a field of the record envelope"
        return TypeIssue(kind="compile", path=TYPE_FILE, detail=detail)
    range_name = str(slot.range or "string")
    kind: SlotKind
    enum_name: str | None = None
    enum_values: list[EnumValue] | None = None
    if range_name in view.all_enums():
        kind = "enum"
        enum_name = range_name
        enum_values = _enum_values(view, range_name)
        if not enum_values:
            detail = f"{where}: enum {range_name} has no values"
            return TypeIssue(kind="compile", path=TYPE_FILE, detail=detail)
    elif range_name in _RANGES:
        kind = _RANGES[range_name]
    else:
        detail = (
            f"{where}: range {range_name!r} is not supported "
            "(use a LinkML type, an enum, or multivalued)"
        )
        return TypeIssue(kind="compile", path=TYPE_FILE, detail=detail)
    if slot.pattern is not None and len(str(slot.pattern)) > MAX_PATTERN:
        detail = f"{where}: the pattern is longer than {MAX_PATTERN} characters"
        return TypeIssue(kind="compile", path=TYPE_FILE, detail=detail)
    override = _annotation(slot, "tl:kind")
    if override is not None:
        if str(override) not in _KIND_OVERRIDES or kind != "string":
            detail = f"{where}: tl:kind {override!r} applies to string slots only (text or ref)"
            return TypeIssue(kind="compile", path=TYPE_FILE, detail=detail)
        kind = _KIND_OVERRIDES[str(override)]  # type: ignore[assignment]
    unit = slot.unit.ucum_code if slot.unit is not None else None
    title = slot.title or slot_name.replace("_", " ").capitalize()
    description = (slot.description or "").strip() or title
    return CompiledSlot(
        name=slot_name,
        label=title,
        description=description,
        kind=kind,
        required=bool(slot.required),
        multivalued=bool(slot.multivalued),
        indexed=_truthy(_annotation(slot, "tl:index")),
        unit=unit,
        minimum=_number(slot.minimum_value),
        maximum=_number(slot.maximum_value),
        pattern=slot.pattern,
        enum_name=enum_name,
        enum_values=enum_values,
    )


def compile_type(
    package: Path, coords: Coordinates, *, lint: bool = True
) -> tuple[CompiledType | None, list[TypeIssue]]:
    """Compile ``package/type.yaml`` for the type ``coords``; ``(None, issues)`` when it fails.

    A storage mode of ``directory-backed`` is a ``unsupported`` issue (FANOUT D11). ``lint=False``
    skips the LinkML linter: the registry lints once, when it validates, and reloading a
    registered package only needs the compiled form.
    """
    type_yaml = package / TYPE_FILE
    try:
        document: Any = yaml.safe_load(type_yaml.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, yaml.YAMLError) as exc:
        return None, [TypeIssue(kind="compile", path=TYPE_FILE, detail=f"not readable YAML: {exc}")]
    if not isinstance(document, dict):
        return None, [TypeIssue(kind="compile", path=TYPE_FILE, detail="not a YAML mapping")]
    names = _import_names(document)
    if IMPORT_NAME not in names:
        detail = f"imports must include {IMPORT_NAME!r}, which declares {BASE_CLASS}"
        return None, [TypeIssue(kind="compile", path=TYPE_FILE, detail=detail)]
    extra, import_issues = check_imports(package)
    if import_issues:
        return None, import_issues

    issues: list[TypeIssue] = []
    try:
        with _workspace(type_yaml, extra) as copy:
            if lint:
                issues = lint_issues(copy)
            view: Any = SchemaView(str(copy))
            return _compile(view, package, coords, issues)
    except Exception as exc:  # LinkML raises many kinds of error for a malformed schema
        if not issues:
            issues.append(TypeIssue(kind="compile", path=TYPE_FILE, detail=str(exc)[:500]))
        return None, issues


def _compile(
    view: Any, package: Path, coords: Coordinates, issues: list[TypeIssue]
) -> tuple[CompiledType | None, list[TypeIssue]]:
    classes: Any = view.all_classes()
    cls: Any = classes.get(coords.name)
    if cls is None:
        detail = f"the class {coords.name} named by the directory is not declared"
        return None, [*issues, TypeIssue(kind="compile", path=TYPE_FILE, detail=detail)]
    if BASE_CLASS not in view.class_ancestors(coords.name):
        detail = f"class {coords.name} must be is_a {BASE_CLASS}"
        return None, [*issues, TypeIssue(kind="compile", path=TYPE_FILE, detail=detail)]
    if cls.abstract:
        detail = f"class {coords.name} is abstract"
        return None, [*issues, TypeIssue(kind="compile", path=TYPE_FILE, detail=detail)]

    declared: Any = view.schema.version
    if declared and str(declared) != coords.version:
        detail = (
            f"version {declared} in type.yaml differs from the directory version {coords.version}"
        )
        issues.append(TypeIssue(kind="compile", path=TYPE_FILE, detail=detail))

    mode = str(_annotation(cls, "tl:storage_mode") or "managed")
    if mode == "directory-backed":
        detail = "directory-backed storage is not supported in v0 (managed or object-backed)"
        issues.append(TypeIssue(kind="unsupported", path=TYPE_FILE, detail=detail))
    elif mode not in ("managed", "object-backed"):
        detail = f"tl:storage_mode {mode!r} is not managed or object-backed"
        issues.append(TypeIssue(kind="compile", path=TYPE_FILE, detail=detail))

    names = [*cls.attributes, *[str(s) for s in cls.slots if s not in cls.attributes]]
    if not names:
        issues.append(TypeIssue(kind="compile", path=TYPE_FILE, detail="the class has no slots"))
    if len(names) > MAX_SLOTS:
        detail = f"the class has {len(names)} slots, more than {MAX_SLOTS}"
        issues.append(TypeIssue(kind="compile", path=TYPE_FILE, detail=detail))
    slots: list[CompiledSlot] = []
    for name in names[:MAX_SLOTS]:
        compiled = _compile_slot(view, coords.name, str(name))
        if isinstance(compiled, TypeIssue):
            issues.append(compiled)
        else:
            slots.append(compiled)

    form, form_issues = read_form(package, {slot.name for slot in slots})
    issues.extend(form_issues)
    if issues:
        return None, issues
    description = (cls.description or view.schema.description or coords.name).strip()
    return (
        CompiledType(
            namespace=coords.namespace,
            name=coords.name,
            version=coords.version,
            description=" ".join(description.split()),
            storage_mode=mode,  # type: ignore[arg-type]
            slots=slots,
            form=form,
        ),
        [],
    )


def read_form(package: Path, slot_names: set[str]) -> tuple[FormHints, list[TypeIssue]]:
    """``form.yaml`` hints (empty when the file is absent); every name must be a slot."""
    file = package / FORM_FILE
    if not file.is_file():
        return FormHints(), []
    try:
        data: Any = yaml.safe_load(file.read_text(encoding="utf-8")) or {}
        hints = FormHints.model_validate(data)
    except (OSError, UnicodeDecodeError, yaml.YAMLError) as exc:
        return FormHints(), [
            TypeIssue(kind="compile", path=FORM_FILE, detail=f"not readable: {exc}")
        ]
    except ValidationError as exc:
        detail = "; ".join(
            f"{'.'.join(str(p) for p in e['loc']) or '(document)'}: {e['msg']}"
            for e in exc.errors()
        )
        return FormHints(), [TypeIssue(kind="compile", path=FORM_FILE, detail=detail)]
    unknown = sorted({name for name in hints.names() if name not in slot_names})
    if unknown:
        detail = f"names no slot of type.yaml: {', '.join(unknown)}"
        return FormHints(), [TypeIssue(kind="compile", path=FORM_FILE, detail=detail)]
    return hints, []


# --- the effective schema -------------------------------------------------------------------------


def to_package_doc(compiled: CompiledType) -> PackageDoc:
    """The ``PackageDoc`` (kind ``company``) that puts this type into an effective schema.

    One pset, named for the type, applies to the type name. Managed types put every slot in it;
    object-backed types only the index fields (their bodies are validated by ``body_schema``).
    Adoption is ``mandatory``, so projects get the pset. Raises ``ValidationError`` if the type
    breaks a package rule (the validator turns that into a ``compile`` issue).
    """
    properties: dict[str, PropertyDef] = {}
    code_lists: dict[str, CodeList] = {}
    for slot in compiled.pset_slots():
        range_name = slot.pset_kind
        if slot.kind == "enum" and not slot.multivalued:
            assert slot.enum_name is not None and slot.enum_values is not None
            range_name = slot.enum_name
            code_lists.setdefault(
                slot.enum_name,
                CodeList(
                    description=f"Values of {slot.enum_name} in {compiled.type_name}.",
                    value_list_policy="closed",
                    values=[CodeValue(code=v.code, label=v.label) for v in slot.enum_values],
                ),
            )
        elif slot.multivalued:
            range_name = "json"
        properties[slot.name] = PropertyDef(
            label=slot.label,
            description=slot.description,
            range=range_name,
            unit=UnitDef(ucum=slot.unit)
            if slot.unit and range_name in ("int", "decimal")
            else None,
            required=slot.required,
            minimum=slot.minimum if range_name in ("int", "decimal") else None,
            maximum=slot.maximum if range_name in ("int", "decimal") else None,
            pattern=slot.pattern if range_name in ("string", "text", "ref") else None,
        )
    pset = PsetDef(
        label=compiled.name,
        description=compiled.description,
        applies_to=[compiled.type_name],
        enforcement="advisory",
        adoption="mandatory",
        custom_section=CustomSectionDef(allowed=False),
        properties=properties,
    )
    return PackageDoc(
        package=compiled.type_name,
        version=compiled.version,
        kind="company",
        title=compiled.name,
        description=compiled.description,
        code_lists=code_lists,
        psets={compiled.pset: pset},
    )


# --- body schema ----------------------------------------------------------------------------------


def _item_schema(slot: CompiledSlot) -> dict[str, Any]:
    out: dict[str, Any] = {}
    if slot.kind in ("string", "text", "ref"):
        out["type"] = "string"
        if slot.pattern is not None:
            out["pattern"] = slot.pattern
    elif slot.kind == "int":
        out["type"] = "integer"
    elif slot.kind == "decimal":
        out["type"] = "number"
    elif slot.kind == "bool":
        out["type"] = "boolean"
    elif slot.kind == "date":
        out.update(type="string", pattern=DATE_PATTERN)
    elif slot.kind == "datetime":
        out.update(type="string", pattern=DATETIME_PATTERN)
    elif slot.kind == "enum":
        out["type"] = "string"
        out["enum"] = [v.code for v in slot.enum_values or []]
    if slot.kind in ("int", "decimal"):
        if slot.minimum is not None:
            out["minimum"] = slot.minimum
        if slot.maximum is not None:
            out["maximum"] = slot.maximum
    return out


def body_schema(compiled: CompiledType) -> dict[str, Any]:
    """JSON Schema (draft 2020-12) a body of this type validates against: every slot, no extras."""
    properties: dict[str, Any] = {}
    for slot in compiled.slots:
        item = _item_schema(slot)
        schema = {"type": "array", "items": item} if slot.multivalued else item
        schema["title"] = slot.label
        schema["description"] = slot.description
        if slot.unit is not None:
            schema["x-unit"] = slot.unit
        properties[slot.name] = schema
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$id": f"urn:tl:type:{compiled.type_name}:{compiled.schema_hash()}",
        "title": compiled.type_name,
        "type": "object",
        "properties": properties,
        "required": [slot.name for slot in compiled.slots if slot.required],
        "additionalProperties": False,
    }


def body_issues(compiled: CompiledType, body: Any) -> list[str]:
    """Human-readable problems of ``body`` against the type, sorted; empty means valid."""
    validator = Draft202012Validator(body_schema(compiled))
    problems: set[str] = set()
    for error in validator.iter_errors(body):
        path = ".".join(str(part) for part in error.absolute_path) or "(body)"
        problems.add(f"{path}: {error.message}")
    return sorted(problems)
