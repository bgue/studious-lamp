# pyright: basic
"""JSON Schema from the core LinkML schema."""

from __future__ import annotations

from contextlib import chdir
from pathlib import Path

from linkml.generators.jsonschemagen import JsonSchemaGenerator

ROOT_SCHEMA = "core.yaml"


def generate(schema_dir: Path) -> dict[str, str]:
    """Return {path relative to generated/: file text}. Runs inside schema_dir."""
    with chdir(schema_dir):
        text = JsonSchemaGenerator(ROOT_SCHEMA).serialize()
    return {"json_schema/core.schema.json": text}
