# pyright: basic
"""Offline classes: ``generated/offline_classes.py`` and ``generated/docs/offline-classes.md``.

Every record type declares ``tl:offline: full | draft_only | none``, resolved exactly as
``type_labels.py`` resolves record types: ``tl:record_types`` on a module class, the subclass named
after the type for a multi-type class such as ``Standard``, and ``core.Record``. A core stream that
is not a record carries the class with ``tl:stream_type: core.ActivityPost`` on its payload or state
class. A missing tag, a value outside the vocabulary, a tag on a class that is neither, or two
classes giving one type different values raises ``OfflineClassError`` naming the class. Nothing
enforces the class yet (OC-S2). Output is sorted and deterministic, and drift-checked.
"""

from __future__ import annotations

import json
from contextlib import chdir
from pathlib import Path
from typing import Any

from linkml_runtime.utils.schemaview import SchemaView

from tl_schema.generators import type_labels
from tl_schema.generators.ddl import _module_of  # pyright: ignore[reportPrivateUsage]
from tl_schema.generators.type_labels import (
    _annotation,  # pyright: ignore[reportPrivateUsage]
)
from tl_schema.modules import module_roots

ROOT_SCHEMA = "core.yaml"
OUTPUT = "offline_classes.py"
DOC_OUTPUT = "docs/offline-classes.md"
CORE_TYPE = "Record"
VALUES = ("full", "draft_only", "none")
MEANINGS = {
    "full": "Created and edited offline, merged on sync.",
    "draft_only": "Drafts offline; issue, number and sign happen on the authority.",
    "none": "Online only.",
}

HEADER = '''"""Offline class of every record type and core stream. Do not edit by hand."""

from __future__ import annotations

from typing import Final, Literal

OfflineClass = Literal["full", "draft_only", "none"]

'''


class OfflineClassError(ValueError):
    """A record type or stream has no valid, consistent ``tl:offline`` class."""


def _value(definition: Any, class_name: str, subject: str) -> str | None:
    raw = _annotation(definition, "tl:offline")
    if raw is None:
        return None
    value = raw.strip()
    if value not in VALUES:
        raise OfflineClassError(
            f"{subject}: class {class_name} has tl:offline {raw!r}, "
            f"expected one of {', '.join(VALUES)}"
        )
    return value


def _agree(subject: str, declared: dict[str, str]) -> str:
    """The one class value of ``subject`` from the classes that declare it."""
    if len(set(declared.values())) > 1:
        detail = ", ".join(f"{name}={value}" for name, value in sorted(declared.items()))
        raise OfflineClassError(f"{subject}: classes disagree on tl:offline ({detail})")
    return next(iter(declared.values()))


def _record_value(
    view: SchemaView, module: str, class_name: str, record_type: str, used: set[str]
) -> str:
    own = record_type.removeprefix(f"{module}.")
    source = class_name if record_type == f"{module}.{class_name}" else own
    definition = view.get_class(source)
    if definition is None:
        raise OfflineClassError(f"record type {record_type}: class {source} not found")
    used.add(source)
    declared: dict[str, str] = {}
    own_value = _value(definition, source, f"record type {record_type}")
    if own_value is not None:
        declared[source] = own_value
    if source != class_name:
        used.add(class_name)
        parent = _value(view.get_class(class_name), class_name, f"record type {record_type}")
        if parent is not None:
            declared[class_name] = parent
    if not declared:
        raise OfflineClassError(f"record type {record_type}: class {source} has no tl:offline")
    return _agree(record_type, declared)


def _check_unused(view: SchemaView, module: str, used: set[str]) -> None:
    for class_name, definition in view.all_classes().items():
        if class_name in used or _module_of(view, class_name) != module:
            continue
        if _annotation(definition, "tl:offline") is not None:
            raise OfflineClassError(
                f"class {class_name} has tl:offline but is neither a record type nor a stream class"
            )


def _module_classes(view: SchemaView, module: str, used: set[str]) -> dict[str, str]:
    found: dict[str, str] = {}
    for class_name, definition in view.all_classes().items():
        if _module_of(view, class_name) != module:
            continue
        if _annotation(definition, "tl:stream_type") is not None:
            raise OfflineClassError(
                f"class {class_name}: tl:stream_type is for core classes only (module {module})"
            )
        raw = _annotation(definition, "tl:record_types")
        if not raw:
            continue
        for record_type in (part.strip() for part in raw.split(",")):
            if record_type:
                found[record_type] = _record_value(view, module, class_name, record_type, used)
    _check_unused(view, module, used)
    return found


def _core_streams(view: SchemaView, used: set[str]) -> dict[str, str]:
    declared: dict[str, dict[str, str]] = {}
    for class_name, definition in view.all_classes().items():
        if _module_of(view, class_name) != "core":
            continue
        stream = _annotation(definition, "tl:stream_type")
        if stream is None:
            continue
        stream = stream.strip()
        if not stream.startswith("core.") or stream == "core.":
            raise OfflineClassError(
                f"class {class_name}: tl:stream_type {stream!r} must name a core stream "
                "(core.<Name>)"
            )
        value = _value(definition, class_name, f"stream {stream}")
        if value is None:
            raise OfflineClassError(
                f"stream {stream}: class {class_name} has tl:stream_type but no tl:offline"
            )
        declared.setdefault(stream, {})[class_name] = value
        used.add(class_name)
    return {stream: _agree(f"stream {stream}", classes) for stream, classes in declared.items()}


def classes(schema_dir: Path) -> tuple[dict[str, str], dict[str, str]]:
    """``(record type -> class, stream type -> class)``, both sorted by name."""
    records: dict[str, str] = {}
    with chdir(schema_dir):
        core = SchemaView(ROOT_SCHEMA)
        used: set[str] = set()
        records[f"core.{CORE_TYPE}"] = _record_value(
            core, "core", CORE_TYPE, f"core.{CORE_TYPE}", used
        )
        streams = _core_streams(core, used)
        _check_unused(core, "core", used)
    for root in module_roots(schema_dir):
        with chdir(root.directory):
            records.update(_module_classes(SchemaView(root.file), root.name, set()))
    return dict(sorted(records.items())), dict(sorted(streams.items()))


def render(records: dict[str, str], streams: dict[str, str]) -> str:
    def block(name: str, found: dict[str, str]) -> str:
        lines = [f"    {json.dumps(key)}: {json.dumps(value)}," for key, value in found.items()]
        return f"{name}: Final[dict[str, OfflineClass]] = {{\n" + "\n".join(lines) + "\n}\n"

    return HEADER + block("OFFLINE_CLASSES", records) + "\n" + block("OFFLINE_STREAMS", streams)


def render_doc(records: dict[str, str], streams: dict[str, str], labels: dict[str, str]) -> str:
    lines = [
        "# Offline classes",
        "",
        "Generated from `tl:offline` and `tl:stream_type` in `schema/`. Do not edit by hand.",
        "",
        "Classes:",
        "",
    ]
    lines += [f"- `{value}`: {MEANINGS[value]}" for value in VALUES]
    lines += [
        "",
        "## Record types",
        "",
        "| Record type | Label | Class | Meaning |",
        "|---|---|---|---|",
    ]
    for record_type, value in records.items():
        label = labels.get(record_type, "")
        lines.append(f"| `{record_type}` | {label} | `{value}` | {MEANINGS[value]} |")
    lines += ["", "## Core streams", "", "| Stream | Class | Meaning |", "|---|---|---|"]
    for stream, value in streams.items():
        lines.append(f"| `{stream}` | `{value}` | {MEANINGS[value]} |")
    return "\n".join(lines) + "\n"


def generate(schema_dir: Path) -> dict[str, str]:
    """Entry point used by ``tl_schema.generate``: the module and the docs page."""
    records, streams = classes(schema_dir)
    labels = type_labels.labels(schema_dir)
    return {OUTPUT: render(records, streams), DOC_OUTPUT: render_doc(records, streams, labels)}
