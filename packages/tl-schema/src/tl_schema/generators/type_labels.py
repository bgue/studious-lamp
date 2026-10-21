# pyright: basic
"""Record-type display names: ``generated/type_labels.py`` from the ``title:`` of record classes.

A record type is named by ``tl:record_types`` on a module class (``documents.Document``), or it is
the generic ``core.Record``. A class annotated with several record types (``Standard``) is titled
through the subclass that has the record type's own name (``CodeList``). Every record type must have
a plain ``title:``; a missing one raises ``TypeLabelsError``, so no type ships without a name.
The output is a sorted ``TYPE_LABELS`` dict, deterministic and drift-checked like the other
generated files.
"""

from __future__ import annotations

import json
from contextlib import chdir
from pathlib import Path
from typing import Any

from linkml_runtime.utils.schemaview import SchemaView

from tl_schema.generators.ddl import _module_of  # pyright: ignore[reportPrivateUsage]
from tl_schema.modules import module_roots

ROOT_SCHEMA = "core.yaml"
OUTPUT = "type_labels.py"
CORE_TYPE = "Record"

HEADER = '''"""Display names of record types, from class titles. Do not edit by hand."""

from __future__ import annotations

from typing import Final

TYPE_LABELS: Final[dict[str, str]] = {
'''


class TypeLabelsError(ValueError):
    """A record type has no usable title."""


def _annotation(element: Any, tag: str) -> str | None:
    annotations = element.annotations
    if not annotations or tag not in annotations:
        return None
    return str(annotations[tag].value)


def _title(view: SchemaView, class_name: str, record_type: str) -> str:
    definition = view.get_class(class_name)
    title = definition.title if definition is not None else None
    if not title or not title.strip():
        raise TypeLabelsError(f"record type {record_type}: class {class_name} has no title")
    return title.strip()


def _module_labels(view: SchemaView, module: str) -> dict[str, str]:
    labels: dict[str, str] = {}
    for class_name, definition in view.all_classes().items():
        if _module_of(view, class_name) != module:
            continue
        raw = _annotation(definition, "tl:record_types")
        if not raw:
            continue
        for record_type in (part.strip() for part in raw.split(",")):
            if not record_type:
                continue
            own = record_type.removeprefix(f"{module}.")
            source = class_name if record_type == f"{module}.{class_name}" else own
            labels[record_type] = _title(view, source, record_type)
    return labels


def labels(schema_dir: Path) -> dict[str, str]:
    """``{record type: title}`` for ``core.Record`` and every module record type."""
    with chdir(schema_dir):
        core = SchemaView(ROOT_SCHEMA)
        found = {f"core.{CORE_TYPE}": _title(core, CORE_TYPE, f"core.{CORE_TYPE}")}
    for root in module_roots(schema_dir):
        with chdir(root.directory):
            found.update(_module_labels(SchemaView(root.file), root.name))
    return dict(sorted(found.items()))


def render(found: dict[str, str]) -> str:
    lines = [f"    {json.dumps(key)}: {json.dumps(value)}," for key, value in found.items()]
    return HEADER + "\n".join(lines) + "\n}\n"


def generate(schema_dir: Path) -> dict[str, str]:
    """Entry point used by ``tl_schema.generate``: ``{"type_labels.py": text}``."""
    return {OUTPUT: render(labels(schema_dir))}
