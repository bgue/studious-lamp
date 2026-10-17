# pyright: basic
"""JSON Schema from the core LinkML schema."""

from __future__ import annotations

from contextlib import chdir
from pathlib import Path

from linkml.generators.jsonschemagen import JsonSchemaGenerator

ROOT_SCHEMA = "core.yaml"

#: Stand-alone document formats described in LinkML, each next to its module: (module directory,
#: schema file, top class, output file). They are not imported by a module root.
DOCUMENT_FORMATS = (
    (
        "documents",
        "publish_mapping.yaml",
        "PublishMapping",
        "json_schema/documents.publish-mapping.schema.json",
    ),
)


def generate(schema_dir: Path) -> dict[str, str]:
    """Return {path relative to generated/: file text}. Runs inside schema_dir."""
    with chdir(schema_dir):
        text = JsonSchemaGenerator(ROOT_SCHEMA).serialize()
    files = {"json_schema/core.schema.json": text}
    for module, file, top_class, output in DOCUMENT_FORMATS:
        directory = schema_dir.parent / "modules" / module
        if not (directory / file).is_file():
            continue
        with chdir(directory):
            files[output] = JsonSchemaGenerator(file, top_class=top_class).serialize()
    return files
